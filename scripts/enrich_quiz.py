"""
enrich_quiz.py — Arricchisce i campi 'explanation' e 'hint' di un quiz JSON tramite Ollama.

Uso:
    python scripts/enrich_quiz.py [--batch-size N] [--base-url URL] [--model MODEL]

Richiede Ollama in esecuzione (default: http://localhost:11434).
"""

import json
import sys
import time
import argparse
import threading
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Libreria 'requests' mancante! Installa con: pip install requests")
    sys.exit(1)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_BATCH_SIZE = 5

DIM = "\033[2;37m"   # grigio chiaro/dim
RESET = "\033[0m"
CLEAR_LINE = "\r\033[2K"


# ── Spinner ──────────────────────────────────────────────────────────────────

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
            # Scrivi il blocco
            sys.stdout.write(block)
            sys.stdout.flush()
            time.sleep(0.12)
            # Torna su di (1 + len(lines)) righe per sovrascrivere
            rows = 1 + len(self._lines)
            sys.stdout.write(f"\033[{rows}A")
            sys.stdout.flush()
            frame_idx += 1

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        # Cancella tutte le righe occupate dallo spinner
        rows = 1 + len(self._lines)
        for _ in range(rows):
            sys.stdout.write(CLEAR_LINE + "\n")
        sys.stdout.write(f"\033[{rows}A")
        sys.stdout.flush()


# ── Ollama helpers ──────────────────────────────────────────────────────────

def get_ollama_models(base_url: str, api_key: str | None) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        r = requests.get(f"{base_url}/api/tags", headers=headers, timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
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


# ── Prompt ──────────────────────────────────────────────────────────────────

def build_prompt(batch: list[dict]) -> str:
    items = []
    for i, q in enumerate(batch):
        opts = "\n".join(
            f"  {chr(65+j)}) {o['text']}" for j, o in enumerate(q["options"])
        )
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


# ── Parsing risposta ────────────────────────────────────────────────────────

def parse_response(text: str) -> list[dict] | None:
    # Rimuovi eventuali blocchi markdown
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    # Cerca il primo '[' e l'ultimo ']'
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


# ── CLI selection helpers ───────────────────────────────────────────────────

def select_from_list(items: list, label: str) -> int:
    print(f"\n--- {label} ---")
    for i, item in enumerate(items):
        print(f"  [{i+1}] {item}")
    while True:
        raw = input(f"\nScegli [1-{len(items)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return int(raw) - 1
        print("  Scelta non valida, riprova.")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Arricchisce explanation/hint di un quiz con Ollama.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Domande per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"URL base di Ollama (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--model", default=None,
                        help="Modello Ollama da usare (se omesso, selezione interattiva)")
    parser.add_argument("--api-key", default=None,
                        help="API key opzionale (per istanze Ollama con autenticazione)")
    parser.add_argument("--force", action="store_true",
                        help="Rigenera anche domande che hanno già explanation/hint")
    args = parser.parse_args()

    quizzes_root = Path("quizzes")
    json_files = sorted(quizzes_root.glob("**/*.json"))
    if not json_files:
        print("❌ Nessun file JSON trovato in quizzes/")
        sys.exit(1)

    # Selezione file
    labels = [str(f.relative_to(quizzes_root)) for f in json_files]
    idx = select_from_list(labels, "SELEZIONE QUIZ")
    quiz_path = json_files[idx]

    # Carica quiz
    with open(quiz_path, encoding="utf-8") as f:
        quiz_data: list[dict] = json.load(f)

    total = len(quiz_data)
    print(f"\n📋 Quiz caricato: {quiz_path.name} ({total} domande)")

    # Filtra domande da arricchire
    if args.force:
        to_enrich = list(range(total))
    else:
        to_enrich = [
            i for i, q in enumerate(quiz_data)
            if not q.get("explanation") or not q.get("hint")
        ]

    if not to_enrich:
        print("✅ Tutte le domande hanno già explanation e hint. Usa --force per rigenerare.")
        sys.exit(0)

    print(f"🔍 Domande da arricchire: {len(to_enrich)}/{total}")

    # Selezione modello
    if args.model:
        model = args.model
    else:
        models = get_ollama_models(args.base_url, args.api_key)
        if not models:
            print("❌ Nessun modello trovato. Assicurati che Ollama sia in esecuzione.")
            sys.exit(1)
        model_idx = select_from_list(models, "SELEZIONE MODELLO")
        model = models[model_idx]

    print(f"\n🤖 Modello: {model}")
    print(f"📦 Batch size: {args.batch_size}")
    print(f"🌐 URL: {args.base_url}\n")

    # Verifica connessione
    try:
        requests.get(f"{args.base_url}/api/tags", timeout=5)
    except Exception:
        print(f"❌ Impossibile connettersi a {args.base_url}. Ollama è in esecuzione?")
        sys.exit(1)

    # Elaborazione a batch
    batch_size = args.batch_size
    enriched = 0
    failed_batches = 0
    spinner = Spinner()

    for batch_start in range(0, len(to_enrich), batch_size):
        batch_indices = to_enrich[batch_start : batch_start + batch_size]
        batch_questions = [quiz_data[i] for i in batch_indices]

        batch_num = batch_start // batch_size + 1
        total_batches = (len(to_enrich) + batch_size - 1) // batch_size

        preview = [q["question"][:70] + ("…" if len(q["question"]) > 70 else "")
                   for q in batch_questions]
        spinner.start(
            f"Batch {batch_num}/{total_batches} — elaborazione {len(batch_questions)} domande…",
            preview,
        )

        prompt = build_prompt(batch_questions)

        try:
            raw = chat(args.base_url, args.api_key, model, prompt)
            results = parse_response(raw)
        except Exception as e:
            spinner.stop()
            print(f"❌ Batch {batch_num}/{total_batches}: errore — {e}")
            failed_batches += 1
            time.sleep(2)
            continue

        spinner.stop()

        if not results:
            print(f"⚠️  Batch {batch_num}/{total_batches}: risposta non parsabile, saltato.")
            failed_batches += 1
            continue

        # Applica i risultati
        applied = 0
        for item in results:
            local_idx = item.get("index")
            if local_idx is None or not (0 <= local_idx < len(batch_indices)):
                continue
            global_idx = batch_indices[local_idx]
            explanation = str(item.get("explanation", "")).strip()
            hint = str(item.get("hint", "")).strip()
            quiz_data[global_idx]["explanation"] = explanation
            quiz_data[global_idx]["hint"] = hint
            applied += 1

        enriched += applied
        print(f"✅ Batch {batch_num}/{total_batches}: {applied}/{len(batch_questions)} aggiornate")

        # Salvataggio incrementale dopo ogni batch
        with open(quiz_path, "w", encoding="utf-8") as f:
            json.dump(quiz_data, f, indent=2, ensure_ascii=False)

        # Breve pausa tra batch per non sovraccaricare modelli piccoli
        if batch_start + batch_size < len(to_enrich):
            time.sleep(1)

    print(f"\n{'='*50}")
    print(f"✅ Completato: {enriched}/{len(to_enrich)} domande arricchite")
    if failed_batches:
        print(f"⚠️  Batch falliti: {failed_batches}")
    print(f"💾 File salvato: {quiz_path}")


if __name__ == "__main__":
    main()
