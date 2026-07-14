"""
ollama_enrich_quiz.py — Arricchisce i campi 'explanation' e 'hint' di un quiz JSON tramite Ollama.

Uso:
    python scripts/ollama_enrich_quiz.py [--batch-size N] [--base-url URL] [--model MODEL]

Richiede Ollama in esecuzione (default: http://localhost:11434).
"""

import argparse
import json
import sys
import threading
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
_orig_warn = warnings.warn
def _dummy_warn(message, category=None, stacklevel=1, source=None):
    if "duckduckgo_search" in str(message) or "ddgs" in str(message):
        return
    _orig_warn(message, category, stacklevel, source)
warnings.warn = _dummy_warn

try:
    import requests
except ImportError:
    print("❌ Libreria 'requests' mancante! Installa con: pip install requests")
    sys.exit(1)

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

try:
    import termios
    import tty
    import select
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_BATCH_SIZE = 5
DEFAULT_RETRIES = 1
DEFAULT_PLAN_LIMIT = 20

DIM = "\033[2;37m"  # grigio chiaro/dim
RESET = "\033[0m"
CLEAR_LINE = "\r\033[2K"


class DummyContext:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class RawTerminal:
    def __enter__(self):
        self.fd = sys.stdin.fileno()
        try:
            self.old_settings = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        except Exception:
            self.old_settings = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.old_settings is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
            except Exception:
                pass


def is_key_pressed() -> str | None:
    if not HAS_TERMIOS:
        return None
    try:
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1)
    except Exception:
        pass
    return None


def sleep_and_check_keys(seconds: float) -> str | None:
    if not HAS_TERMIOS:
        time.sleep(seconds)
        return None
    start = time.time()
    while time.time() - start < seconds:
        k = is_key_pressed()
        if k:
            return k
        time.sleep(0.05)
    return None





class Spinner:
    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lines: list[str] = []

    def start(self, header: str, lines: list[str]) -> None:
        self._stop_event.clear()
        self._lines = lines
        self._thread = threading.Thread(target=self._run, args=(header,), daemon=True)
        self._thread.start()

    def _run(self, header: str) -> None:
        frame_idx = 0
        while not self._stop_event.is_set():
            frame = self._FRAMES[frame_idx % len(self._FRAMES)]
            block = f"{DIM}{frame} {header}{RESET}\n"
            for line in self._lines:
                block += f"{DIM}  {line}{RESET}\n"
            sys.stdout.write(block)
            sys.stdout.flush()
            time.sleep(0.12)
            rows = 1 + len(self._lines)
            sys.stdout.write(f"\033[{rows}A")
            sys.stdout.flush()
            frame_idx += 1

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        rows = 1 + len(self._lines)
        for _ in range(rows):
            sys.stdout.write(CLEAR_LINE + "\n")
        sys.stdout.write(f"\033[{rows}A")
        sys.stdout.flush()


def get_ollama_models(base_url: str, api_key: str | None) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        r = requests.get(f"{base_url}/api/tags", headers=headers, timeout=8)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        return sorted([n for n in names if n])
    except Exception as e:
        print(f"⚠️  Impossibile recuperare i modelli: {e}")
        return []
def web_search(query: str) -> str:
    if DDGS is None:
        return "Errore: Libreria 'duckduckgo_search' non importata."
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return "Nessun risultato di ricerca pertinente trovato."
            snippets = []
            for r in results:
                title = r.get("title", "N/D")
                body = r.get("body", r.get("snippet", "N/D"))
                snippets.append(f"- Titolo: {title}\n  Contesto: {body}")
            return "\n\n".join(snippets)
    except Exception as e:
        return f"Errore durante la ricerca sul web: {e}"



def chat(base_url: str, api_key: str | None, model: str, prompt: str) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    r = requests.post(
        f"{base_url}/api/chat",
        headers=headers,
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def build_prompt(batch: list[dict]) -> str:
    items = []
    for i, q in enumerate(batch):
        opts = "\n".join(f"  {chr(65+j)}) {o['text']}" for j, o in enumerate(q["options"]))
        correct_letter = chr(65 + q["correctIndex"])
        code_block = f"\nCodice:\n{q['code']}" if q.get("code") else ""
        items.append(
            f"[{i}]\n"
            f"Domanda: {q['question']}{code_block}\n"
            f"Opzioni:\n{opts}\n"
            f"Risposta corretta: {correct_letter}) {q['options'][q['correctIndex']]['text']}"
        )

    questions_text = "\n\n".join(items)

    return f"""Sei un tutor universitario esperto. Per ogni domanda a scelta multipla fornita, devi compilare due campi:

- "explanation": spiega PERCHÉ la risposta indicata è corretta, facendo riferimento al concetto teorico sottostante. Deve essere utile per lo studio. NON dire solo "la risposta X è corretta". Max 2-3 frasi.
- "hint": un breve indizio che aiuti lo studente a ragionare senza rivelare direttamente la risposta. Max 1 frase.

REGOLE IMPORTANTI DI SICUREZZA (ZERO ALLUCINAZIONI):
1. È assolutamente vietato inventare concetti o fatti. La verità scientifica/teorica è la priorità assoluta.
2. Se non hai la certezza assoluta sui concetti teorici della domanda o sul motivo esatto per cui la risposta segnata è corretta, DEVI impostare sia "explanation" che "hint" come stringa vuota "".
3. Meglio un campo vuoto "" piuttosto che una spiegazione parzialmente incerta, dubbiosa, vaga o inventata.
4. Rispondi esclusivamente con un array JSON valido, senza blocchi di markdown (no ```json ... ```), senza alcun testo introduttivo o conclusivo.

FORMATO OUTPUT (array con un oggetto per ogni domanda, nell'ordine ricevuto):
[
  {{"index": 0, "explanation": "...", "hint": "..."}},
  {{"index": 1, "explanation": "...", "hint": "..."}}
]

DOMANDE:

{questions_text}

Rispondi SOLO con l'array JSON:"""


def parse_response(text: str) -> list[dict] | None:
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return None

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list):
        return None
    return parsed


def parse_single_response(text: str) -> dict | None:
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


def select_from_list(items: list[str], label: str) -> int:
    print(f"\n--- {label} ---")
    for i, item in enumerate(items):
        print(f"  [{i + 1}] {item}")
    while True:
        try:
            raw = input(f"\nScegli [1-{len(items)}]: ").strip()
        except EOFError:
            print("\nUscita (EOF).")
            sys.exit(0)
        if raw.lower() in {"q", "quit", "exit"}:
            print("Uscita.")
            sys.exit(0)
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return int(raw) - 1
        print("  Scelta non valida, riprova.")


def status_badge(status: str) -> str:
    if status == "completo":
        return "🟢"
    if status == "incompleto":
        return "🟡"
    return "🔴"


def build_quiz_label(item: dict) -> str:
    badge = status_badge(item["status"])
    return (
        f"{badge} {item['rel']} "
        f"[{item['complete']}/{item['total']} | "
        f"B: {item['missing_both']} | "
        f"E: {item['missing_explanation']} | "
        f"H: {item['missing_hint']}]"
    )


def resolve_quiz_path(quizzes_root: Path, quiz_arg: str | None, scan: dict | None = None) -> Path:
    stats = []
    if scan is not None:
        stats = sorted(scan.get("stats", []), key=lambda x: x["rel"])
    if not stats:
        files = sorted(quizzes_root.glob("**/*.json"))
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    quiz_data = json.load(f)
                if not isinstance(quiz_data, list):
                    continue
            except Exception:
                continue
            total = len(quiz_data)
            complete, missing_explanation, missing_hint, missing_both = summarize_questions(quiz_data)
            status = classify_quiz(total, complete, missing_both)
            stats.append(
                {
                    "path": path,
                    "rel": str(path.relative_to(quizzes_root)),
                    "total": total,
                    "complete": complete,
                    "missing_explanation": missing_explanation,
                    "missing_hint": missing_hint,
                    "missing_both": missing_both,
                    "status": status,
                }
            )

    if not stats:
        print("❌ Nessun file JSON trovato in quizzes/")
        sys.exit(1)

    if quiz_arg:
        candidate = Path(quiz_arg)
        if not candidate.is_absolute():
            if candidate.parts and candidate.parts[0] == "quizzes":
                candidate = Path(*candidate.parts[1:])
            candidate = quizzes_root / candidate
        candidate = candidate.resolve()

        valid_paths = {item["path"].resolve(): item["path"] for item in stats}
        if candidate in valid_paths:
            return valid_paths[candidate]

        print(f"❌ Quiz non trovato: {quiz_arg}")
        print("   Usa un path relativo a quizzes/, ad esempio: sapienza/informatica/uniquizzes/so1.json")
        sys.exit(1)

    labels = [build_quiz_label(item) for item in stats]
    idx = select_from_list(labels, "SELEZIONE QUIZ")
    return stats[idx]["path"]


def question_needs_enrich(q: dict, force: bool) -> bool:
    if force:
        return True
    has_explanation = bool(str(q.get("explanation", "")).strip())
    has_hint = bool(str(q.get("hint", "")).strip())
    return not (has_explanation and has_hint)


def summarize_questions(quiz_data: list[dict]) -> tuple[int, int, int, int]:
    complete = 0
    missing_explanation = 0
    missing_hint = 0
    missing_both = 0
    for q in quiz_data:
        has_explanation = bool(str(q.get("explanation", "")).strip())
        has_hint = bool(str(q.get("hint", "")).strip())
        if has_explanation and has_hint:
            complete += 1
        elif not has_explanation and not has_hint:
            missing_both += 1
        elif not has_explanation:
            missing_explanation += 1
        else:
            missing_hint += 1
    return complete, missing_explanation, missing_hint, missing_both


def classify_quiz(total: int, complete: int, missing_both: int) -> str:
    if total == 0:
        return "da fare"
    if complete == total:
        return "completo"
    if missing_both == total:
        return "da fare"
    return "incompleto"


def scan_all_quizzes(quizzes_root: Path) -> dict:
    files = sorted(quizzes_root.glob("**/*.json"))
    if not files:
        return {"files": [], "stats": [], "groups": {"completo": [], "incompleto": [], "da fare": []}}

    stats: list[dict] = []
    groups = {"completo": [], "incompleto": [], "da fare": []}

    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                quiz_data = json.load(f)
            if not isinstance(quiz_data, list):
                continue
        except Exception:
            continue

        total = len(quiz_data)
        complete, missing_explanation, missing_hint, missing_both = summarize_questions(quiz_data)
        status = classify_quiz(total, complete, missing_both)
        rel = str(path.relative_to(quizzes_root))

        item = {
            "path": path,
            "rel": rel,
            "total": total,
            "complete": complete,
            "missing_explanation": missing_explanation,
            "missing_hint": missing_hint,
            "missing_both": missing_both,
            "status": status,
        }
        stats.append(item)
        groups[status].append(item)

    return {"files": files, "stats": stats, "groups": groups}


def print_scan_report(scan: dict) -> None:
    groups = scan["groups"]
    total_quiz = len(scan["stats"])
    print("\n🔎 Scansione quiz completata")
    print(f"📚 Quiz trovati: {total_quiz}")
    print(f"✅ Completi: {len(groups['completo'])}")
    print(f"🛠️  Incompleti: {len(groups['incompleto'])}")
    print(f"🆕 Da fare: {len(groups['da fare'])}")

    def print_group(title: str, key: str, limit: int = 10) -> None:
        items = groups[key]
        print(f"\n{title} ({len(items)}):")
        if not items:
            print("  - nessuno")
            return
        for item in items[:limit]:
            print(
                f"  - {item['rel']} "
                f"[{item['complete']}/{item['total']} | "
                f"B: {item['missing_both']} | "
                f"E: {item['missing_explanation']} | "
                f"H: {item['missing_hint']}]"
            )
        if len(items) > limit:
            print(f"  ... altri {len(items) - limit}")

    print_group("✅ Completi", "completo")
    print_group("🛠️  Incompleti", "incompleto")
    print_group("🆕 Da fare", "da fare")


def print_batch_plan(total: int, batch_size: int, to_enrich: list[int], plan_limit: int) -> None:
    to_enrich_set = set(to_enrich)
    total_batches = (total + batch_size - 1) // batch_size
    complete_batches = 0
    enrich_batches = 0

    print("\n🧭 Piano batch:")
    shown = 0
    for batch_start in range(0, total, batch_size):
        batch_num = batch_start // batch_size + 1
        batch_end = min(batch_start + batch_size, total) - 1
        batch_indices = list(range(batch_start, min(batch_start + batch_size, total)))
        pending = [i for i in batch_indices if i in to_enrich_set]

        if pending:
            enrich_batches += 1
            status = "da popolare"
            details = f"{len(pending)}/{len(batch_indices)} domande ({', '.join(str(i) for i in pending)})"
        else:
            complete_batches += 1
            status = "completo"
            details = f"{len(batch_indices)}/{len(batch_indices)} complete"

        if plan_limit < 0 or shown < plan_limit:
            print(f"  - Batch {batch_num}/{total_batches} [{batch_start}-{batch_end}]: {status} — {details}")
            shown += 1

    if plan_limit >= 0 and total_batches > plan_limit:
        hidden = total_batches - plan_limit
        print(f"  ... ({hidden} batch non mostrati, usa --plan-limit -1 per vederli tutti)")

    print(f"📦 Batch totali: {total_batches}")
    print(f"✅ Batch completi: {complete_batches}")
    print(f"🛠️  Batch da popolare: {enrich_batches}")


def ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    while True:
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if raw == "":
            return default_yes
        if raw in {"y", "yes", "s", "si"}:
            return True
        if raw in {"n", "no", "q", "quit", "exit"}:
            return False
        print("  Risposta non valida, usa y/n.")


def pick_model(args: argparse.Namespace) -> str:
    models = get_ollama_models(args.base_url, args.api_key)
    cloud_models = [m for m in models if "cloud" in m.lower()]
    if args.model:
        model = args.model
        if models and model not in models:
            print(f"⚠️  Modello '{model}' non trovato in /api/tags, provo comunque.")
        return model
    if not cloud_models:
        print("❌ Nessun modello cloud trovato (i modelli cloud devono contenere 'cloud' nel nome).")
        sys.exit(1)
    model_idx = select_from_list(cloud_models, "SELEZIONE MODELLO (SOLO CLOUD)")
    return cloud_models[model_idx]


def verify_connection(base_url: str) -> None:
    try:
        requests.get(f"{base_url}/api/tags", timeout=5).raise_for_status()
    except Exception:
        print(f"❌ Impossibile connettersi a {base_url}. Ollama è in esecuzione?")
        sys.exit(1)


def test_model_operability(base_url: str, api_key: str | None, model: str) -> tuple[bool, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Rispondi solo con la parola 'OK' se mi senti."}],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    try:
        r = requests.post(
            f"{base_url}/api/chat",
            headers=headers,
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "").strip()
        return True, content
    except Exception as e:
        return False, str(e)
def draw_tui(
    quiz_name: str,
    model: str,
    base_url: str,
    total_q: int,
    initial_complete: int,
    session_enriched: int,
    session_failed: int,
    batch_current: int,
    batch_total: int,
    elapsed_time: float,
    current_questions: list[str],
    logs: list[str],
    status: str = "IN ELABORAZIONE"
):
    # Pulisce lo schermo e porta il cursore all'inizio (home)
    sys.stdout.write("\033[H\033[J")
    
    # Intestazione
    sys.stdout.write("=" * 80 + "\n")
    sys.stdout.write(f" 🤖 OLLAMA QUIZ ENRICHER (TUI)                      Host: {base_url}\n")
    sys.stdout.write("=" * 80 + "\n")
    sys.stdout.write(f" 📋 Quiz: {quiz_name}\n")
    sys.stdout.write(f" 🧠 Modello: {model}\n")
    sys.stdout.write(f" 🚦 Stato: {status}\n")
    sys.stdout.write("-" * 80 + "\n")
    
    # Barra di progresso
    percent = (batch_current / batch_total * 100) if batch_total > 0 else 0
    filled = int(percent / 2.5)  # 40 caratteri totale
    bar = "█" * filled + "░" * (40 - filled)
    sys.stdout.write(f" PROGRESSO SESSIONE:\n")
    sys.stdout.write(f" [{bar}] {percent:.1f}% (Batch {batch_current}/{batch_total})\n\n")
    
    # Statistiche domande
    sys.stdout.write(f" 📊 STATISTICHE DOMANDE:\n")
    sys.stdout.write(f"  • Totale domande nel quiz:    {total_q:,}\n")
    sys.stdout.write(f"  • Già complete all'avvio:    {initial_complete:,}\n")
    sys.stdout.write(f"  • Arricchite in sessione:     {session_enriched:,}\n")
    sys.stdout.write(f"  • Fallite in sessione:        {session_failed:,}\n\n")
    
    # Statistiche tempo
    sys.stdout.write(f" ⏱️ STATISTICHE TEMPO:\n")
    elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed_time))
    sys.stdout.write(f"  • Tempo trascorso:            {elapsed_str}\n")
    if session_enriched > 0 and elapsed_time > 0:
        speed = session_enriched / elapsed_time
        sys.stdout.write(f"  • Velocità media:             {speed:.2f} dom/sec\n")
        remaining = (batch_total - batch_current) * (total_q // batch_total if batch_total > 0 else 0)
        remaining_sec = remaining / speed if speed > 0 else 0
        eta_str = time.strftime('%H:%M:%S', time.gmtime(remaining_sec)) if remaining_sec > 0 else "--:--:--"
        sys.stdout.write(f"  • Tempo stimato (ETA):        ~{eta_str}\n")
    else:
        sys.stdout.write(f"  • Velocità media:             --- dom/sec\n")
        sys.stdout.write(f"  • Tempo stimato (ETA):        --:--:--\n")
    sys.stdout.write("-" * 80 + "\n")
    
    # Domande correnti
    sys.stdout.write(f" 🔄 BATCH CORRENTE ({len(current_questions)} domande):\n")
    for i, q in enumerate(current_questions):
        # Tronca a 74 caratteri
        q_truncated = q[:74] + "..." if len(q) > 74 else q
        sys.stdout.write(f"  {i+1}. {q_truncated}\n")
    sys.stdout.write("\n")
    
    # Log eventi
    sys.stdout.write(" ⚠️ LOG ULTIMI EVENTI:\n")
    for log in logs[-4:]:
        sys.stdout.write(f"  {log}\n")
    sys.stdout.write("=" * 80 + "\n")
    sys.stdout.write(" Comandi: [P] Pausa/Riprendi  |  [Q] Salva ed Esci in sicurezza\n")
    sys.stdout.flush()


def draw_tui_header(title: str, base_url: str):
    sys.stdout.write("\033[H\033[J")
    sys.stdout.write("=" * 80 + "\n")
    sys.stdout.write(f" {title.upper():<50} Host: {base_url}\n")
    sys.stdout.write("=" * 80 + "\n")


def select_quiz_tui(stats: list[dict], base_url: str) -> int | None:
    while True:
        draw_tui_header("Selezione Quiz (TUI)", base_url)
        print(" Scegli il file inserendo il numero corrispondente:\n")
        
        for i, item in enumerate(stats):
            label = build_quiz_label(item)
            print(f"  [{i + 1}] {label}")
            
        print(f"\n  [M] Torna al menu principale")
        print("=" * 80)
        
        try:
            raw = input(" Digita la tua scelta e premi Invio: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
            
        if raw == 'm':
            return None
            
        if raw.isdigit() and 1 <= int(raw) <= len(stats):
            return int(raw) - 1
            
        print("\033[31m Scelta non valida. Riprova...\033[0m")
        time.sleep(1)


def select_model_tui(models: list[str], base_url: str) -> str | None:
    while True:
        draw_tui_header("Selezione Modello Cloud (TUI)", base_url)
        print(" Scegli il modello inserendo il numero corrispondente:\n")
        
        for i, m in enumerate(models):
            print(f"  [{i + 1}] {m}")
            
        print(f"\n  [M] Torna al menu principale")
        print("=" * 80)
        
        try:
            raw = input(" Digita la tua scelta e premi Invio: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
            
        if raw == 'm':
            return None
            
        if raw.isdigit() and 1 <= int(raw) <= len(models):
            return models[int(raw) - 1]
            
        print("\033[31m Scelta non valida. Riprova...\033[0m")
        time.sleep(1)


def run_tests_tui(base_url: str, api_key: str | None) -> None:
    draw_tui_header("Test Modelli Cloud (TUI)", base_url)
    print(" Connessione all'host Ollama...")
    
    try:
        requests.get(f"{base_url}/api/tags", timeout=5).raise_for_status()
        print(" ✅ Connessione all'host Ollama riuscita!\n")
    except Exception as e:
        print(f" ❌ Connessione fallita: {e}\n")
        print("=" * 80)
        input(" Premi Invio per tornare al menu...")
        return

    models = get_ollama_models(base_url, api_key)
    cloud_models = [m for m in models if "cloud" in m.lower()]
    if not cloud_models:
        print(" ❌ Nessun modello cloud trovato (devono contenere 'cloud' nel nome).\n")
        print("=" * 80)
        input(" Premi Invio per tornare al menu...")
        return

    print(f" Esecuzione test di operatività su {len(cloud_models)} modelli cloud:\n")
    for m in cloud_models:
        print(f"  • Modello '{m}': invio chiamata...", end="", flush=True)
        success, msg = test_model_operability(base_url, api_key, m)
        if success:
            print(f"\r  • Modello '{m}': \033[32mOPERATIVO!\033[0m (Risposta: '{msg}')")
        else:
            print(f"\r  • Modello '{m}': \033[31mNON OPERATIVO\033[0m. Dettaglio: {msg}")
            
    print("\n" + "=" * 80)
    input(" Premi Invio per tornare al menu principale...")


def check_quiz_diagnostics(quiz_data: list[dict]) -> list[str]:
    errors = []
    seen_ids = set()
    for idx, item in enumerate(quiz_data):
        missing_fields = []
        for fld in ['id', 'question', 'options', 'correctIndex']:
            if fld not in item:
                missing_fields.append(fld)
        if missing_fields:
            errors.append(f"Domanda all'indice {idx}: manca di campi obbligatori ({', '.join(missing_fields)}).")
            continue

        try:
            import uuid
            question_id = str(uuid.UUID(item['id']))
            if question_id in seen_ids:
                errors.append(f"Domanda all'indice {idx}: UUID duplicato '{question_id}'.")
            seen_ids.add(question_id)
        except Exception:
            errors.append(f"Domanda all'indice {idx}: 'id' deve essere un UUID valido.")

        if not isinstance(item.get('options'), list) or len(item['options']) == 0:
            errors.append(f"Domanda all'indice {idx}: deve avere un array 'options' non vuoto.")
            continue

        correct_index = item.get('correctIndex')
        if not isinstance(correct_index, int):
            errors.append(f"Domanda all'indice {idx}: 'correctIndex' deve essere un intero.")
        elif correct_index < 0 or correct_index >= len(item['options']):
            errors.append(f"Domanda all'indice {idx}: 'correctIndex' non valido ({correct_index}).")
            
    return errors


def browse_questions_paginated(questions: list[tuple[int, dict, str]], title: str):
    page_size = 2
    total_pages = (len(questions) + page_size - 1) // page_size
    current_page = 0

    while True:
        sys.stdout.write("\033[H\033[J")
        sys.stdout.write("=" * 80 + "\n")
        sys.stdout.write(f" 🔍 {title} (Pagina {current_page + 1} di {total_pages})\n")
        sys.stdout.write(f" Trovate {len(questions)} domande corrispondenti.\n")
        sys.stdout.write("=" * 80 + "\n\n")

        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(questions))

        for idx_in_filter in range(start_idx, end_idx):
            global_idx, q, issue_desc = questions[idx_in_filter]
            sys.stdout.write(f" 📌 [DOMANDA ALL'INDICE {global_idx}] UUID: {q.get('id', 'N/D')}\n")
            sys.stdout.write(f"  • Problema: \033[31m{issue_desc}\033[0m\n")
            sys.stdout.write(f"  • Testo:     {q.get('question', '')}\n")
            if q.get('code'):
                sys.stdout.write(f"    Codice:\n")
                for line in q['code'].split('\n'):
                    sys.stdout.write(f"      {line}\n")
            sys.stdout.write(f"  • Opzioni:\n")
            for j, o in enumerate(q.get('options', [])):
                prefix = "    "
                if j == q.get('correctIndex'):
                    prefix = "  👉"
                sys.stdout.write(f"{prefix} {chr(65+j)}) {o.get('text', '')}\n")
            
            exp = str(q.get('explanation', '')).strip()
            hint = str(q.get('hint', '')).strip()
            sys.stdout.write(f"  • Spiegazione: {f'{DIM}{exp}{RESET}' if exp else '[Vuota]'}\n")
            sys.stdout.write(f"  • Suggerimento: {hint if hint else '[Vuoto]'}\n")
            sys.stdout.write("-" * 80 + "\n")

        sys.stdout.write("\n COMANDI:\n")
        sys.stdout.write("  [N] Pagina successiva  |  [P] Pagina precedente  |  [B] Torna all'esploratore\n")
        sys.stdout.write("=" * 80 + "\n")

        try:
            cmd = input(" Digita un comando: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == 'b':
            break
        elif cmd == 'n':
            if current_page < total_pages - 1:
                current_page += 1
        elif cmd == 'p':
            if current_page > 0:
                current_page -= 1


def explore_quiz_tui(quiz_path: Path):
    try:
        with open(quiz_path, encoding="utf-8") as f:
            quiz_data = json.load(f)
    except Exception as e:
        print(f"\n❌ Errore nel caricamento del file: {e}")
        time.sleep(2)
        return

    total = len(quiz_data)
    complete, missing_explanation, missing_hint, missing_both = summarize_questions(quiz_data)
    structural_errors = check_quiz_diagnostics(quiz_data)

    while True:
        sys.stdout.write("\033[H\033[J")
        sys.stdout.write("=" * 80 + "\n")
        sys.stdout.write(f" 📊 ESPLORAZIONE E DIAGNOSTICA: {quiz_path.name}\n")
        sys.stdout.write("=" * 80 + "\n")
        sys.stdout.write(f" Percorso: {quiz_path}\n\n")
        
        sys.stdout.write(f" STATISTICHE DOMANDE:\n")
        sys.stdout.write(f"  • Totale domande:             {total}\n")
        if total > 0:
            sys.stdout.write(f"  • Complete (Spieg.+Sugger.):   {complete} ({(complete/total*100):.1f}%)\n")
            sys.stdout.write(f"  • Incomplete:                 {total - complete} ({((total-complete)/total*100):.1f}%)\n")
        else:
            sys.stdout.write(f"  • Complete (Spieg.+Sugger.):   {complete} (0.0%)\n")
            sys.stdout.write(f"  • Incomplete:                 {total - complete} (0.0%)\n")
        sys.stdout.write(f"     - Mancano entrambi:        {missing_both}\n")
        sys.stdout.write(f"     - Manca solo spiegazione:  {missing_explanation}\n")
        sys.stdout.write(f"     - Manca solo suggerimento: {missing_hint}\n\n")

        sys.stdout.write(f" DIAGNOSTICA STRUTTURALE (validate.py):\n")
        if structural_errors:
            sys.stdout.write(f"  ❌ Rilevati {len(structural_errors)} errori strutturali:\n")
            for err in structural_errors[:5]:
                sys.stdout.write(f"    - {err}\n")
            if len(structural_errors) > 5:
                sys.stdout.write(f"    ... e altri {len(structural_errors) - 5} errori\n")
        else:
            sys.stdout.write("  ✅ Nessun errore di struttura rilevato (il file rispetta i campi obbligatori).\n")
        sys.stdout.write("-" * 80 + "\n")
        
        sys.stdout.write(" SCEGLI COSA ESPLORARE:\n")
        sys.stdout.write("  [1] Domande con spiegazione mancante\n")
        sys.stdout.write("  [2] Domande con suggerimento mancante\n")
        sys.stdout.write("  [3] Domande con entrambi mancanti\n")
        sys.stdout.write("  [4] Domande con errori strutturali (diagnostica)\n")
        sys.stdout.write("  [5] Tutte le domande incomplete\n")
        sys.stdout.write("\n  [M] Torna al menu principale\n")
        sys.stdout.write("=" * 80 + "\n")
        
        try:
            choice = input(" Digita la tua scelta e premi Invio: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == 'm':
            break

        filtered_questions = []
        filter_title = ""
        
        if choice == '1':
            filter_title = "DOMANDE CON SPIEGAZIONE MANCANTE"
            filtered_questions = [
                (idx, q, "Manca spiegazione") 
                for idx, q in enumerate(quiz_data) 
                if not str(q.get("explanation", "")).strip()
            ]
        elif choice == '2':
            filter_title = "DOMANDE CON SUGGERIMENTO MANCANTE"
            filtered_questions = [
                (idx, q, "Manca suggerimento") 
                for idx, q in enumerate(quiz_data) 
                if not str(q.get("hint", "")).strip()
            ]
        elif choice == '3':
            filter_title = "DOMANDE CON ENTRAMBI MANCANTI"
            filtered_questions = [
                (idx, q, "Manca spiegazione e suggerimento") 
                for idx, q in enumerate(quiz_data) 
                if not str(q.get("explanation", "")).strip() and not str(q.get("hint", "")).strip()
            ]
        elif choice == '4':
            filter_title = "DOMANDE CON ERRORI STRUTTURALI"
            err_indices = {}
            for err in structural_errors:
                import re
                m = re.search(r"all'indice (\d+)", err)
                if m:
                    idx = int(m.group(1))
                    if idx not in err_indices:
                        err_indices[idx] = []
                    err_indices[idx].append(err)
            
            filtered_questions = [
                (idx, quiz_data[idx], "\n".join(err_indices[idx]))
                for idx in sorted(err_indices.keys())
            ]
        elif choice == '5':
            filter_title = "TUTTE LE DOMANDE INCOMPLETE"
            filtered_questions = []
            for idx, q in enumerate(quiz_data):
                has_explanation = bool(str(q.get("explanation", "")).strip())
                has_hint = bool(str(q.get("hint", "")).strip())
                if not (has_explanation and has_hint):
                    details = []
                    if not has_explanation: details.append("Manca spiegazione")
                    if not has_hint: details.append("Manca suggerimento")
                    filtered_questions.append((idx, q, " & ".join(details)))
        else:
            print("\033[31m Scelta non valida. Riprova...\033[0m")
            time.sleep(1)
            continue

        if not filtered_questions:
            print(f"\n✅ Nessuna domanda trovata per questo filtro!")
            time.sleep(1.5)
            continue

        browse_questions_paginated(filtered_questions, filter_title)


def main_menu_tui(args: argparse.Namespace) -> tuple[Path | None, str | None, int]:
    quizzes_root = Path("quizzes")
    scan = scan_all_quizzes(quizzes_root)
    if not scan["stats"]:
        print("❌ Nessun file JSON valido trovato in quizzes/")
        sys.exit(1)
        
    selected_quiz_path: Path | None = None
    selected_model: str | None = None
    selected_batch_size: int = args.batch_size if args.batch_size > 0 else 5
    
    if args.quiz:
        candidate = Path(args.quiz)
        if not candidate.is_absolute():
            candidate = quizzes_root / candidate
        candidate = candidate.resolve()
        valid_paths = {item["path"].resolve(): item["path"] for item in scan["stats"]}
        if candidate in valid_paths:
            selected_quiz_path = valid_paths[candidate]
            
    if args.model:
        selected_model = args.model
        
    while True:
        draw_tui_header("Menu Principale (TUI)", args.base_url)
        
        quiz_label = selected_quiz_path.name if selected_quiz_path else "\033[31m[Nessun quiz selezionato]\033[0m"
        model_label = selected_model if selected_model else "\033[31m[Nessun modello selezionato]\033[0m"
        
        print(" STATO CONFIGURAZIONE:")
        print(f"  • Quiz attivo:     {quiz_label}")
        print(f"  • Modello cloud:   {model_label}")
        print(f"  • Dimensione Batch:{selected_batch_size}\n")
        
        print(" OPERAZIONI DISPONIBILI:")
        print("  [1] Seleziona Quiz")
        print("  [2] Seleziona Modello Cloud")
        print("  [3] Esegui Test Operatività Modelli")
        print("  [4] Cambia dimensione Batch")
        print("  [5] Avvia Arricchimento Quiz")
        print("  [6] Esplora Statistiche e Dettagli Quiz")
        print("\n  [Q] Esci dallo script")
        print("=" * 80)
        
        with RawTerminal() if HAS_TERMIOS else DummyContext():
            while True:
                time.sleep(0.1)
                choice = is_key_pressed()
                if choice:
                    choice = choice.lower()
                    break
                    
        if choice == '1':
            idx = select_quiz_tui(scan["stats"], args.base_url)
            if idx is not None:
                selected_quiz_path = scan["stats"][idx]["path"]
        elif choice == '2':
            models = get_ollama_models(args.base_url, args.api_key)
            cloud_models = [m for m in models if "cloud" in m.lower()]
            if not cloud_models:
                print("\n\033[31m❌ Impossibile caricare i modelli. Ollama è in esecuzione?\033[0m")
                time.sleep(1.5)
                continue
            model_sel = select_model_tui(cloud_models, args.base_url)
            if model_sel is not None:
                selected_model = model_sel
        elif choice == '3':
            run_tests_tui(args.base_url, args.api_key)
        elif choice == '4':
            draw_tui_header("Modifica Batch Size (TUI)", args.base_url)
            print(f" Inserisci la nuova dimensione per il batch (Corrente: {selected_batch_size}):\n")
            print(" Premere Invio senza digitare per mantenere il valore corrente.")
            print("=" * 80)
            try:
                raw = input(" Nuova dimensione: ").strip()
                if raw != "":
                    if raw.isdigit() and int(raw) > 0:
                        selected_batch_size = int(raw)
                    else:
                        print("\033[31m Dimensione non valida. Riprova...\033[0m")
                        time.sleep(1.5)
            except (EOFError, KeyboardInterrupt):
                pass
        elif choice == '5':
            if not selected_quiz_path:
                print("\n\033[31m⚠️  Seleziona prima un quiz (Opzione [1])!\033[0m")
                time.sleep(1.5)
                continue
            if not selected_model:
                print("\n\033[31m⚠️  Seleziona prima un modello (Opzione [2])!\033[0m")
                time.sleep(1.5)
                continue
            return selected_quiz_path, selected_model, selected_batch_size
        elif choice == '6':
            if not selected_quiz_path:
                print("\n\033[31m⚠️  Seleziona prima un quiz (Opzione [1])!\033[0m")
                time.sleep(1.5)
                continue
            explore_quiz_tui(selected_quiz_path)
            # Ricarichiamo la scansione dopo l'esplorazione per sicurezza
            scan = scan_all_quizzes(quizzes_root)
        elif choice == 'q':
            sys.stdout.write("\033[H\033[J")
            print("Uscita dallo script.")
            sys.exit(0)


def perform_rag_enrichment(args: argparse.Namespace, global_idx: int, q: dict, batch_num: int, total_batches: int,
                           enriched: int, failed_batches: int, logs: list[str], preview_questions: list[str],
                           quiz_path: Path, quiz_data: list[dict], model: str, start_time: float) -> int:
    log_msg = f"🔍 Domanda all'indice {global_idx} saltata per incertezza. Avvio ricerca sul web..."
    if hasattr(args, "headless") and args.headless:
        print(json.dumps({
            "type": "progress",
            "batch": batch_num,
            "total_batches": total_batches,
            "enriched": enriched,
            "failed": failed_batches,
            "log": log_msg
        }), flush=True)
    else:
        logs.append(f"[{time.strftime('%H:%M:%S')}] {log_msg}")
        draw_tui(quiz_path.name, model, args.base_url, len(quiz_data),
                 sum(1 for x in quiz_data if x.get("explanation", "").strip() and x.get("hint", "").strip()),
                 enriched, failed_batches, batch_num, total_batches, time.time() - start_time,
                 preview_questions, logs, "RICERCA WEB RAG")
    
    context = web_search(q["question"])
    
    opts_str = "\n".join(f"  {chr(65+j)}) {o['text']}" for j, o in enumerate(q["options"]))
    correct_let = chr(65 + q["correctIndex"])
    code_blk = f"\nCodice:\n{q['code']}" if q.get("code") else ""
    
    rag_prompt = f"""Sei un tutor universitario esperto. La seguente domanda è stata saltata per incertezza delle informazioni:
Domanda: {q['question']}{code_blk}
Opzioni:
{opts_str}
Risposta corretta: {correct_let}) {q['options'][q['correctIndex']]['text']}

Abbiamo eseguito una ricerca web ed ecco il contesto trovato:
=== CONTESTO DI RICERCA ===
{context}
==========================

In base a questo contesto, se ora hai la certezza assoluta sul concetto e sul motivo della risposta corretta, fornisci "explanation" e "hint".
Se rimani incerto, imposta entrambi come stringa vuota "".

REGOLE DI SICUREZZA:
1. Non inventare nulla. La verità teorica è la priorità assoluta.
2. Rispondi esclusivamente con un singolo oggetto JSON valido:
{{"explanation": "spiegazione di 2-3 frasi", "hint": "indizio di 1 frase"}}
Qualsiasi testo extra o blocco markdown invaliderà il parsing.

Rispondi SOLO con l'oggetto JSON:"""
    # Aggiorna il log: ricerca completata, invio al modello
    log_msg2 = f"🧠 Ricerca completata per indice {global_idx}. Rielaborazione LLM in corso..."
    if hasattr(args, "headless") and args.headless:
        print(json.dumps({
            "type": "progress",
            "batch": batch_num,
            "total_batches": total_batches,
            "enriched": enriched,
            "failed": failed_batches,
            "log": log_msg2
        }), flush=True)
    else:
        logs.append(f"[{time.strftime('%H:%M:%S')}] {log_msg2}")
        draw_tui(quiz_path.name, model, args.base_url, len(quiz_data),
                 sum(1 for x in quiz_data if x.get("explanation", "").strip() and x.get("hint", "").strip()),
                 enriched, failed_batches, batch_num, total_batches, time.time() - start_time,
                 preview_questions, logs, "RICERCA WEB RAG")

    try:
        raw_rag = chat(args.base_url, args.api_key, model, rag_prompt)
        rag_res = parse_single_response(raw_rag)
        if rag_res and (rag_res.get("explanation", "").strip() or rag_res.get("hint", "").strip()):
            q["explanation"] = str(rag_res.get("explanation", "")).strip()
            q["hint"] = str(rag_res.get("hint", "")).strip()
            enriched += 1
            success_log = f"🎉 Domanda all'indice {global_idx} arricchita con successo via RAG!"
            if hasattr(args, "headless") and args.headless:
                print(json.dumps({
                    "type": "progress",
                    "batch": batch_num,
                    "total_batches": total_batches,
                    "enriched": enriched,
                    "failed": failed_batches,
                    "log": success_log
                }), flush=True)
            else:
                logs.append(f"[{time.strftime('%H:%M:%S')}] {success_log}")
        else:
            fail_log = f"⚠️ Domanda all'indice {global_idx} rimane non arricchita (LLM ancora incerto)."
            if hasattr(args, "headless") and args.headless:
                print(json.dumps({
                    "type": "progress",
                    "batch": batch_num,
                    "total_batches": total_batches,
                    "enriched": enriched,
                    "failed": failed_batches,
                    "log": fail_log
                }), flush=True)
            else:
                logs.append(f"[{time.strftime('%H:%M:%S')}] {fail_log}")
    except Exception as rag_err:
        err_log = f"❌ Errore RAG su indice {global_idx}: {rag_err}"
        if hasattr(args, "headless") and args.headless:
            print(json.dumps({
                "type": "progress",
                "batch": batch_num,
                "total_batches": total_batches,
                "enriched": enriched,
                "failed": failed_batches,
                "log": err_log
            }), flush=True)
        else:
            logs.append(f"[{time.strftime('%H:%M:%S')}] {err_log}")
            
    return enriched


def enrich_single_quiz(args: argparse.Namespace, quiz_path: Path, model: str) -> tuple[int, int, int]:
    with open(quiz_path, encoding="utf-8") as f:
        quiz_data: list[dict] = json.load(f)

    total = len(quiz_data)

    complete, missing_explanation, missing_hint, missing_both = summarize_questions(quiz_data)
    to_enrich = [i for i, q in enumerate(quiz_data) if question_needs_enrich(q, args.force)]

    if not to_enrich:
        print("✅ Tutte le domande hanno già explanation e hint.")
        return 0, 0, 0

    if args.plan_only:
        print(f"\n📋 Quiz caricato: {quiz_path.name} ({total} domande)")
        print(f"✅ Domande complete: {complete}/{total}")
        print(f"🧩 Mancano entrambi: {missing_both} | solo explanation: {missing_explanation} | solo hint: {missing_hint}")
        if args.force:
            print("⚠️  --force attivo: verranno riprocessate tutte le domande.")
        print_batch_plan(total, args.batch_size, to_enrich, args.plan_limit)
        print("ℹ️  Modalità --plan-only: nessuna chiamata al modello eseguita.")
        return 0, len(to_enrich), 0

    logs = [f"[{time.strftime('%H:%M:%S')}] Avvio elaborazione. {len(to_enrich)} domande da arricchire."]
    start_time = time.time()
    enriched = 0
    failed_batches = 0
    pending_key: str | None = None
    
    total_batches = (len(to_enrich) + args.batch_size - 1) // args.batch_size

    if hasattr(args, "headless") and args.headless:
        print(json.dumps({
            "type": "start",
            "quiz": quiz_path.name,
            "model": model,
            "total": total,
            "complete": complete,
            "to_enrich": len(to_enrich),
            "total_batches": total_batches
        }), flush=True)

        for batch_start in range(0, len(to_enrich), args.batch_size):
            batch_indices = to_enrich[batch_start: batch_start + args.batch_size]
            batch_questions = [quiz_data[i] for i in batch_indices]
            batch_num = batch_start // args.batch_size + 1

            prompt = build_prompt(batch_questions)
            results: list[dict] | None = None
            error: Exception | None = None

            for attempt in range(args.retries + 1):
                try:
                    raw = chat(args.base_url, args.api_key, model, prompt)
                    results = parse_response(raw)
                    if results is not None:
                        break
                except Exception as exc:
                    error = exc
                if attempt < args.retries:
                    time.sleep(1.0)

            if results is None:
                failed_batches += 1
                err_msg = str(error) if error is not None else "Risposta non parsabile."
                print(json.dumps({
                    "type": "progress",
                    "batch": batch_num,
                    "total_batches": total_batches,
                    "enriched": enriched,
                    "failed": failed_batches,
                    "log": f"❌ Batch {batch_num} fallito: {err_msg}"
                }), flush=True)
                time.sleep(1.0)
                continue

            applied = 0
            for item in results:
                local_idx = item.get("index")
                if local_idx is None or not (0 <= local_idx < len(batch_indices)):
                    continue
                global_idx = batch_indices[local_idx]
                exp = str(item.get("explanation", "")).strip()
                hnt = str(item.get("hint", "")).strip()
                quiz_data[global_idx]["explanation"] = exp
                quiz_data[global_idx]["hint"] = hnt
                if exp or hnt:
                    applied += 1

            enriched += applied
            
            # RAG/Web Search per domande saltate per incertezza in headless
            if hasattr(args, "with_search") and args.with_search:
                for global_idx in batch_indices:
                    q = quiz_data[global_idx]
                    if not q.get("explanation", "").strip() and not q.get("hint", "").strip():
                        enriched = perform_rag_enrichment(
                            args, global_idx, q, batch_num, total_batches, enriched, failed_batches,
                            [], [], quiz_path, quiz_data, model, start_time
                        )

            # Salva
            with open(quiz_path, "w", encoding="utf-8") as f:
                json.dump(quiz_data, f, indent=2, ensure_ascii=False)

            print(json.dumps({
                "type": "progress",
                "batch": batch_num,
                "total_batches": total_batches,
                "enriched": enriched,
                "failed": failed_batches,
                "log": f"✅ Batch {batch_num} completato ({applied} domande aggiornate)."
            }), flush=True)

            if batch_start + args.batch_size < len(to_enrich):
                time.sleep(1.0)

        status_final = "COMPLETATO" if enriched + failed_batches * args.batch_size >= len(to_enrich) else "INTERROTTO"
        print(json.dumps({
            "type": "finish",
            "enriched": enriched,
            "failed": failed_batches,
            "status": status_final
        }), flush=True)
        return enriched, len(to_enrich), failed_batches

    logs = [f"[{time.strftime('%H:%M:%S')}] Avvio elaborazione. {len(to_enrich)} domande da arricchire."]
    start_time = time.time()
    enriched = 0
    failed_batches = 0
    pending_key: str | None = None

    with RawTerminal() if HAS_TERMIOS else DummyContext():
        for batch_start in range(0, len(to_enrich), args.batch_size):
            batch_indices = to_enrich[batch_start: batch_start + args.batch_size]
            batch_questions = [quiz_data[i] for i in batch_indices]
            batch_num = batch_start // args.batch_size + 1

            # Domande del batch corrente per anteprima
            preview_questions = [q["question"] for q in batch_questions]

            # Controlla tasti prima del batch
            key = pending_key or is_key_pressed()
            pending_key = None
            if key:
                if key.lower() == 'q':
                    logs.append(f"[{time.strftime('%H:%M:%S')}] Interruzione richiesta dall'utente.")
                    draw_tui(quiz_path.name, model, args.base_url, total, complete, enriched, failed_batches,
                             batch_num, total_batches, time.time() - start_time, preview_questions, logs, "INTERROTTO")
                    break
                elif key.lower() == 'p':
                    logs.append(f"[{time.strftime('%H:%M:%S')}] In pausa. Premi 'P' o qualsiasi tasto per riprendere...")
                    draw_tui(quiz_path.name, model, args.base_url, total, complete, enriched, failed_batches,
                             batch_num - 1, total_batches, time.time() - start_time, [], logs, "IN PAUSA")
                    
                    # Ciclo di attesa per la pausa
                    paused = True
                    while paused:
                        time.sleep(0.1)
                        k = is_key_pressed()
                        if k:
                            if k.lower() == 'q':
                                key = 'q'
                                paused = False
                            else:
                                paused = False
                    
                    if key == 'q':
                        logs.append(f"[{time.strftime('%H:%M:%S')}] Interruzione richiesta dall'utente (dalla pausa).")
                        draw_tui(quiz_path.name, model, args.base_url, total, complete, enriched, failed_batches,
                                 batch_num, total_batches, time.time() - start_time, preview_questions, logs, "INTERROTTO")
                        break
                    
                    logs.append(f"[{time.strftime('%H:%M:%S')}] Ripresa elaborazione.")

            # Render iniziale TUI per questo batch
            draw_tui(quiz_path.name, model, args.base_url, total, complete, enriched, failed_batches,
                     batch_num, total_batches, time.time() - start_time, preview_questions, logs, "IN ELABORAZIONE")

            prompt = build_prompt(batch_questions)
            results: list[dict] | None = None
            error: Exception | None = None

            for attempt in range(args.retries + 1):
                try:
                    raw = chat(args.base_url, args.api_key, model, prompt)
                    results = parse_response(raw)
                    if results is not None:
                        break
                except Exception as exc:
                    error = exc
                if attempt < args.retries:
                    k = sleep_and_check_keys(1.0)
                    if k:
                        pending_key = k

            if results is None:
                if error is not None:
                    logs.append(f"[{time.strftime('%H:%M:%S')}] ❌ Batch {batch_num} fallito: {error}")
                else:
                    logs.append(f"[{time.strftime('%H:%M:%S')}] ⚠️ Batch {batch_num}: risposta non parsabile.")
                failed_batches += 1
                # Aggiorna la TUI con l'errore
                draw_tui(quiz_path.name, model, args.base_url, total, complete, enriched, failed_batches,
                         batch_num, total_batches, time.time() - start_time, preview_questions, logs, "IN ELABORAZIONE")
                k = sleep_and_check_keys(1.0)
                if k:
                    pending_key = k
                continue

            applied = 0
            for item in results:
                local_idx = item.get("index")
                if local_idx is None or not (0 <= local_idx < len(batch_indices)):
                    continue
                global_idx = batch_indices[local_idx]
                exp = str(item.get("explanation", "")).strip()
                hnt = str(item.get("hint", "")).strip()
                quiz_data[global_idx]["explanation"] = exp
                quiz_data[global_idx]["hint"] = hnt
                if exp or hnt:
                    applied += 1

            enriched += applied
            logs.append(f"[{time.strftime('%H:%M:%S')}] ✅ Batch {batch_num} completato ({applied} domande aggiornate).")
            
            # RAG/Web Search per domande saltate per incertezza in standard TUI
            if hasattr(args, "with_search") and args.with_search:
                for global_idx in batch_indices:
                    q = quiz_data[global_idx]
                    if not q.get("explanation", "").strip() and not q.get("hint", "").strip():
                        enriched = perform_rag_enrichment(
                            args, global_idx, q, batch_num, total_batches, enriched, failed_batches,
                            logs, preview_questions, quiz_path, quiz_data, model, start_time
                        )

            # Salva
            with open(quiz_path, "w", encoding="utf-8") as f:
                json.dump(quiz_data, f, indent=2, ensure_ascii=False)

            # Ridisegna la TUI aggiornata alla fine del batch
            draw_tui(quiz_path.name, model, args.base_url, total, complete, enriched, failed_batches,
                     batch_num, total_batches, time.time() - start_time, [], logs, "IN ELABORAZIONE")

            if batch_start + args.batch_size < len(to_enrich):
                k = sleep_and_check_keys(1.0)
                if k:
                    pending_key = k

    # Render finale
    elapsed = time.time() - start_time
    status_final = "COMPLETATO" if enriched + failed_batches * args.batch_size >= len(to_enrich) else "INTERROTTO"
    draw_tui(quiz_path.name, model, args.base_url, total, complete, enriched, failed_batches,
             total_batches if status_final == "COMPLETATO" else batch_num,
             total_batches, elapsed, [], logs, status_final)
    
    print(f"\n💾 Sessione terminata. File salvato in: {quiz_path}")
    return enriched, len(to_enrich), failed_batches


def main() -> None:
    parser = argparse.ArgumentParser(description="Arricchisce explanation/hint di un quiz con Ollama.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Domande per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"URL base di Ollama (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--model", default=None,
                        help="Modello Ollama da usare (se omesso, selezione interattiva)")
    parser.add_argument("--quiz", default=None,
                        help="Path quiz relativo a quizzes/ (se omesso, selezione interattiva)")
    parser.add_argument("--api-key", default=None,
                        help="API key opzionale (per istanze Ollama con autenticazione)")
    parser.add_argument("--force", action="store_true",
                        help="Rigenera anche domande che hanno già explanation/hint")
    parser.add_argument("--list-models", action="store_true",
                        help="Mostra i modelli disponibili e termina")
    parser.add_argument("--test", action="store_true",
                        help="Esegue un test di connessione ed effettua una chiamata di prova (chat) per verificare l'operatività del modello")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help=f"Tentativi extra per batch su errore/parse fail (default: {DEFAULT_RETRIES})")
    parser.add_argument("--plan-only", action="store_true",
                        help="Mostra piano batch e termina (senza chiamare Ollama)")
    parser.add_argument("--plan-limit", type=int, default=DEFAULT_PLAN_LIMIT,
                        help=f"Numero massimo di batch da mostrare nel piano (default: {DEFAULT_PLAN_LIMIT}, -1 = tutti)")
    parser.add_argument("--walk-incomplete", action="store_true",
                        help="Processa un quiz incompleto/da fare alla volta, chiedendo se passare al successivo")
    parser.add_argument("--headless", action="store_true",
                        help="Avvia in modalità headless per essere guidato da TUI esterna (es. Bun)")
    parser.add_argument("--with-search", action="store_true",
                        help="Esegue una ricerca web se il modello è incerto ed ha saltato una domanda")
    args = parser.parse_args()

    if args.batch_size <= 0:
        print("❌ --batch-size deve essere > 0")
        sys.exit(1)
    if args.retries < 0:
        print("❌ --retries deve essere >= 0")
        sys.exit(1)

    if args.list_models:
        models = get_ollama_models(args.base_url, args.api_key)
        cloud_models = [m for m in models if "cloud" in m.lower()]
        if not cloud_models:
            print("❌ Nessun modello cloud trovato (i modelli cloud devono contenere 'cloud' nel nome).")
            sys.exit(1)
        print("\nModelli cloud disponibili:")
        for m in cloud_models:
            print(f"- {m}")
        return

    if args.test:
        print(f"📡 Test di connessione a Ollama: {args.base_url}...")
        try:
            requests.get(f"{args.base_url}/api/tags", timeout=5).raise_for_status()
            print("✅ Connessione all'host Ollama riuscita!")
        except Exception as e:
            print(f"❌ Connessione fallita: {e}")
            sys.exit(1)

        models = get_ollama_models(args.base_url, args.api_key)
        cloud_models = [m for m in models if "cloud" in m.lower()]
        if not cloud_models:
            print("❌ Nessun modello cloud disponibile trovato su questa istanza.")
            sys.exit(1)

        to_test = [args.model] if args.model else cloud_models
        print(f"\n🧪 Test di operatività per i modelli cloud ({len(to_test)} da testare):")
        for m in to_test:
            if m not in models and not args.model:
                continue
            print(f"  - Modello '{m}': invio chiamata di test...", end="", flush=True)
            success, msg = test_model_operability(args.base_url, args.api_key, m)
            if success:
                print(f"\r  ✅ Modello '{m}': OPERATIVO! (Risposta: '{msg}')")
            else:
                print(f"\r  ❌ Modello '{m}': NON OPERATIVO. Dettaglio: {msg}")
        return


    quizzes_root = Path("quizzes")
    scan = scan_all_quizzes(quizzes_root)
    if not scan["stats"]:
        print("❌ Nessun file JSON valido trovato in quizzes/")
        sys.exit(1)

    # Se l'utente ha esplicitamente fornito sia quiz che modello da CLI,
    # andiamo direttamente ad arricchire senza mostrare il menu TUI.
    if args.quiz and (args.model or args.plan_only):
        quiz_path = resolve_quiz_path(quizzes_root, args.quiz, scan)
        model = args.model or "<plan-only>"
        if not args.plan_only:
            verify_connection(args.base_url)
        enrich_single_quiz(args, quiz_path, model)
        return

    # Se l'utente ha chiesto walk-incomplete via CLI
    if args.walk_incomplete:
        print_scan_report(scan)
        model = pick_model(args)
        if not args.plan_only:
            verify_connection(args.base_url)
        queue = sorted(
            [s for s in scan["stats"] if s["status"] in {"incompleto", "da fare"}],
            key=lambda x: (0 if x["status"] == "incompleto" else 1, x["rel"]),
        )
        if not queue:
            print("✅ Nessun quiz incompleto/da fare trovato.")
            return

        total_fixed = 0
        total_pending = 0
        processed = 0
        for i, item in enumerate(queue):
            print(f"\n➡️  Quiz {i + 1}/{len(queue)}: {item['rel']} ({item['status']})")
            enriched, pending, _ = enrich_single_quiz(args, item["path"], model)
            total_fixed += enriched
            total_pending += pending
            processed += 1
            if i < len(queue) - 1 and not ask_yes_no("Vuoi passare al prossimo quiz?", default_yes=True):
                break

        print(f"\n🏁 Sessione completata: quiz processati {processed}, arricchite {total_fixed}/{total_pending} domande.")
        return

    # Di default, usiamo il Menu principale interattivo (TUI)
    quiz_path, model, batch_size = main_menu_tui(args)
    if quiz_path and model:
        args.batch_size = batch_size
        enrich_single_quiz(args, quiz_path, model)


if __name__ == "__main__":
    main()
