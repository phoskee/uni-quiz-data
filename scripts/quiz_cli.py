#!/usr/bin/env python3
"""
CLI interattiva per eseguire gli script del progetto da un solo entry point.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

COMMANDS = [
    {
        "key": "generate",
        "label": "Genera quiz da PDF (Gemini)",
        "script": "generate_quiz.py",
        "args_hint": "(interattivo)",
        "examples": ["--help"],
    },
    {
        "key": "ollama-enrich",
        "label": "Arricchisci quiz (Ollama)",
        "script": "ollama_enrich_quiz.py",
        "args_hint": "--quiz <path> --model <name> --walk-incomplete --plan-only --force --retries N",
        "examples": [
            "--help",
            "--quiz sapienza/informatica/uniquizzes/so1.json --plan-only",
            "--quiz sapienza/informatica/uniquizzes/so1.json --model llama3.2 --retries 2",
            "--walk-incomplete --model llama3.2",
        ],
    },
    {
        "key": "validate",
        "label": "Valida JSON quiz",
        "script": "validate.py",
        "args_hint": "(nessuno)",
        "examples": ["--help"],
    },
]


def print_menu() -> None:
    print("\n=== Uni Quiz CLI ===")
    for idx, cmd in enumerate(COMMANDS, start=1):
        print(f"[{idx}] {cmd['label']}  ({cmd['script']})  {cmd.get('args_hint', '')}")
    print("[q] Esci")


def ask_selection() -> dict | None:
    while True:
        raw = input("\nSeleziona comando: ").strip().lower()
        if raw in {"q", "quit", "exit"}:
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(COMMANDS):
                return COMMANDS[idx - 1]
        print("Scelta non valida.")


def print_command_help(cmd: dict) -> None:
    print(f"\nScript: {cmd['script']}")
    print("Argomenti comuni:")
    for ex in cmd.get("examples", []):
        print(f"  - {ex}")
    print("Digita `help` per vedere l'help completo dello script.")


def ask_extra_args(cmd: dict) -> list[str]:
    print_command_help(cmd)
    while True:
        raw = input("Argomenti extra (invio per nessuno): ").strip()
        if not raw:
            return []
        if raw.lower() in {"help", "-h", "--help"}:
            run_script(cmd["script"], ["--help"])
            continue
        try:
            return shlex.split(raw)
        except ValueError as exc:
            print(f"Argomenti non validi: {exc}")


def run_script(script_name: str, extra_args: list[str]) -> int:
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"❌ Script non trovato: {script_path}")
        return 1

    cmd = [sys.executable, str(script_path), *extra_args]
    print(f"\n▶ Eseguo: {' '.join(shlex.quote(c) for c in cmd)}\n")
    completed = subprocess.run(cmd, cwd=str(ROOT))
    return completed.returncode


def main() -> int:
    while True:
        print_menu()
        selection = ask_selection()
        if selection is None:
            print("Uscita.")
            return 0

        extra_args = ask_extra_args(selection)
        exit_code = run_script(selection["script"], extra_args)
        print(f"\nCodice uscita: {exit_code}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrotto.")
        raise SystemExit(130)
