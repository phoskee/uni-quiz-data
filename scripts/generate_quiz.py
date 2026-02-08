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
    """Recupera la lista dei modelli disponibili interrogando le API."""
    print("🔍 Recupero modelli disponibili...")
    try:
        models = []
        for m in client.models.list():
            # Filtriamo i modelli Gemini che supportano la generazione di contenuti
            if "generateContent" in m.supported_actions and "gemini" in m.name:
                # Puliamo il nome per lo script (es. models/gemini-1.5-flash -> gemini-1.5-flash)
                models.append(m.name.split("/")[-1])
        return sorted(list(set(models)), reverse=True)
    except Exception as e:
        print(f"⚠️ Errore nel caricamento modelli: {e}")
        return ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

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
    
    for page in doc:
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
        annotated_text += "\n--- PAGINA ---\n"
    return annotated_text

def generate_quiz(text_content, model_name):
    print(f"🤖 Generazione quiz in corso con {model_name}...")
    prompt = f"""
    Analizza il testo seguente estratto da un PDF di quiz universitari.
    Il testo include tag di colore <#RRGGBB>Testo</#RRGGBB>.
    
    REGOLE:
    1. Trova le domande e le opzioni.
    2. La risposta corretta è evidenziata da un colore (spesso VERDE o BLU).
    3. Restituisci SOLO un array JSON di oggetti con: question, options (text, image), correctIndex, explanation, hint.
    
    TESTO:
    {text_content[:50000]}  # Limite di sicurezza per il prompt
    
    JSON:
    """
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
    if not text_content.strip():
        print("❌ Testo non trovato. Il PDF potrebbe essere una scansione.")
        return

    quiz_data = generate_quiz(text_content, model_name)
    
    if quiz_data:
        dest_dir = selected_file.parent.parent / "community"
        dest_dir.mkdir(exist_ok=True)
        out_path = dest_dir / (selected_file.stem + ".json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(quiz_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Salvato in: {out_path}")

if __name__ == "__main__":
    main()