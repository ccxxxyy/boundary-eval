"""Print the grader-validation matrix for every task.

    python -m faultline.matrix

This is the evidence behind the eval's central claim. For each task it grades
the reference, the alternate correct solutions and the known-broken ones, and
shows two columns side by side: how each fares against the public self-check,
and how it fares against exhaustive fault injection.

The rows that matter are the ones marked `<-- signal`: solutions that pass
every check a developer would write and are still not crash-safe. Those are the
bugs this eval exists to find.
"""

from __future__ import annotations

import sys

from .grade import grade
from .loader import SolutionSource, TaskBundle, discover_tasks


def _row(task: TaskBundle, source: SolutionSource, expectation: str) -> tuple[str, ...]:
    report = grade(task, source, include_counterexample=False)
    name = source.origin.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    if report.load_error:
        public = "error"
        hidden = "error"
    else:
        public = f"{report.public_passed}/{report.public_total}"
        hidden = "crash-safe" if report.hidden_passed else "UNSAFE"

    verdict = ""
    if expectation == "correct" and not report.hidden_passed:
        verdict = "<-- FALSE FAILURE"
    elif expectation == "broken" and report.hidden_passed:
        verdict = "<-- FALSE PASS"
    elif (
        expectation == "broken"
        and not report.hidden_passed
        and report.public_passed == report.public_total
    ):
        verdict = "<-- signal"

    return name, expectation, public, hidden, str(report.traces_run), verdict


def main() -> int:
    tasks = discover_tasks()
    signal_rows = 0
    problems = 0

    for task in tasks:
        title = getattr(task.module, "TITLE", task.task_id)
        print(f"\n{task.task_id}  -  {title}")
        print("-" * 96)
        print(
            f"{'solution':<44} {'expected':<9} {'public':<7} {'injection':<11} "
            f"{'traces':<7} "
        )

        rows = [
            *((s, "correct") for s in [task.reference(), *task.alternates()]),
            *((s, "broken") for s in task.broken()),
        ]
        for source, expectation in rows:
            name, exp, public, hidden, traces, verdict = _row(task, source, expectation)
            if "signal" in verdict:
                signal_rows += 1
            if "FALSE" in verdict:
                problems += 1
            print(f"{name:<44} {exp:<9} {public:<7} {hidden:<11} {traces:<7} {verdict}")

    print()
    print(f"{len(tasks)} tasks")
    print(
        f"{signal_rows} broken solutions pass every public scenario and are still caught by "
        "fault injection"
    )
    if problems:
        print(f"{problems} GRADER PROBLEM(S): see the rows marked above")
        return 1
    print("no false passes and no false failures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
