# uni-quiz-data 🎓

Questo repository nasce con l'obiettivo di raccogliere, archiviare e standardizzare i quiz universitari. L'idea è quella di creare una base di dati strutturata in formato JSON, utile per facilitare lo studio e permettere l'integrazione di questi dati in applicazioni o piattaforme di apprendimento.

## 🛠 Setup iniziale

Per utilizzare gli script di generazione e validazione, è consigliato configurare un ambiente Python:

### Avvio rapido (consigliato)
```bash
./scripts/quiz_cli.sh
```
Questo comando crea/usa `venv`, installa le dipendenze (solo quando cambiano) e apre una CLI interattiva per lanciare tutti gli script principali.

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

### Quiz a risposta multipla
- `quizzes/<università>/<facoltà>/`:
    - `_docs/`: Contiene il materiale grezzo (PDF, dispense).
    - `community/`: Contiene i quiz generati o revisionati dagli utenti.
    - `uniquizzes/`: (Opzionale) Quiz provenienti da fonti ufficiali o specifiche.

### Domande aperte
- `open-questions/<università>/<facoltà>/<categoria>.json`: Domande a risposta aperta, valutate tramite AI.
    - Il nome del file definisce la categoria (es. `sistemi-operativi.json` diventa "Sistemi Operativi").
    - Ogni file JSON contiene un array di oggetti con campo `text` (obbligatorio), `referenceAnswer` e `hint` (opzionali).

### Altro
- `scripts/`: Strumenti per la generazione e validazione dei quiz.
- `schema/`: Schemi JSON di riferimento.

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
2. Usa il prompt che trovi nella cartella [`prompt/`](prompt/) per generare il JSON.
3. Salva il risultato nella cartella `community/` del corso.

## ✅ Verifica della correttezza

Il controllo della struttura JSON è **automatico** su ogni Pull Request tramite GitHub Actions. Per verificare localmente prima di caricare:
```bash
python3 scripts/validate.py
```

## 📜 Policy sul Copyright e Responsabilità

1. **Origine dei dati**: I quiz devono essere generati esclusivamente a partire da appunti personali, rielaborazioni originali di concetti generali o da materiale di cui si detengono i diritti di distribuzione. È severamente vietato caricare materiale protetto da copyright (scansioni di libri, slide protette, test ufficiali) nella cartella `_docs`.
2. **Responsabilità**: Ogni contributore è l'unico responsabile del materiale che carica. I manutentori del repository si riservano il diritto di rimuovere immediatamente qualsiasi contenuto segnalato per violazione della proprietà intellettuale.
3. **DMCA / Takedown**: Questo progetto ha scopi puramente didattici. Se sei il titolare di un diritto d'autore e ritieni che un contenuto violi il copyright, contattaci inviando una segnalazione: provvederemo alla rimozione immediata del materiale indicato.

## 🚀 Come contribuire

### Quiz a risposta multipla
1. Carica il materiale in `_docs/`.
2. Genera il JSON (automaticamente o via prompt).
3. Verifica il file con lo script.
4. Invia una Pull Request.

### Domande aperte
1. Crea un file JSON in `open-questions/<università>/<facoltà>/<categoria>.json`.
2. Ogni oggetto deve avere almeno il campo `text`. Aggiungi `referenceAnswer` per guidare la valutazione AI e `hint` per aiutare lo studente.
3. Verifica il file con lo script di validazione.
4. Invia una Pull Request.

---
*L'obiettivo è rendere il materiale didattico più accessibile e organizzato attraverso la condivisione.*
