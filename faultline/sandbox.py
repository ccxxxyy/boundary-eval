"""Grade model-written code in a separate process.

Candidate code is arbitrary text from a language model, so it gets its own
interpreter: a hang is bounded by a timeout instead of stalling the run, and a
solution that corrupts its interpreter cannot take the harness with it. The
subprocess communicates only through a JSON file.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def grade_in_subprocess(
    task_dir: Path, solution_path: Path, timeout: float = 180.0
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report.json"
        command = [
            sys.executable,
            "-m",
            "faultline.grade",
            "--task",
            str(task_dir),
            "--solution",
            str(solution_path),
            "--json",
            str(out),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _failed(task_dir, solution_path, f"grading timed out after {timeout:.0f}s")

        if not out.exists():
            detail = (completed.stderr or completed.stdout or "").strip()[-800:]
            return _failed(task_dir, solution_path, f"grader produced no report: {detail}")
        return json.loads(out.read_text(encoding="utf-8"))


def _failed(task_dir: Path, solution_path: Path, reason: str) -> dict[str, Any]:
    return {
        "task_id": task_dir.name,
        "solution": str(solution_path),
        "public_scenarios_passed": 0,
        "public_scenarios_total": 0,
        "public_results": [],
        "crash_safe": False,
        "traces_run": 0,
        "trace_budget_exhausted": False,
        "crash_points_truncated": False,
        "seconds": 0.0,
        "violations": [],
        "counterexample": None,
        "load_error": reason,
    }
