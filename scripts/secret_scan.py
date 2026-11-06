"""Fail if the tree looks like it contains credentials.

Run this before building the submission ZIP. A key in the package is an
automatic integrity failure (FAQ 24, 39). Documentation that names the
environment variable, or this file's own pattern list, is not a hit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".idea",
}

# Real key material, not the name of an environment variable.
SECRETS = (
    re.compile(r"sk-or-v1-[0-9a-fA-F]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"OPENROUTER_API_KEY\s*=\s*sk-"),
    re.compile(r"BEGIN OPENSSH PRIVATE KEY"),
    re.compile(r"aws_secret_access_key\s*=\s*\S+"),
)


def main() -> int:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRETS:
            if pattern.search(text):
                hits.append(f"{path.relative_to(ROOT)}: matches {pattern.pattern}")
    if hits:
        print("secret scan failed:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        return 1
    print("secret scan clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
