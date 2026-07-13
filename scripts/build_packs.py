#!/usr/bin/env python3
"""Genera pacchetti quiz pubblici, deterministici e privi di hint/spiegazioni."""

import argparse
import gzip
import hashlib
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUIZZES = ROOT / "quizzes"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def category_key(label: str) -> str:
    value = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    return re.sub(r"(^-+|-+$)", "", re.sub(r"[^a-z0-9]+", "-", value))


def searchable_text(question: dict) -> str:
    value = " ".join([question["question"], *[option.get("text", "") for option in question["options"]]])
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist/packs")
    args = parser.parse_args()
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)

    source_manifest = json.loads((QUIZZES / "_manifest.json").read_text(encoding="utf-8"))
    pack_manifest = {"schemaVersion": 1, "generatedFrom": "phoskee/uni-quiz-data", "quizzes": []}

    for relative, public_quiz_id in sorted(source_manifest["quizzes"].items()):
        path = ROOT / relative
        source_bytes = path.read_bytes()
        source_sha = git_blob_sha(source_bytes)
        questions = json.loads(source_bytes)
        category_counts: dict[str, int] = {}
        categories: dict[str, dict] = {}
        packed_questions = []

        for order, question in enumerate(questions, 1):
            label = question.get("category") or None
            key = category_key(label) if label else None
            category_order = None
            if key:
                category_counts[key] = category_counts.get(key, 0) + 1
                category_order = category_counts[key]
                categories.setdefault(key, {"key": key, "label": label, "position": len(categories) + 1, "questionCount": 0})
                categories[key]["questionCount"] += 1
            packed_questions.append({
                "id": question["id"], "order": order, "categoryKey": key,
                "categoryOrder": category_order, "question": question["question"],
                "options": question["options"], "correctIndex": question["correctIndex"],
                "image": question.get("image", ""), "code": question.get("code", ""),
                "searchableText": searchable_text(question),
            })

        quiz_name = path.stem
        payload = {
            "schemaVersion": 1, "publicQuizId": public_quiz_id, "sourceSha": source_sha,
            "path": relative, "title": quiz_name, "questionCount": len(packed_questions),
            "categories": list(categories.values()), "questions": packed_questions,
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        digest = hashlib.sha256(compressed).hexdigest()
        asset = f"{public_quiz_id}/{source_sha}.json.gz"
        target = output / asset
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(compressed)
        pack_manifest["quizzes"].append({
            "publicQuizId": public_quiz_id, "sourceSha": source_sha, "path": relative,
            "title": quiz_name, "questionCount": len(packed_questions), "asset": asset,
            "compressedBytes": len(compressed), "uncompressedBytes": len(raw), "sha256": digest,
        })

    (output / "manifest.json").write_text(json.dumps(pack_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generati {len(pack_manifest['quizzes'])} pacchetti in {output}")


if __name__ == "__main__":
    main()
