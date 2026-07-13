#!/usr/bin/env python3
"""
gemini_enrich_quiz.py — Arricchisce i campi 'explanation' e 'hint' di un quiz JSON tramite le API di Google Gemini.

Uso:
    python scripts/gemini_enrich_quiz.py
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
    from google import genai
    from google.genai import types
    from dotenv import load_dotenv
except ImportError:
    print("❌ Librerie mancanti! Installa con: pip install google-genai requests python-dotenv")
    sys.exit(1)

try:
    import termios
    import tty
    import select
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

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


def get_available_gemini_models(client: genai.Client) -> list[str]:
    try:
        models = []
        for m in client.models.list():
            if "generateContent" in m.supported_actions and "gemini" in m.name:
                models.append(m.name.split("/")[-1])
        # Filtriamo per includere solo i modelli flash/pro più rilevanti
        relevant = [m for m in models if "flash" in m or "pro" in m]
        return sorted(list(set(relevant or models)), reverse=True)
    except Exception:
        # Fallback se le API falliscono o non c'è rete
        return ["gemini-3.5-flash", "gemini-3.0-flash"]


def chat_gemini(client: genai.Client, model: str, prompt: str) -> str:
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
    )
    return response.text.strip()


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
4. Rispondi esclusivamente con un array JSON valido, senza blocchi di markdown, senza alcun testo introduttivo o conclusivo.

FORMATO OUTPUT (array con un oggetto per ogni domanda, nell'ordine ricevuto):
[
  {{"index": 0, "explanation": "...", "hint": "..."}},
  {{"index": 1, "explanation": "...", "hint": "..."}}
]

DOMANDE:

{questions_text}

Rispondi solo con l'array JSON conforme al formato:"""


def parse_response(text: str) -> list[dict] | None:
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        # Tenta il parse diretto dell'intera stringa
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return None
        return None

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list):
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
            candidate = quizzes_root / candidate
        candidate = candidate.resolve()

        valid_paths = {item["path"].resolve(): item["path"] for item in stats}
        if candidate in valid_paths:
            return valid_paths[candidate]

        print(f"❌ Quiz non trovato: {quiz_arg}")
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
        if path.name.startswith("_"):
            continue
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


def draw_tui_header(title: str):
    sys.stdout.write("\033[H\033[J")
    sys.stdout.write("=" * 80 + "\n")
    sys.stdout.write(f" 🤖 GEMINI QUIZ ENRICHER (TUI)                     API: Google AI Studio\n")
    sys.stdout.write("=" * 80 + "\n")


def draw_tui(
    quiz_name: str,
    model: str,
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
    sys.stdout.write("\033[H\033[J")
    sys.stdout.write("=" * 80 + "\n")
    sys.stdout.write(f" 🤖 GEMINI QUIZ ENRICHER (TUI)                     API: Google AI Studio\n")
    sys.stdout.write("=" * 80 + "\n")
    sys.stdout.write(f" 📋 Quiz: {quiz_name}\n")
    sys.stdout.write(f" 🧠 Modello: {model}\n")
    sys.stdout.write(f" 🚦 Stato: {status}\n")
    sys.stdout.write("-" * 80 + "\n")

    percent = (batch_current / batch_total * 100) if batch_total > 0 else 0
    filled = int(percent / 2.5)
    bar = "█" * filled + "░" * (40 - filled)
    sys.stdout.write(f" PROGRESSO SESSIONE:\n")
    sys.stdout.write(f" [{bar}] {percent:.1f}% (Batch {batch_current}/{batch_total})\n\n")

    sys.stdout.write(f" 📊 STATISTICHE DOMANDE:\n")
    sys.stdout.write(f"  • Totale domande nel quiz:    {total_q:,}\n")
    sys.stdout.write(f"  • Già complete all'avvio:    {initial_complete:,}\n")
    sys.stdout.write(f"  • Arricchite in sessione:     {session_enriched:,}\n")
    sys.stdout.write(f"  • Fallite in sessione:        {session_failed:,}\n\n")

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

    sys.stdout.write(f" 🔄 BATCH CORRENTE ({len(current_questions)} domande):\n")
    for i, q in enumerate(current_questions):
        q_truncated = q[:74] + "..." if len(q) > 74 else q
        sys.stdout.write(f"  {i+1}. {q_truncated}\n")
    sys.stdout.write("\n")

    sys.stdout.write(" ⚠️ LOG ULTIMI EVENTI:\n")
    for log in logs[-4:]:
        sys.stdout.write(f"  {log}\n")
    sys.stdout.write("=" * 80 + "\n")
    sys.stdout.write(" Comandi: [P] Pausa/Riprendi  |  [Q] Salva ed Esci in sicurezza\n")
    sys.stdout.flush()


def select_quiz_tui(stats: list[dict]) -> int | None:
    while True:
        draw_tui_header("Selezione Quiz (TUI)")
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


def select_model_tui(models: list[str]) -> str | None:
    while True:
        draw_tui_header("Selezione Modello Gemini (TUI)")
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


def run_key_test_tui(client: genai.Client) -> None:
    draw_tui_header("Verifica API Key Gemini (TUI)")
    print(" Tentativo di connessione a Google AI Studio...")
    try:
        # Eseguiamo una chiamata leggerissima di test
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents="Rispondi solo con la parola 'OK'."
        )
        resp_text = response.text.strip()
        print(f" ✅ API Key VALIDA ed OPERATIVA!")
        print(f" 💬 Risposta test: '{resp_text}'\n")
    except Exception as e:
        print(f" ❌ Connessione o API Key non valida: {e}\n")
    print("=" * 80)
    input(" Premi Invio per tornare al menu principale...")


def main_menu_tui(args: argparse.Namespace, client: genai.Client) -> tuple[Path | None, str | None]:
    quizzes_root = Path("quizzes")
    scan = scan_all_quizzes(quizzes_root)
    if not scan["stats"]:
        print("❌ Nessun file JSON valido trovato in quizzes/")
        sys.exit(1)

    selected_quiz_path: Path | None = None
    selected_model: str | None = "gemini-3.5-flash"  # Default raccomandato ed economico

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
        draw_tui_header("Menu Principale (TUI)")
        quiz_label = selected_quiz_path.name if selected_quiz_path else "\033[31m[Nessun quiz selezionato]\033[0m"
        model_label = selected_model if selected_model else "\033[31m[Nessun modello selezionato]\033[0m"

        print(" STATO CONFIGURAZIONE:")
        print(f"  • Quiz attivo:     {quiz_label}")
        print(f"  • Modello Gemini:  {model_label}\n")

        print(" OPERAZIONI DISPONIBILI:")
        print("  [1] Seleziona Quiz")
        print("  [2] Seleziona Modello Gemini")
        print("  [3] Esegui Test Validità API Key")
        print("  [4] Avvia Arricchimento Quiz")
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
            idx = select_quiz_tui(scan["stats"])
            if idx is not None:
                selected_quiz_path = scan["stats"][idx]["path"]
        elif choice == '2':
            models = get_available_gemini_models(client)
            model_sel = select_model_tui(models)
            if model_sel is not None:
                selected_model = model_sel
        elif choice == '3':
            run_key_test_tui(client)
        elif choice == '4':
            if not selected_quiz_path:
                print("\n\033[31m⚠️  Seleziona prima un quiz (Opzione [1])!\033[0m")
                time.sleep(1.5)
                continue
            if not selected_model:
                print("\n\033[31m⚠️  Seleziona prima un modello (Opzione [2])!\033[0m")
                time.sleep(1.5)
                continue
            return selected_quiz_path, selected_model
        elif choice == 'q':
            sys.stdout.write("\033[H\033[J")
            print("Uscita.")
            sys.exit(0)


def enrich_single_quiz(client: genai.Client, args: argparse.Namespace, quiz_path: Path, model: str) -> tuple[int, int, int]:
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
    total_batches = (len(to_enrich) + args.batch_size - 1) // args.batch_size

    with RawTerminal() if HAS_TERMIOS else DummyContext():
        for batch_start in range(0, len(to_enrich), args.batch_size):
            batch_indices = to_enrich[batch_start: batch_start + args.batch_size]
            batch_questions = [quiz_data[i] for i in batch_indices]
            batch_num = batch_start // args.batch_size + 1
            preview_questions = [q["question"] for q in batch_questions]

            # Controlla tasti prima del batch
            key = is_key_pressed()
            if key:
                if key.lower() == 'q':
                    logs.append(f"[{time.strftime('%H:%M:%S')}] Interruzione richiesta dall'utente.")
                    draw_tui(quiz_path.name, model, total, complete, enriched, failed_batches,
                             batch_num, total_batches, time.time() - start_time, preview_questions, logs, "INTERROTTO")
                    break
                elif key.lower() == 'p':
                    logs.append(f"[{time.strftime('%H:%M:%S')}] In pausa. Premi 'P' o qualsiasi tasto per riprendere...")
                    draw_tui(quiz_path.name, model, total, complete, enriched, failed_batches,
                             batch_num - 1, total_batches, time.time() - start_time, [], logs, "IN PAUSA")
                    
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
                        draw_tui(quiz_path.name, model, total, complete, enriched, failed_batches,
                                 batch_num, total_batches, time.time() - start_time, preview_questions, logs, "INTERROTTO")
                        break
                    
                    logs.append(f"[{time.strftime('%H:%M:%S')}] Ripresa elaborazione.")

            draw_tui(quiz_path.name, model, total, complete, enriched, failed_batches,
                     batch_num, total_batches, time.time() - start_time, preview_questions, logs, "IN ELABORAZIONE")

            prompt = build_prompt(batch_questions)
            results: list[dict] | None = None
            error: Exception | None = None

            for attempt in range(args.retries + 1):
                try:
                    raw = chat_gemini(client, model, prompt)
                    results = parse_response(raw)
                    if results is not None:
                        break
                except Exception as exc:
                    error = exc
                    # Gestione esplicita del Rate Limit (quota esaurita, HTTP 429 o analogo)
                    exc_str = str(exc).lower()
                    if "429" in exc_str or "resource_exhausted" in exc_str or "quota" in exc_str or "exhausted" in exc_str:
                        logs.append(f"[{time.strftime('%H:%M:%S')}] ⚠️ Quota API esaurita. Auto-attesa di 30s...")
                        draw_tui(quiz_path.name, model, total, complete, enriched, failed_batches,
                                 batch_num, total_batches, time.time() - start_time, preview_questions, logs, "PAUSA QUOTA (30s)")
                        time.sleep(30)
                        # Consenti di rieseguire questo tentativo del batch
                        continue
                if attempt < args.retries:
                    time.sleep(2)

            if results is None:
                if error is not None:
                    logs.append(f"[{time.strftime('%H:%M:%S')}] ❌ Batch {batch_num} fallito: {error}")
                else:
                    logs.append(f"[{time.strftime('%H:%M:%S')}] ⚠️ Batch {batch_num}: risposta non parsabile.")
                failed_batches += 1
                draw_tui(quiz_path.name, model, total, complete, enriched, failed_batches,
                         batch_num, total_batches, time.time() - start_time, preview_questions, logs, "IN ELABORAZIONE")
                time.sleep(2)
                continue

            applied = 0
            for item in results:
                local_idx = item.get("index")
                if local_idx is None or not (0 <= local_idx < len(batch_indices)):
                    continue
                global_idx = batch_indices[local_idx]
                quiz_data[global_idx]["explanation"] = str(item.get("explanation", "")).strip()
                quiz_data[global_idx]["hint"] = str(item.get("hint", "")).strip()
                applied += 1

            enriched += applied
            logs.append(f"[{time.strftime('%H:%M:%S')}] ✅ Batch {batch_num} completato ({applied} domande aggiornate).")
            
            with open(quiz_path, "w", encoding="utf-8") as f:
                json.dump(quiz_data, f, indent=2, ensure_ascii=False)

            draw_tui(quiz_path.name, model, total, complete, enriched, failed_batches,
                     batch_num, total_batches, time.time() - start_time, [], logs, "IN ELABORAZIONE")

            if batch_start + args.batch_size < len(to_enrich) and args.delay > 0:
                # Pausa di cortesia tra i batch per rimanere sotto i 15 RPM
                steps = int(args.delay * 10)
                for _ in range(steps):
                    time.sleep(0.1)
                    k = is_key_pressed()
                    if k:
                        break

    elapsed = time.time() - start_time
    status_final = "COMPLETATO" if enriched + failed_batches * args.batch_size >= len(to_enrich) else "INTERROTTO"
    draw_tui(quiz_path.name, model, total, complete, enriched, failed_batches,
             total_batches if status_final == "COMPLETATO" else batch_num,
             total_batches, elapsed, [], logs, status_final)
    
    print(f"\n💾 Sessione terminata. File salvato in: {quiz_path}")
    return enriched, len(to_enrich), failed_batches


def main() -> None:
    parser = argparse.ArgumentParser(description="Arricchisce explanation/hint di un quiz con Google Gemini.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Domande per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--model", default=None,
                        help="Modello Gemini da usare (default: selezione interattiva / gemini-3.5-flash)")
    parser.add_argument("--quiz", default=None,
                        help="Path quiz relativo a quizzes/ (se omesso, selezione interattiva)")
    parser.add_argument("--force", action="store_true",
                        help="Rigenera anche domande che hanno già explanation/hint")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help=f"Tentativi extra per batch su errore/parse fail (default: {DEFAULT_RETRIES})")
    parser.add_argument("--plan-only", action="store_true",
                        help="Mostra piano batch e termina (senza chiamare Gemini)")
    parser.add_argument("--plan-limit", type=int, default=DEFAULT_PLAN_LIMIT,
                        help=f"Numero massimo di batch da mostrare nel piano (default: {DEFAULT_PLAN_LIMIT}, -1 = tutti)")
    parser.add_argument("--delay", type=float, default=4.0,
                        help="Ritardo in secondi tra i batch per rispettare il rate limit (default: 4.0, usa 0 per nessun ritardo)")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ Chiave API GEMINI_API_KEY non trovata nel file .env! Assicurati che sia configurata.")
        sys.exit(1)

    client = genai.Client(api_key=API_KEY)

    if args.quiz and (args.model or args.plan_only):
        quizzes_root = Path("quizzes")
        scan = scan_all_quizzes(quizzes_root)
        quiz_path = resolve_quiz_path(quizzes_root, args.quiz, scan)
        model = args.model or "gemini-3.5-flash"
        enrich_single_quiz(client, args, quiz_path, model)
        return

    quiz_path, model = main_menu_tui(args, client)
    if quiz_path and model:
        enrich_single_quiz(client, args, quiz_path, model)


if __name__ == "__main__":
    main()
