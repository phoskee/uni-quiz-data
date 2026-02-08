# 🤖 Prompt per la Generazione Quiz

Copia e incolla questo prompt nella tua LLM preferita (ChatGPT, Claude, Gemini) insieme al documento che trovi in `_docs/`.

---

**Inizio Prompt**

Agisci come un Professore Universitario esperto nella materia trattata nel documento fornito. Il tuo compito è trasformare il materiale didattico in un set di domande a scelta multipla di alta qualità.

**ISTRUZIONI TECNICHE:**
Genera un output esclusivamente in formato JSON che sia un array di oggetti, seguendo rigorosamente queste regole:

1. **Struttura Campi:**
   - `question`: Formula una domanda chiara e non ambigua.
   - `options`: Fornisci esattamente 4 opzioni. Ogni opzione è un oggetto `{ "text": "...", "image": "" }`.
   - `correctIndex`: Indica l'indice (0, 1, 2 o 3) della risposta corretta.
   - `image`: Lascia stringa vuota "" a meno che il testo non faccia esplicito riferimento a un'immagine necessaria.
   - `code`: Se la domanda riguarda programmazione o logica, inserisci qui lo snippet di codice, altrimenti lascia stringa vuota "".
   - `explanation`: Scrivi una spiegazione pedagogica che aiuti a capire il concetto.
   - `hint`: Fornisci un indizio sottile che spinga a ragionare.

2. **Qualità dei Contenuti:**
   - I "distrattori" (risposte errate) devono essere plausibili.
   - Evita opzioni come "Tutte le precedenti" o "Nessuna delle precedenti".
   - Assicurati che ci sia una sola risposta corretta.

**SCHEMA JSON DI RIFERIMENTO:**
```json
[
  {
    "question": "Esempio di domanda?",
    "options": [
      { "text": "Risposta A", "image": "" },
      { "text": "Risposta B", "image": "" },
      { "text": "Risposta C", "image": "" },
      { "text": "Risposta D", "image": "" }
    ],
    "correctIndex": 0,
    "image": "",
    "code": "",
    "explanation": "Spiegazione approfondita...",
    "hint": "Suggerimento..."
  }
]
```

**MATERIALE DI PARTENZA:**
[Carica il file o incolla qui il testo del documento]

**Fine Prompt**
