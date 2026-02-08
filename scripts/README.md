# 🛠 Script Utility

In questa cartella trovi gli strumenti per gestire e generare i quiz.

## 📦 Setup Ambiente (Consigliato)

Per evitare conflitti tra librerie, ti consigliamo di usare un ambiente virtuale Python.

### 1. Crea l'ambiente virtuale
```bash
python3 -m venv venv
```

### 2. Attiva l'ambiente
- **Su macOS/Linux:**
  ```bash
  source venv/bin/activate
  ```
- **Su Windows:**
  ```bash
  .\venv\Scripts\activate
  ```

### 3. Installa le dipendenze
```bash
pip install -r scripts/requirements.txt
```

---

## 🚀 Script disponibili

### 1. Generatore di Quiz (`generate_quiz.py`)
Utilizza l'IA di Gemini per convertire i PDF in `_docs/` in file JSON strutturati, analizzando anche pattern visivi come colori e grassetti.

**Uso:**
1. Configura la tua API Key nel file `.env` (usa `.env.example` come base).
2. Carica un PDF in `_docs/`.
3. Lancia: `python scripts/generate_quiz.py`.

### 2. Validatore (`validate.py`)
Controlla che i file JSON nella cartella `quizzes/` rispettino lo schema richiesto dal progetto.

**Uso:**
```bash
python scripts/validate.py
```
