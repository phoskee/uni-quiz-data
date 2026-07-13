#!/usr/bin/env python3
"""Convert a numbered multiple-choice PDF into the Uni-Quiz JSON schema.

This parser targets documents where each item has a numeric prefix followed by
five options labelled A) through E).  The AG2026 police-question database is
one such document: its legend states that option A is the correct answer.

MinerU is still useful as a fallback for scanned PDFs, but this script prefers
the PDF text layer when it exists.  That preserves the reading order of the
two columns, which table extraction alone does not guarantee.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from pypdf import PdfReader


QUESTION_RE = re.compile(r"(?m)^\s*(\d{1,4})\.\s+")
OPTION_RE = re.compile(r"(?m)^\s*([A-E])\)\s*")
EXPECTED_OPTIONS = ("A", "B", "C", "D", "E")
QUESTION_ID_NAMESPACE = uuid.UUID("8200bc4d-aa86-4d3a-a4a7-8b55a44e9f10")

# First question number for each section printed in the AG2026 source PDF.
CATEGORY_BOUNDARIES = (
    (1, "Cultura generale"),
    (1338, "Storia"),
    (2005, "Matematica"),
    (2671, "Cittadinanza e Costituzione"),
    (3337, "Inglese"),
    (4003, "Informatica"),
    (4669, "Ragionamento logico-matematico"),
    (5335, "Ragionamento critico-verbale"),
)


def compact(text: str) -> str:
    """Make PDF line wrapping harmless while preserving the actual content."""
    return re.sub(r"\s+", " ", text).strip()


def category_for(question_number: int) -> str:
    """Return the source-PDF section containing the numbered question."""
    return next(
        category
        for start, category in reversed(CATEGORY_BOUNDARIES)
        if question_number >= start
    )


def quiz_item(question_number: int, question: str, options: list[str]) -> dict[str, Any]:
    """Return an item conforming to schema/schema.json, including empty optionals."""
    return {
        "id": str(uuid.uuid5(QUESTION_ID_NAMESPACE, f"ag2026:{question_number}")),
        "question": question,
        "options": [{"text": option, "image": ""} for option in options],
        "correctIndex": 0,
        "image": "",
        "code": "",
        "explanation": "",
        "hint": "",
        "category": category_for(question_number),
    }


def parse_questions(
    text: str, page_number: int, expected_number: int | None
) -> tuple[list[dict[str, Any]], list[str], int | None]:
    """Parse one page and return valid items plus review messages."""
    matches = list(QUESTION_RE.finditer(text))
    questions: list[dict[str, Any]] = []
    issues: list[str] = []

    selected: list[re.Match[str]] = []
    for match in matches:
        number = int(match.group(1))
        if expected_number is None:
            # The first question of a selected range establishes the sequence.
            expected_number = number
        if number == expected_number:
            selected.append(match)
            expected_number += 1

    for index, match in enumerate(selected):
        number = match.group(1)
        end = selected[index + 1].start() if index + 1 < len(selected) else len(text)
        block = text[match.end() : end]
        option_parts = OPTION_RE.split(block)

        # split() returns [question, label, answer, label, answer, ...].
        labels = option_parts[1::2]
        answers = option_parts[2::2]
        if tuple(labels) != EXPECTED_OPTIONS or len(answers) != len(EXPECTED_OPTIONS):
            issues.append(
                f"pagina {page_number}, domanda {number}: opzioni non riconosciute "
                f"(trovate: {', '.join(labels) or 'nessuna'})"
            )
            continue

        question = compact(option_parts[0])
        options = [compact(answer) for answer in answers]
        if not question or any(not option for option in options):
            issues.append(f"pagina {page_number}, domanda {number}: testo vuoto")
            continue

        questions.append(quiz_item(int(number), question, options))

    return questions, issues, expected_number


def extract(pdf_path: Path, start_page: int, end_page: int | None) -> tuple[list[dict[str, Any]], list[str]]:
    reader = PdfReader(pdf_path)
    if reader.is_encrypted and reader.decrypt("") == 0:
        raise ValueError("Il PDF è cifrato e non accetta una password vuota.")

    last_page = len(reader.pages) if end_page is None else min(end_page, len(reader.pages))
    if not 1 <= start_page <= last_page:
        raise ValueError("Intervallo pagine non valido.")

    all_questions: list[dict[str, Any]] = []
    issues: list[str] = []
    expected_number: int | None = None
    for page_number in range(start_page, last_page + 1):
        text = reader.pages[page_number - 1].extract_text() or ""
        if not text.strip():
            issues.append(f"pagina {page_number}: nessun testo nativo; usare MinerU/OCR")
            continue
        questions, page_issues, expected_number = parse_questions(
            text, page_number, expected_number
        )
        all_questions.extend(questions)
        issues.extend(page_issues)
    return all_questions, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="PDF sorgente")
    parser.add_argument("output", type=Path, help="File JSON da creare")
    parser.add_argument("--start-page", type=int, default=1, help="Prima pagina, base 1")
    parser.add_argument("--end-page", type=int, help="Ultima pagina inclusa, base 1")
    parser.add_argument("--report", type=Path, help="Report JSON con le anomalie da revisionare")
    args = parser.parse_args()

    try:
        questions, issues = extract(args.pdf, args.start_page, args.end_page)
    except (OSError, ValueError) as error:
        print(f"Errore: {error}", file=sys.stderr)
        return 1

    if not questions:
        print("Errore: non è stata estratta nessuna domanda.", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.report:
        report = {
            "source": str(args.pdf),
            "pages": {"start": args.start_page, "end": args.end_page},
            "questionsExtracted": len(questions),
            "issues": issues,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Estratte {len(questions)} domande; anomalie da revisionare: {len(issues)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
