import json
import os
import sys

def validate_quiz_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            return False, "Il root deve essere un array di oggetti."
        
        for idx, item in enumerate(data):
            # Campi obbligatori
            if 'question' not in item or 'options' not in item or 'correctIndex' not in item:
                return False, f"Oggetto all'indice {idx} manca di campi obbligatori (question, options, correctIndex)."
            
            if not isinstance(item['options'], list) or len(item['options']) == 0:
                return False, f"Oggetto all'indice {idx} deve avere un array 'options' non vuoto."
            
            # Controllo tipo e range di correctIndex
            if not isinstance(item['correctIndex'], int):
                return False, f"Oggetto all'indice {idx}: 'correctIndex' deve essere un intero."
                
            if item['correctIndex'] < 0 or item['correctIndex'] >= len(item['options']):
                return False, f"Oggetto all'indice {idx} ha un 'correctIndex' non valido ({item['correctIndex']})."
                
        return True, None
    except json.JSONDecodeError as e:
        return False, f"Errore di parsing JSON: {e}"
    except Exception as e:
        return False, f"Errore generico: {e}"

def main():
    base_dir = 'quizzes'
    if not os.path.exists(base_dir):
        print(f"Errore: La cartella '{base_dir}' non esiste.")
        sys.exit(1)
        
    errors = 0
    files_checked = 0
    
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.json'):
                files_checked += 1
                file_path = os.path.join(root, file)
                is_valid, error_msg = validate_quiz_file(file_path)
                if is_valid:
                    print(f"✅ {file_path}")
                else:
                    print(f"❌ {file_path}: {error_msg}")
                    errors += 1
    
    print(f"\nVerifica completata: {files_checked} file controllati, {errors} errori trovati.")
    if errors > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
