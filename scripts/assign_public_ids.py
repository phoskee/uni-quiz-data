#!/usr/bin/env python3
"""Assegna una sola volta UUID pubblici a quiz e domande esistenti."""

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUIZZES = ROOT / "quizzes"
MANIFEST = QUIZZES / "_manifest.json"


def quiz_files():
    return sorted(
        path for path in QUIZZES.rglob("*.json")
        if not any(part.startswith("_") for part in path.relative_to(QUIZZES).parts)
    )


def main():
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    else:
        manifest = {"schemaVersion": 1, "quizzes": {}}

    quizzes = manifest.setdefault("quizzes", {})
    seen_questions: set[str] = set()
    changed_files = 0

    for path in quiz_files():
        relative = path.relative_to(ROOT).as_posix()
        quizzes.setdefault(relative, str(uuid.uuid4()))
        questions = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for question in questions:
            public_id = question.get("id")
            try:
                parsed = uuid.UUID(public_id) if isinstance(public_id, str) else None
            except ValueError:
                parsed = None
            if parsed is None or str(parsed) in seen_questions:
                public_id = str(uuid.uuid4())
                question["id"] = public_id
                changed = True
            seen_questions.add(public_id)
        if changed:
            path.write_text(json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed_files += 1

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ID assegnati: {len(quizzes)} quiz, {len(seen_questions)} domande; {changed_files} file aggiornati")


if __name__ == "__main__":
    main()
