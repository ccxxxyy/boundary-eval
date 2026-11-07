"""Review, not authorship.

Writing crash-safe code from a fully disclosed spec is a different skill from
noticing that a module which already passes its tests is still unsafe. The
second is what a reviewer does, and it is the failure mode this eval's
known-broken solutions were built to capture: they look finished, they pass
every public scenario, and they lose or double money the first time the
process dies.

The candidate's module docstring is stripped before the model sees it. Those
docstrings say `BROKEN` and name the expected violation; leaving them in
would measure whether the model can read a spoiler, not whether it can review.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass

from .grade import grade
from .loader import SolutionSource, TaskBundle, discover_tasks

VERDICT_RE = re.compile(r'"verdict"\s*:\s*"(SAFE|UNSAFE)"', re.IGNORECASE)

# The cases that decide whether the pivot has signal: four broken solutions
# that pass every public scenario, plus two known-correct ones so a model
# cannot score well by calling everything unsafe.
PROBE = (
    ("t03_at_least_once_ledger", "b01_mark_then_apply.py", "UNSAFE"),
    ("t03_at_least_once_ledger", "b02_apply_then_mark.py", "UNSAFE"),
    ("t06_fenced_payout", "b01_ignores_the_claim_result.py", "UNSAFE"),
    ("t02_outbox_notification", "b01_early_return_when_shipped.py", "UNSAFE"),
    ("t03_at_least_once_ledger", "reference.py", "SAFE"),
    ("t06_fenced_payout", "reference.py", "SAFE"),
)


def without_author_notes(source: str) -> str:
    """Drop the module docstring. It is written for the grader, not for a reviewer."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    docstring = ast.get_docstring(tree)
    if not docstring:
        return source
    body = tree.body
    if not body or not isinstance(body[0], ast.Expr):
        return source
    start = body[0].end_lineno or body[0].lineno
    lines = source.splitlines()
    rest = lines[start:]
    while rest and not rest[0].strip():
        rest.pop(0)
    return "\n".join(rest) + ("\n" if rest else "")


def parse_verdict(text: str) -> tuple[str | None, str]:
    """Pull SAFE/UNSAFE out of a review. Prefer a JSON object; fall back to
    the last explicit verdict word so a truncated reply is not scored as a
    crash-safety judgement."""
    matches = list(VERDICT_RE.finditer(text))
    if matches:
        verdict = matches[-1].group(1).upper()
        reason = ""
        start = matches[-1].start()
        brace = text.rfind("{", 0, start + 1)
        if brace != -1:
            try:
                obj = json.loads(_balanced_object(text, brace))
                reason = str(obj.get("reason") or "")
            except json.JSONDecodeError:
                pass
        return verdict, reason

    last = None
    for match in re.finditer(r"\b(SAFE|UNSAFE)\b", text.upper()):
        last = match.group(1)
    return last, ""


def _balanced_object(text: str, start: int) -> str:
    depth = 0
    for index, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:]


@dataclass(frozen=True)
class AuditCase:
    task_id: str
    name: str
    expected: str
    origin: str
    prompt: str
    code: str
    public_passed: int
    public_total: int
    actually_safe: bool
    violation: str | None


def review_prompt(case: AuditCase) -> str:
    return (
        f"{case.prompt}\n\n"
        "## What you are reviewing\n\n"
        "A colleague submitted the module below. It has already been run against "
        f"the public self-check for this task and passed {case.public_passed}/"
        f"{case.public_total} scenarios (normal delivery, redelivery after a lost "
        "acknowledgement, and each disclosed remote-call outcome). You are doing "
        "the review a senior engineer would do before merging: given the fault "
        "model in the contract above, is this module crash-safe?\n\n"
        "Reply with one JSON object and nothing else:\n"
        '{"verdict": "SAFE" or "UNSAFE", "reason": "one or two sentences"}\n\n'
        "Do not suggest a rewrite. Do not mention tests you have not been shown.\n\n"
        f"```python\n{case.code.rstrip()}\n```\n"
    )


def build_case(task: TaskBundle, source: SolutionSource, expected: str) -> AuditCase:
    report = grade(task, source, include_counterexample=False)
    name = source.origin.replace("\\", "/").rsplit("/", 1)[-1]
    return AuditCase(
        task_id=task.task_id,
        name=name,
        expected=expected,
        origin=source.origin,
        prompt=task.prompt,
        code=without_author_notes(source.source),
        public_passed=report.public_passed,
        public_total=report.public_total,
        actually_safe=bool(report.hidden_passed),
        violation=(report.violations[0] if report.violations else None),
    )


def probe_cases() -> list[AuditCase]:
    by_id = {task.task_id: task for task in discover_tasks()}
    cases: list[AuditCase] = []
    for task_id, filename, expected in PROBE:
        task = by_id[task_id]
        if filename == "reference.py":
            source = task.reference()
        else:
            source = next(
                s for s in task.broken() if s.origin.replace("\\", "/").endswith(filename)
            )
        cases.append(build_case(task, source, expected))
    return cases
