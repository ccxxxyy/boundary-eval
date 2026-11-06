"""Build the submission ZIP: code, docs, cached results. No venv, no keys, no video."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "faultline-eval.zip"

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    "dist",
}
SKIP_SUFFIXES = {".pyc", ".zip", ".mp4", ".mov", ".webm"}
SKIP_NAMES = {".env"}


def included(path: Path) -> bool:
    rel_parts = path.relative_to(ROOT).parts
    if any(part in SKIP_DIRS for part in rel_parts):
        return False
    if path.name in SKIP_NAMES or path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return True


def main() -> int:
    files = [p for p in ROOT.rglob("*") if p.is_file() and included(p)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(ROOT).as_posix())
    size_mb = OUT.stat().st_size / (1024 * 1024)
    print(f"wrote {OUT} ({size_mb:.2f} MB, {len(files)} files)")
    if size_mb > 50:
        print("ERROR: ZIP exceeds the 50 MB limit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
