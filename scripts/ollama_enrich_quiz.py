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
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Libreria 'requests' mancante! Installa con: pip install requests")
    sys.exit(1)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_BATCH_SIZE = 5
DEFAULT_RETRIES = 1
DEFAULT_PLAN_LIMIT = 20

DIM = "\033[2;37m"  # grigio chiaro/dim
RESET = "\033[0m"
CLEAR_LINE = "\r\033[2K"


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

REGOLE IMPORTANTI:
- Se non sei sicuro della spiegazione, metti stringa vuota "" per quel campo.
- Non inventare informazioni false.
- Rispondi SOLO con un array JSON valido, senza markdown, senza testo aggiuntivo.

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
    if args.model:
        model = args.model
        if models and model not in models:
            print(f"⚠️  Modello '{model}' non trovato in /api/tags, provo comunque.")
        return model
    if not models:
        print("❌ Nessun modello trovato. Assicurati che Ollama sia in esecuzione.")
        sys.exit(1)
    model_idx = select_from_list(models, "SELEZIONE MODELLO")
    return models[model_idx]


def verify_connection(base_url: str) -> None:
    try:
        requests.get(f"{base_url}/api/tags", timeout=5).raise_for_status()
    except Exception:
        print(f"❌ Impossibile connettersi a {base_url}. Ollama è in esecuzione?")
        sys.exit(1)


def enrich_single_quiz(args: argparse.Namespace, quiz_path: Path, model: str) -> tuple[int, int, int]:
    with open(quiz_path, encoding="utf-8") as f:
        quiz_data: list[dict] = json.load(f)

    total = len(quiz_data)
    print(f"\n📋 Quiz caricato: {quiz_path.name} ({total} domande)")

    complete, missing_explanation, missing_hint, missing_both = summarize_questions(quiz_data)
    to_enrich = [i for i, q in enumerate(quiz_data) if question_needs_enrich(q, args.force)]

    print(f"✅ Domande complete: {complete}/{total}")
    print(f"🧩 Mancano entrambi: {missing_both} | solo explanation: {missing_explanation} | solo hint: {missing_hint}")
    if args.force:
        print("⚠️  --force attivo: verranno riprocessate tutte le domande.")

    print_batch_plan(total, args.batch_size, to_enrich, args.plan_limit)

    if not to_enrich:
        print("✅ Tutte le domande hanno già explanation e hint.")
        return 0, 0, 0

    if args.plan_only:
        print("ℹ️  Modalità --plan-only: nessuna chiamata al modello eseguita.")
        return 0, len(to_enrich), 0

    print(f"🔍 Domande da arricchire: {len(to_enrich)}/{total}")
    print(f"\n🤖 Modello: {model}")
    print(f"📦 Batch size: {args.batch_size}")
    print(f"🔁 Retries extra: {args.retries}")
    print(f"🌐 URL: {args.base_url}\n")

    enriched = 0
    failed_batches = 0
    spinner = Spinner()

    for batch_start in range(0, len(to_enrich), args.batch_size):
        batch_indices = to_enrich[batch_start: batch_start + args.batch_size]
        batch_questions = [quiz_data[i] for i in batch_indices]
        batch_num = batch_start // args.batch_size + 1
        total_batches = (len(to_enrich) + args.batch_size - 1) // args.batch_size

        preview = [q["question"][:70] + ("…" if len(q["question"]) > 70 else "") for q in batch_questions]
        spinner.start(
            f"Batch {batch_num}/{total_batches} — elaborazione {len(batch_questions)} domande…",
            preview,
        )

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
                time.sleep(1)

        spinner.stop()

        if results is None:
            if error is not None:
                print(f"❌ Batch {batch_num}/{total_batches}: errore — {error}")
            else:
                print(f"⚠️  Batch {batch_num}/{total_batches}: risposta non parsabile dopo {args.retries + 1} tentativi")
            failed_batches += 1
            time.sleep(1)
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
        print(f"✅ Batch {batch_num}/{total_batches}: {applied}/{len(batch_questions)} aggiornate")

        with open(quiz_path, "w", encoding="utf-8") as f:
            json.dump(quiz_data, f, indent=2, ensure_ascii=False)

        if batch_start + args.batch_size < len(to_enrich):
            time.sleep(1)

    print(f"\n{'=' * 50}")
    print(f"✅ Completato: {enriched}/{len(to_enrich)} domande arricchite")
    if failed_batches:
        print(f"⚠️  Batch falliti: {failed_batches}")
    print(f"💾 File salvato: {quiz_path}")
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
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help=f"Tentativi extra per batch su errore/parse fail (default: {DEFAULT_RETRIES})")
    parser.add_argument("--plan-only", action="store_true",
                        help="Mostra piano batch e termina (senza chiamare Ollama)")
    parser.add_argument("--plan-limit", type=int, default=DEFAULT_PLAN_LIMIT,
                        help=f"Numero massimo di batch da mostrare nel piano (default: {DEFAULT_PLAN_LIMIT}, -1 = tutti)")
    parser.add_argument("--walk-incomplete", action="store_true",
                        help="Processa un quiz incompleto/da fare alla volta, chiedendo se passare al successivo")
    args = parser.parse_args()

    if args.batch_size <= 0:
        print("❌ --batch-size deve essere > 0")
        sys.exit(1)
    if args.retries < 0:
        print("❌ --retries deve essere >= 0")
        sys.exit(1)

    if args.list_models:
        models = get_ollama_models(args.base_url, args.api_key)
        if not models:
            print("❌ Nessun modello trovato. Assicurati che Ollama sia in esecuzione.")
            sys.exit(1)
        print("\nModelli disponibili:")
        for m in models:
            print(f"- {m}")
        return

    quizzes_root = Path("quizzes")
    scan = scan_all_quizzes(quizzes_root)
    if not scan["stats"]:
        print("❌ Nessun file JSON valido trovato in quizzes/")
        sys.exit(1)
    print_scan_report(scan)

    if args.walk_incomplete:
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

    quiz_path = resolve_quiz_path(quizzes_root, args.quiz, scan)
    model = pick_model(args) if not args.plan_only else (args.model or "<plan-only>")
    if not args.plan_only:
        verify_connection(args.base_url)
    enrich_single_quiz(args, quiz_path, model)


if __name__ == "__main__":
    main()
