"""Degenerate solutions must be contained, not merely tolerated.

Model output in practice includes code that never terminates, code that does
not import, and code that catches everything in sight. If any of those can hang
the run or sneak through as a pass, the headline numbers are not trustworthy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline.grade import grade
from faultline.loader import SolutionSource, load_task

ADVERSARIAL = Path(__file__).parent / "adversarial"
TASK = load_task(Path(__file__).resolve().parent.parent / "tasks" / "t01_idempotent_charge")


def _load(name: str) -> SolutionSource:
    return SolutionSource.from_path(ADVERSARIAL / name)


def test_swallowing_the_crash_is_not_a_pass() -> None:
    report = grade(TASK, _load("swallows_the_crash.py"))
    assert not report.hidden_passed
    assert any("caught SimulatedCrash" in v for v in report.violations), report.violations


def test_infinite_loop_is_stopped_by_the_operation_budget() -> None:
    report = grade(TASK, _load("runs_forever.py"))
    assert not report.hidden_passed
    assert report.seconds < 30, "the operation budget did not contain a runaway solution"


def test_import_failure_is_reported_not_raised() -> None:
    report = grade(TASK, _load("will_not_import.py"))
    assert report.load_error is not None
    assert not report.hidden_passed
    assert "ModuleNotFoundError" in report.load_error


@pytest.mark.parametrize("name", [p.name for p in sorted(ADVERSARIAL.glob("*.py"))])
def test_no_adversarial_input_takes_the_harness_down(name: str) -> None:
    report = grade(TASK, _load(name))
    assert not report.hidden_passed
