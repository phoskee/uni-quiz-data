# Script Utility

In questa cartella trovi gli strumenti per gestire e generare i quiz.

## Setup Ambiente

Per evitare conflitti tra librerie, usa un ambiente virtuale Python.

```bash
# Crea e attiva l'ambiente
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# .\venv\Scripts\activate       # Windows

# Installa le dipendenze
pip install -r scripts/requirements.txt
```

---

## Script disponibili

### `generate_quiz.py` — Generatore di quiz da PDF

Converte un PDF in un file JSON di quiz strutturato usando l'API Gemini.
Estrae il testo dal PDF preservando i colori (usati spesso per evidenziare le risposte corrette), poi invia tutto al modello che identifica domande, opzioni, risposta corretta e genera `explanation` e `hint` per ogni domanda (non perfetto, va rivisto)

**Prerequisiti:**
- Chiave API Gemini configurata in `.env` (vedi `.env.example`)
- PDF sorgente posizionato in `quizzes/<università>/<facoltà>/_docs/`

**Uso:**
```bash
python scripts/generate_quiz.py
```

Il processo è interattivo:
1. Seleziona il PDF da elaborare tra quelli presenti in `_docs/`
2. Seleziona il modello Gemini da usare
3. Il JSON generato viene salvato automaticamente in `community/` nella stessa facoltà

**Output:** `quizzes/<università>/<facoltà>/community/<nome_file>.json`

---

### `enrich_quiz.py` — Arricchitore di explanation e hint via Ollama

Compila i campi `explanation` e `hint` su un quiz JSON esistente usando un modello LLM locale tramite [Ollama](https://ollama.com). Lavora a batch per essere compatibile anche con modelli di piccole dimensioni.

Per ogni domanda ancora priva di spiegazione, invia al modello un batch di domande (con la risposta corretta già nota) chiedendo di produrre:
- `explanation`: perché quella risposta è corretta (concetto teorico, max 2-3 frasi)
- `hint`: un indizio che guidi lo studente senza rivelare la risposta

Il file viene aggiornato dopo ogni batch, quindi in caso di interruzione il lavoro già fatto è preservato. Le domande che hanno già entrambi i campi vengono saltate automaticamente.

**Prerequisiti:**
- [Ollama](https://ollama.com) in esecuzione in locale (o su server remoto)
- Almeno un modello scaricato (es. `ollama pull llama3.2`)

**Uso base:**
```bash
python scripts/enrich_quiz.py
```

Il processo è interattivo: selezioni il file quiz e il modello da usare.

**Opzioni disponibili:**

| Flag | Default | Descrizione |
|---|---|---|
| `--model MODEL` | interattivo | Specifica il modello senza selezione interattiva |
| `--batch-size N` | `5` | Domande per chiamata. Riduci a 3 per modelli < 3B |
| `--base-url URL` | `http://localhost:11434` | URL dell'istanza Ollama |
| `--api-key KEY` | nessuna | API key per istanze Ollama con autenticazione |
| `--force` | off | Rigenera anche le domande che hanno già i campi compilati |

**Esempi:**
```bash
# Usa un modello specifico con batch ridotto per modelli piccoli
python scripts/enrich_quiz.py --model llama3.2 --batch-size 3

# Ollama remoto con autenticazione
python scripts/enrich_quiz.py --base-url https://mio-ollama.example.com --api-key sk-xxx

# Rigenera tutto da capo
python scripts/enrich_quiz.py --force
```

---

### `validate.py` — Validatore della struttura JSON

Controlla che tutti i file `.json` in `quizzes/` rispettino lo schema richiesto dal progetto. Esegue un walk ricorsivo della cartella e verifica per ogni file che:
- Il root sia un array
- Ogni domanda abbia i campi obbligatori: `question`, `options`, `correctIndex`
- `options` sia un array non vuoto
- `correctIndex` sia un intero nel range valido degli indici di `options`

Restituisce exit code `1` se trova almeno un errore (usato dalla CI su GitHub Actions).

**Uso:**
```bash
python scripts/validate.py
```

**Output esempio:**
```
✅ quizzes/sapienza/informatica/sounbot/so1.json
❌ quizzes/sapienza/informatica/community/reti.json: Oggetto all'indice 3 ha un 'correctIndex' non valido (5).

Verifica completata: 12 file controllati, 1 errori trovati.
```
