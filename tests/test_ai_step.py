"""Verifies the AI step against the live Gemini API.

Reads `GEMINI_API_KEY` from the environment or from `.streamlit/secrets.toml`, and skips
cleanly when neither is present — so the suite is safe to run without credentials.

    .venv/Scripts/python.exe tests/test_ai_step.py
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "demo"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app import GEMINI_MODEL, ai_review, qualify  # noqa: E402

failures: list[str] = []


def load_key() -> str | None:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    path = ROOT / ".streamlit" / "secrets.toml"
    if not path.exists():
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))["GEMINI_API_KEY"]
    except (KeyError, ValueError):
        return None


key = load_key()
if not key:
    print("SKIP  no GEMINI_API_KEY in the environment or .streamlit/secrets.toml")
    sys.exit(0)

print(f"model={GEMINI_MODEL}")

row = qualify("bloggerspassion.com", "personal finance")
print(f"row: {row['Domain']} signal={row['Guest-post signal']} email={row['Contact Email'] or '-'}")

review = ai_review(row, key)
reason = str(review.get("Reason for fit", ""))

if reason.startswith("AI step failed"):
    print(f"FAIL  {reason}")
    failures.append("ai_review failed")

for field in ("Relevance", "Reason for fit", "Outreach subject", "Outreach body"):
    value = str(review.get(field, ""))
    filled = bool(value.strip())
    print(f"{'PASS' if filled else 'FAIL'}  {field}: {value[:120]!r}")
    if not filled:
        failures.append(field)

if not isinstance(review.get("Relevance"), int):
    print(f"FAIL  Relevance is not an integer: {review.get('Relevance')!r}")
    failures.append("Relevance type")

leaked = key in reason
print(f"{'FAIL' if leaked else 'PASS'}  the key never appears in failure text")
if leaked:
    failures.append("key leaked into an error message")

print()
print(f"result: {'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
