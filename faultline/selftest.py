"""The public self-check that solution authors are given.

These scenarios cover only failures a developer would naturally write a test
for: a plain delivery, a redelivery after a lost acknowledgement, and each
individual remote-call outcome the task's prompt lists. No process crashes are
injected here.

Keeping this honest matters for the eval's claim. Every condition exercised
below is spelled out in the task prompt, and so is the fact that the process
can die mid-way. The hidden part of the grader is not *what* can go wrong, only
the exhaustive enumeration of *where*. A model that fails the hidden grader but
passes this self-check has written code that looks tested and is not safe -
which is precisely the failure mode worth measuring.

The scenarios are derived from the task's own fault model rather than fixed, so
a task is never self-checked against a fault its prompt did not disclose.
"""

from __future__ import annotations

from typing import Any, Callable

from .faults import TIMEOUT_VARIANTS, AttemptFault, Schedule
from .injector import Task, TraceResult, run_schedule

# A crash point past the end of any attempt: the handler finishes its work and
# the process dies before the acknowledgement is recorded.
ACK_LOST = 10**9

Variants = tuple[tuple[tuple[int, str], ...], ...]


def public_scenarios(variants: Variants = TIMEOUT_VARIANTS) -> list[tuple[str, Schedule]]:
    scenarios: list[tuple[str, Schedule]] = [
        ("normal delivery", Schedule((AttemptFault(),))),
        (
            "redelivery after a lost acknowledgement",
            Schedule((AttemptFault(crash_before_op=ACK_LOST), AttemptFault())),
        ),
    ]

    for variant in variants:
        if not variant:
            continue
        fault = AttemptFault(remote_timeouts=variant)
        scenarios.append((f"no crash, but {fault.describe()}", Schedule((fault,))))

    first_nonempty = next((v for v in variants if v), None)
    if first_nonempty is not None:
        scenarios.append(
            (
                "redelivery, then the same remote failure on the second attempt",
                Schedule(
                    (
                        AttemptFault(crash_before_op=ACK_LOST),
                        AttemptFault(remote_timeouts=first_nonempty),
                    )
                ),
            )
        )
    return scenarios


def run_public_scenarios(
    task: Task,
    make_solution: Callable[[], Any],
    op_budget: int = 64,
    variants: Variants = TIMEOUT_VARIANTS,
) -> list[tuple[str, TraceResult]]:
    return [
        (name, run_schedule(task, make_solution, schedule, op_budget))
        for name, schedule in public_scenarios(variants)
    ]


def format_report(results: list[tuple[str, TraceResult]]) -> str:
    lines = []
    for name, trace in results:
        status = "PASS" if trace.passed else "FAIL"
        lines.append(f"[{status}] {name}")
        for violation in trace.violations:
            lines.append(f"         {violation}")
    passed = sum(1 for _, t in results if t.passed)
    lines.append(f"{passed}/{len(results)} public scenarios passed")
    return "\n".join(lines)
