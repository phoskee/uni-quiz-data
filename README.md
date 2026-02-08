# uni-quiz-data 🎓

Questo repository nasce con l'obiettivo di raccogliere, archiviare e standardizzare i quiz universitari. L'idea è quella di creare una base di dati strutturata in formato JSON, utile per facilitare lo studio e permettere l'integrazione di questi dati in applicazioni o piattaforme di apprendimento.

## 🛠 Setup iniziale

Per utilizzare gli script di generazione e validazione, è consigliato configurare un ambiente Python:

1. **Crea e attiva l'ambiente virtuale:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Su Windows: .\venv\Scripts\activate
   ```
2. **Installa le dipendenze:**
   ```bash
   pip install -r scripts/requirements.txt
   ```
3. **Configura le chiavi:** Copia il file `.env.example` in `.env` e inserisci la tua [Gemini API Key](https://aistudio.google.com/app/apikey).

## 📂 Struttura del repository

Il progetto è organizzato per università e facoltà:
- `quizzes/<università>/<facoltà>/`:
    - `_docs/`: Contiene il materiale grezzo (PDF, dispense).
    - `community/`: Contiene i quiz generati o revisionati dagli utenti.
    - `uniquizzes/`: (Opzionale) Quiz provenienti da fonti ufficiali o specifiche.
- `scripts/`: Strumenti per la generazione e validazione dei quiz.

## 🤖 Come generare un quiz

### 1. Carica il materiale
Inserisci il PDF nella cartella `_docs` del corso di riferimento (es: `quizzes/sapienza/informatica/_docs/esame.pdf`).

### 2. Generazione automatica (Consigliato)
Lo script `generate_quiz.py` usa l'IA per analizzare il PDF e salvarlo nella cartella `community` corretta.
```bash
python scripts/generate_quiz.py
```

### 3. Uso di NotebookLM
Se preferisci usare [NotebookLM](https://notebooklm.google.com/):
1. Carica i file nel notebook.
2. Usa il prompt sotto per generare il JSON.
3. Salva il risultato nella cartella `community/` del corso.

**Prompt consigliato:**
> "Analizza il documento e genera un set di domande a scelta multipla. Il risultato deve essere esclusivamente un array JSON di oggetti:
> {
>   \"question\": \"Testo della domanda\",
>   \"options\": [{\"text\": \"Opzione 1\", \"image\": \"\"}, ...],
>   \"correctIndex\": 0,
>   \"image\": \"\", \"code\": \"\", \"explanation\": \"...\", \"hint\": \"...\"
> }"

## ✅ Verifica della correttezza

Il controllo della struttura JSON è **automatico** su ogni Pull Request tramite GitHub Actions. Per verificare localmente prima di caricare:
```bash
python3 scripts/validate.py
```

## 🚀 Come contribuire

1. Carica il materiale in `_docs/`.
2. Genera il JSON (automaticamente o via prompt).
3. Verifica il file con lo script.
4. Invia una Pull Request.

---
*L'obiettivo è rendere il materiale didattico più accessibile e organizzato attraverso la condivisione.*