"""Validation of the grader itself.

The rubric this eval is built for asks for a grader that produces neither false
passes nor false failures. That is a claim about the grader, so it gets its own
test suite rather than a sentence in the README:

  * every reference and alternate solution must be reported crash-safe, which
    bounds false failures and shows the grader is not keyed to one
    implementation shape;
  * every known-broken solution must be reported unsafe, *and* must fail on the
    specific invariant its docstring declares, which bounds false passes and
    rules out a solution failing for an unrelated reason;
  * results must be byte-identical across runs, since a counterexample that
    does not reproduce is not evidence.
"""

from __future__ import annotations

import re

import pytest

from faultline.grade import grade
from faultline.loader import SolutionSource, TaskBundle, discover_tasks

TASKS = discover_tasks()
EXPECTED_VIOLATION = re.compile(r'Expected violation:\s*"([^"]+)"')


def _task_ids(bundle: TaskBundle) -> str:
    return bundle.task_id


def _declared_expectation(source: SolutionSource) -> str:
    match = EXPECTED_VIOLATION.search(source.source)
    assert match, (
        f"{source.origin} must declare its expected failure in the module docstring, "
        'in the form: Expected violation: "..."'
    )
    return match.group(1)


def _correct_solutions(task: TaskBundle) -> list[SolutionSource]:
    return [task.reference(), *task.alternates()]


@pytest.mark.parametrize("task", TASKS, ids=_task_ids)
def test_task_has_validation_material(task: TaskBundle) -> None:
    assert task.alternates(), f"{task.task_id}: need at least one alternate correct solution"
    assert len(task.broken()) >= 3, f"{task.task_id}: need at least three known-broken solutions"


@pytest.mark.parametrize("task", TASKS, ids=_task_ids)
def test_correct_solutions_are_accepted(task: TaskBundle) -> None:
    """No false failures, and no dependence on implementation shape."""
    for source in _correct_solutions(task):
        report = grade(task, source)
        assert report.load_error is None, report.load_error
        assert report.public_passed == report.public_total, (
            f"{source.origin}: failed a public scenario"
        )
        assert report.hidden_passed, (
            f"{source.origin} is correct but was reported unsafe.\n{report.counterexample}"
        )


@pytest.mark.parametrize("task", TASKS, ids=_task_ids)
def test_broken_solutions_are_rejected_for_the_right_reason(task: TaskBundle) -> None:
    """No false passes, and no passing-by-accident on an unrelated invariant."""
    for source in task.broken():
        expected = _declared_expectation(source)
        report = grade(task, source)
        assert report.load_error is None, report.load_error
        assert not report.hidden_passed, f"{source.origin} is unsafe but was reported crash-safe"
        joined = " | ".join(report.violations)
        assert expected in joined, (
            f"{source.origin} failed, but on the wrong invariant.\n"
            f"  expected to contain: {expected!r}\n"
            f"  actually reported:   {joined!r}"
        )


@pytest.mark.parametrize("task", TASKS, ids=_task_ids)
def test_hidden_grader_adds_signal_over_the_public_checks(task: TaskBundle) -> None:
    """At least one broken solution must pass every public scenario.

    If the public self-check already caught everything, the fault injection
    would not be measuring anything a developer's own tests do not.
    """
    survivors = [
        source.origin
        for source in task.broken()
        for report in [grade(source=source, task=task)]
        if report.public_passed == report.public_total and not report.hidden_passed
    ]
    assert survivors, (
        f"{task.task_id}: every broken solution is already caught by the public "
        "scenarios, so the hidden grader contributes no signal"
    )


@pytest.mark.parametrize("task", TASKS, ids=_task_ids)
def test_grading_is_deterministic(task: TaskBundle) -> None:
    for source in [task.reference(), *task.broken()]:
        first = grade(task, source)
        second = grade(task, source)
        assert first.traces_run == second.traces_run
        assert first.hidden_passed == second.hidden_passed
        assert first.counterexample == second.counterexample
