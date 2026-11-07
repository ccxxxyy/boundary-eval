"""The review prompt must not leak the answer, and must parse a verdict
out of the kinds of replies models actually produce."""

from __future__ import annotations

from faultline.audit import parse_verdict, without_author_notes
from faultline.loader import load_task


def test_author_notes_are_stripped_before_review() -> None:
    task = load_task("tasks/t03_at_least_once_ledger")
    broken = next(s for s in task.broken() if s.origin.endswith("b01_mark_then_apply.py"))
    shown = without_author_notes(broken.source)
    assert "BROKEN" not in shown
    assert "Expected violation" not in shown
    assert "def handle_message" in shown


def test_correct_code_is_not_stripped_of_its_body() -> None:
    task = load_task("tasks/t03_at_least_once_ledger")
    shown = without_author_notes(task.reference().source)
    assert "def handle_message" in shown
    assert "def read_balance" in shown


def test_parse_verdict_from_json() -> None:
    verdict, reason = parse_verdict(
        'Here is my review.\n{"verdict": "UNSAFE", "reason": "crash between mark and apply"}'
    )
    assert verdict == "UNSAFE"
    assert "mark" in reason


def test_parse_verdict_prefers_the_last_json_object() -> None:
    text = (
        '{"verdict": "SAFE", "reason": "looks fine"}\n'
        '{"verdict": "UNSAFE", "reason": "lost on crash"}'
    )
    verdict, _ = parse_verdict(text)
    assert verdict == "UNSAFE"


def test_probe_ground_truth_matches_the_grader() -> None:
    from faultline.audit import probe_cases

    cases = probe_cases()
    assert len(cases) == 6
    for case in cases:
        assert case.expected in {"SAFE", "UNSAFE"}
        assert (case.expected == "SAFE") == case.actually_safe
        assert "BROKEN" not in case.code
        if case.expected == "UNSAFE":
            assert case.public_passed == case.public_total
