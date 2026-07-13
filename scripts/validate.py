import json
import os
import sys
import uuid

SEEN_QUESTION_IDS = set()

def validate_quiz_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
            return False, "Il root deve essere un array di oggetti."

        for idx, item in enumerate(data):
            # Campi obbligatori
            if 'id' not in item or 'question' not in item or 'options' not in item or 'correctIndex' not in item:
                return False, f"Oggetto all'indice {idx} manca di campi obbligatori (id, question, options, correctIndex)."

            try:
                question_id = str(uuid.UUID(item['id']))
            except (ValueError, TypeError, AttributeError):
                return False, f"Oggetto all'indice {idx}: 'id' deve essere un UUID valido."
            if question_id in SEEN_QUESTION_IDS:
                return False, f"Oggetto all'indice {idx}: UUID duplicato '{question_id}'."
            SEEN_QUESTION_IDS.add(question_id)

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

def validate_open_question_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
            return False, "Il root deve essere un array di oggetti."

        if len(data) == 0:
            return False, "L'array non può essere vuoto."

        for idx, item in enumerate(data):
            if 'text' not in item:
                return False, f"Oggetto all'indice {idx} manca del campo obbligatorio 'text'."

            if not isinstance(item['text'], str) or not item['text'].strip():
                return False, f"Oggetto all'indice {idx}: 'text' deve essere una stringa non vuota."

            # Campi opzionali: devono essere stringhe se presenti
            for field in ('referenceAnswer', 'hint'):
                if field in item and not isinstance(item[field], str):
                    return False, f"Oggetto all'indice {idx}: '{field}' deve essere una stringa."

        return True, None
    except json.JSONDecodeError as e:
        return False, f"Errore di parsing JSON: {e}"
    except Exception as e:
        return False, f"Errore generico: {e}"

def validate_directory(base_dir, validator, label):
    if not os.path.exists(base_dir):
        return 0, 0

    errors = 0
    files_checked = 0

    for root, dirs, files in os.walk(base_dir):
        # Ignora cartelle con prefisso _
        dirs[:] = [d for d in dirs if not d.startswith('_')]
        for file in files:
            if file.endswith('.json') and not file.startswith('_'):
                files_checked += 1
                file_path = os.path.join(root, file)
                is_valid, error_msg = validator(file_path)
                if is_valid:
                    print(f"  ✅ {file_path}")
                else:
                    print(f"  ❌ {file_path}: {error_msg}")
                    errors += 1

    return files_checked, errors

def main():
    total_files = 0
    total_errors = 0

    manifest_path = os.path.join('quizzes', '_manifest.json')
    if not os.path.exists(manifest_path):
        print("❌ quizzes/_manifest.json mancante.")
        sys.exit(1)
    with open(manifest_path, 'r', encoding='utf-8') as manifest_file:
        manifest = json.load(manifest_file)
    manifest_quizzes = manifest.get('quizzes', {})
    quiz_ids = list(manifest_quizzes.values())
    if len(quiz_ids) != len(set(quiz_ids)):
        print("❌ UUID quiz duplicati in quizzes/_manifest.json.")
        sys.exit(1)
    try:
        for quiz_id in quiz_ids:
            uuid.UUID(quiz_id)
    except (ValueError, TypeError, AttributeError):
        print("❌ UUID quiz non valido in quizzes/_manifest.json.")
        sys.exit(1)
    discovered = set()
    for root, dirs, files in os.walk('quizzes'):
        dirs[:] = [d for d in dirs if not d.startswith('_')]
        for file in files:
            if file.endswith('.json') and not file.startswith('_'):
                discovered.add(os.path.join(root, file).replace(os.sep, '/'))
    if discovered != set(manifest_quizzes):
        missing = sorted(discovered - set(manifest_quizzes))
        stale = sorted(set(manifest_quizzes) - discovered)
        print(f"❌ Manifest quiz non allineato. Mancanti={missing}, obsoleti={stale}")
        sys.exit(1)

    # Validazione quiz a risposta multipla
    print("📝 Quiz a risposta multipla (quizzes/):")
    files, errors = validate_directory('quizzes', validate_quiz_file, 'quiz')
    total_files += files
    total_errors += errors
    if files == 0:
        print("  Nessun file trovato.")

    # Validazione domande aperte
    print(f"\n📖 Domande aperte (open-questions/):")
    files, errors = validate_directory('open-questions', validate_open_question_file, 'open-questions')
    total_files += files
    total_errors += errors
    if files == 0:
        print("  Nessun file trovato.")

    print(f"\nVerifica completata: {total_files} file controllati, {total_errors} errori trovati.")
    if total_errors > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
