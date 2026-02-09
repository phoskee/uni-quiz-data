import os
import json
import sys
from pathlib import Path

try:
    from google import genai
    import fitz  # PyMuPDF
    from dotenv import load_dotenv
except ImportError:
    print("❌ Librerie mancanti! Installa con: pip install google-genai pymupdf python-dotenv")
    sys.exit(1)

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY or API_KEY == "tua_chiave_qui":
    print("⚠️  API Key non configurata nel file .env.")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

def get_available_models():
    """Recupera la lista dei modelli disponibili."""
    try:
        models = []
        for m in client.models.list():
            if "generateContent" in m.supported_actions and "gemini" in m.name:
                models.append(m.name.split("/")[-1])
        return sorted(list(set(models)), reverse=True)
    except:
        return ["gemini-2.0-flash", "gemini-1.5-flash"]

def int_to_hex(color_int):
    if color_int is None: return "#000000"
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}"

def extract_text_with_colors(pdf_path):
    doc = fitz.open(pdf_path)
    annotated_text = ""
    print(f"📖 Estrazione testo e colori da '{pdf_path.name}'...")
    
    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if "lines" in b:
                for l in b["lines"]:
                    for s in l["spans"]:
                        color = int_to_hex(s["color"])
                        text = s["text"].strip()
                        if not text: continue
                        if color.lower() not in ["#000000", "#222222", "#333333"]:
                            annotated_text += f"<{color}>{text}</{color}> "
                        else:
                            annotated_text += f"{text} "
                    annotated_text += "\n"
        annotated_text += f"\n--- FINE PAGINA {page_num + 1} ---\n"
    return annotated_text

def generate_quiz(text_content, model_name):
    print(f"🤖 Generazione quiz con {model_name}...")

    prompt = f"""Sei un assistente specializzato nella conversione di quiz universitari da PDF a formato JSON strutturato.

COMPITO:
Analizza il testo estratto da un PDF e converti OGNI domanda trovata in un oggetto JSON.
Preserva fedelmente il contenuto originale: non inventare, modificare o omettere domande e risposte presenti nel documento.

REGOLE PER IDENTIFICARE LA RISPOSTA CORRETTA (in ordine di priorità):
1. Etichette esplicite: righe come "Answer: A", "Risposta corretta: B", "Soluzione: C" vicino alla domanda.
2. Tag di colore: testo racchiuso in tag come <#008000>Testo</#008000>. Il VERDE (#008000, #00ff00) o il BLU (#0000ff, #0055ff) indicano solitamente la risposta corretta.
3. Soluzioni a fine documento: una lista di risposte corrette raggruppata alla fine del PDF.
4. Se nessun metodo funziona, usa la tua conoscenza della materia. Se non sei sicuro, imposta correctIndex sulla risposta più plausibile.

STRUTTURA JSON - Ogni oggetto DEVE avere TUTTI questi campi:
- "question": il testo esatto della domanda, ripulito da numerazione (es. "1.", "Q1:") e artefatti di formattazione.
- "options": array di oggetti con "text" e "image". Mantieni l'ordine originale. Rimuovi i prefissi di lettera (A., B., ecc.) dal testo. Il campo "image" è sempre stringa vuota "".
- "correctIndex": intero 0-based che indica la posizione della risposta corretta (A=0, B=1, C=2, D=3).
- "image": stringa vuota "".
- "code": se la domanda contiene snippet di codice, pseudocodice o output di terminale, inseriscilo qui preservando indentazione e formattazione. Altrimenti stringa vuota "".
- "explanation": una spiegazione chiara e concisa del PERCHÉ la risposta è corretta, facendo riferimento al concetto teorico sottostante. NON scrivere frasi generiche come "La risposta A è corretta" — spiega il ragionamento. Compila questo campo SOLO se sei sicuro della correttezza della risposta e del ragionamento. Se hai dubbi, lascia stringa vuota "".
- "hint": un indizio breve che guidi lo studente verso la risposta corretta senza rivelarla (es. "Pensa alla differenza tra stack e heap"). Compila questo campo SOLO se sei sicuro che l'indizio sia accurato e realmente utile per ragionare. Se hai dubbi, lascia stringa vuota "".

REGOLE IMPORTANTI su "explanation" e "hint":
- È MEGLIO lasciare il campo vuoto che fornire informazioni errate o inventate.
- Se la risposta corretta è stata identificata solo tramite colore o etichetta (e non conosci la materia), lascia entrambi i campi vuoti.
- "explanation" deve spiegare il concetto in modo che lo studente impari qualcosa.
- "hint" non deve MAI contenere la risposta diretta, ma solo uno spunto di riflessione.

ESEMPIO DI OUTPUT:
[
  {{
    "question": "Qual è la complessità temporale della ricerca binaria?",
    "options": [
      {{"text": "O(n)", "image": ""}},
      {{"text": "O(log n)", "image": ""}},
      {{"text": "O(n log n)", "image": ""}},
      {{"text": "O(1)", "image": ""}}
    ],
    "correctIndex": 1,
    "image": "",
    "code": "",
    "explanation": "La ricerca binaria dimezza lo spazio di ricerca ad ogni iterazione, quindi il numero massimo di confronti è log₂(n), da cui la complessità O(log n).",
    "hint": "Quante volte puoi dimezzare n elementi prima di arrivare a 1?"
  }}
]

TESTO ESTRATTO DAL PDF:
{text_content[:60000]}

Restituisci ESCLUSIVAMENTE un array JSON valido, senza testo aggiuntivo, commenti o blocchi markdown:"""
    
    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].strip()
        return json.loads(text)
    except Exception as e:
        print(f"❌ Errore AI: {e}")
        return None

def main():
    quizzes_root = Path("quizzes")
    pdf_files = list(quizzes_root.glob("**/_docs/*.pdf"))
    
    if not pdf_files:
        print("❌ Nessun PDF trovato.")
        return

    print("\n--- SELEZIONE DOCUMENTO ---")
    for i, f in enumerate(pdf_files):
        print(f"[{i+1}] {f.relative_to(quizzes_root)}")
    try:
        sel_f = int(input("\nScegli il file: ")) - 1
        selected_file = pdf_files[sel_f]
    except: return

    models = get_available_models()
    print("\n--- SELEZIONE MODELLO ---")
    for i, m in enumerate(models):
        print(f"[{i+1}] {m}")
    try:
        sel_m = int(input(f"\nScegli il modello [1-{len(models)}]: ") or "1") - 1
        model_name = models[sel_m]
    except: model_name = "gemini-2.0-flash"

    text_content = extract_text_with_colors(selected_file)
    quiz_data = generate_quiz(text_content, model_name)
    
    if quiz_data:
        dest_dir = selected_file.parent.parent / "community"
        dest_dir.mkdir(exist_ok=True)
        # Normalizziamo il nome del file sostituendo gli spazi con _
        file_name = selected_file.stem.replace(" ", "_") + ".json"
        out_path = dest_dir / file_name
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(quiz_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Salvato in: {out_path}")

if __name__ == "__main__":
    main()
