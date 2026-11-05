"""Grade one solution against one task.

    python -m faultline.grade --task tasks/t01_idempotent_charge \
        --solution tasks/t01_idempotent_charge/reference.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .injector import EvalResult, explore
from .loader import SolutionSource, TaskBundle, load_task
from .selftest import format_report, run_public_scenarios


@dataclass
class PublicOutcome:
    name: str
    passed: bool
    violations: list[str]


@dataclass
class Report:
    task_id: str
    solution: str
    public_passed: int
    public_total: int
    hidden_passed: bool
    traces_run: int
    budget_exhausted: bool
    seconds: float
    counterexample: str | None
    violations: list[str]
    public_results: list[PublicOutcome] = field(default_factory=list)
    crash_points_truncated: bool = False
    load_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "solution": self.solution,
            "public_scenarios_passed": self.public_passed,
            "public_scenarios_total": self.public_total,
            "public_results": [
                {"name": o.name, "passed": o.passed, "violations": o.violations}
                for o in self.public_results
            ],
            "crash_safe": self.hidden_passed,
            "traces_run": self.traces_run,
            "trace_budget_exhausted": self.budget_exhausted,
            "crash_points_truncated": self.crash_points_truncated,
            "seconds": round(self.seconds, 3),
            "violations": self.violations,
            "counterexample": self.counterexample,
            "load_error": self.load_error,
        }

    def public_feedback(self) -> str:
        """Exactly what a solution author is allowed to see: the public
        scenarios and how they went. Never the fault-injection results."""
        lines = []
        for outcome in self.public_results:
            lines.append(f"[{'PASS' if outcome.passed else 'FAIL'}] {outcome.name}")
            for violation in outcome.violations:
                lines.append(f"         {violation}")
        return "\n".join(lines)


def grade(
    task: TaskBundle,
    source: SolutionSource,
    max_crashes: int | None = None,
    include_counterexample: bool = True,
) -> Report:
    module = task.module
    max_crashes = max_crashes if max_crashes is not None else getattr(module, "MAX_CRASHES", 2)
    op_budget = getattr(module, "OP_BUDGET", 64)

    started = time.perf_counter()
    try:
        source.instantiate()  # fail fast on syntax errors and bad imports
    except BaseException as exc:  # noqa: BLE001 - any failure to load is reportable
        return Report(
            task_id=task.task_id,
            solution=source.origin,
            public_passed=0,
            public_total=0,
            hidden_passed=False,
            traces_run=0,
            budget_exhausted=False,
            seconds=time.perf_counter() - started,
            counterexample=None,
            violations=[],
            load_error=f"{type(exc).__name__}: {exc}",
        )

    public = run_public_scenarios(module, source.instantiate, op_budget)
    result: EvalResult = explore(
        module, source.instantiate, max_crashes=max_crashes, op_budget=op_budget
    )

    witness = result.minimal_counterexample()
    return Report(
        task_id=task.task_id,
        solution=source.origin,
        public_passed=sum(1 for _, t in public if t.passed),
        public_total=len(public),
        hidden_passed=result.passed,
        traces_run=result.traces_run,
        budget_exhausted=result.budget_exhausted,
        seconds=time.perf_counter() - started,
        counterexample=witness.render() if (witness and include_counterexample) else None,
        violations=list(witness.violations) if witness else [],
        public_results=[
            PublicOutcome(name=name, passed=trace.passed, violations=list(trace.violations))
            for name, trace in public
        ],
        crash_points_truncated=result.crash_points_truncated,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, help="path to a task directory")
    parser.add_argument("--solution", required=True, help="path to a candidate solution module")
    parser.add_argument("--max-crashes", type=int, default=None)
    parser.add_argument("--public-only", action="store_true", help="run only the public self-check")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args(argv)

    task = load_task(args.task)
    source = SolutionSource.from_path(args.solution)

    if args.public_only:
        print(format_report(run_public_scenarios(task.module, source.instantiate)))
        return 0

    report = grade(task, source, max_crashes=args.max_crashes)

    print(f"task      {report.task_id}")
    print(f"solution  {Path(report.solution).name}")
    if report.load_error:
        print(f"LOAD ERROR  {report.load_error}")
        return 1
    print(f"public    {report.public_passed}/{report.public_total} scenarios passed")
    print(
        f"hidden    {'CRASH-SAFE' if report.hidden_passed else 'UNSAFE'} "
        f"after {report.traces_run} fault schedules in {report.seconds:.2f}s"
    )
    if report.counterexample:
        print("\nsmallest counterexample:")
        print(report.counterexample)

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )

    return 0 if report.hidden_passed else 1


if __name__ == "__main__":
    sys.exit(main())
