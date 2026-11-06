"""The model-facing pipeline, exercised without touching the network.

A canned client stands in for OpenRouter so the repair loop, the code
extraction and the subprocess grading are all covered at no cost. The leakage
test is the important one: if fault-injection output ever reached the model,
the eval would be measuring how well a model can grind against a grader rather
than whether it can reason about crash safety from a specification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline.loader import load_task
from faultline.openrouter import Completion
from faultline.run_eval import extract_module, run_one

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_DIR = REPO_ROOT / "tasks" / "t01_idempotent_charge"
TASK = load_task(TASK_DIR)

MODEL = {"id": "canned/model", "label": "canned"}
DEFAULTS = {"temperature": 0.0, "max_tokens": 4000}


def _as_answer(path: Path) -> str:
    return f"Here you go.\n\n```python\n{path.read_text(encoding='utf-8')}\n```\n"


class CannedClient:
    """Returns prepared answers in order and remembers what it was asked."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, model, messages, **kwargs) -> Completion:
        self.calls.append([dict(m) for m in messages])
        index = min(len(self.calls) - 1, len(self.answers) - 1)
        return Completion(text=self.answers[index], model=model, cached=True)


def test_repair_loop_fixes_a_public_failure() -> None:
    client = CannedClient(
        [
            _as_answer(TASK_DIR / "broken" / "b05_timeout_escapes.py"),
            _as_answer(TASK_DIR / "reference.py"),
        ]
    )
    record = run_one(client, TASK, MODEL, seed=1, repair_rounds=2, defaults=DEFAULTS)

    assert record.repair_rounds_used == 1, "should have taken exactly one repair round"
    assert record.public_passed == record.public_total
    assert record.crash_safe


def test_repair_feedback_never_leaks_fault_injection_output() -> None:
    client = CannedClient(
        [
            _as_answer(TASK_DIR / "broken" / "b05_timeout_escapes.py"),
            _as_answer(TASK_DIR / "reference.py"),
        ]
    )
    run_one(client, TASK, MODEL, seed=1, repair_rounds=2, defaults=DEFAULTS)

    assert len(client.calls) == 2, "expected a second call carrying the repair feedback"
    feedback = client.calls[1][-1]["content"]
    for leak in ("CRASH (", "trace with", "counterexample", "crashes before op", "VIOLATION"):
        assert leak not in feedback, f"repair feedback leaked grader internals: {leak!r}"


def test_solution_that_passes_the_self_check_is_still_graded() -> None:
    """The headline finding in miniature: clean self-check, unsafe code."""
    client = CannedClient([_as_answer(TASK_DIR / "broken" / "b01_fresh_key_per_call.py")])
    record = run_one(client, TASK, MODEL, seed=1, repair_rounds=2, defaults=DEFAULTS)

    assert record.public_passed == record.public_total
    assert record.repair_rounds_used == 0, "no repair should be offered when the self-check passes"
    assert not record.crash_safe
    assert any("charged 2 times" in v for v in record.violations), record.violations
    assert record.counterexample is not None


@pytest.mark.parametrize(
    "answer", ["I cannot help with that.", "```json\n{\"nope\": true}\n```"]
)
def test_unusable_answers_are_recorded_not_raised(answer: str) -> None:
    client = CannedClient([answer])
    record = run_one(client, TASK, MODEL, seed=1, repair_rounds=0, defaults=DEFAULTS)

    assert not record.crash_safe
    assert record.load_error is not None


def test_extraction_prefers_the_block_that_compiles_and_defines_the_entrypoint() -> None:
    """Models explain themselves with fragments. Grading a fragment would
    report a syntax error as a crash-safety failure."""
    response = (
        "The problem is here:\n\n"
        "```python\n    except GatewayTimeout:\n        retry()\n```\n\n"
        "Here is the full module:\n\n"
        "```python\ndef handle_order(**kwargs):\n    return 'ch_1'\n```\n"
    )
    code = extract_module(response, "handle_order")
    assert code is not None
    assert "def handle_order" in code
    compile(code, "<extracted>", "exec")


def test_extraction_recovers_a_truncated_block() -> None:
    """Output cut off by the token limit has no closing fence."""
    response = "```python\ndef handle_order(**kwargs):\n    return 'ch_1'\n"
    code = extract_module(response, "handle_order")
    assert code is not None
    assert "def handle_order" in code


def test_extraction_ignores_non_python_blocks() -> None:
    assert extract_module('```json\n{"a": 1}\n```', "handle_order") is None


def test_recorded_solution_is_written_to_disk() -> None:
    client = CannedClient([_as_answer(TASK_DIR / "reference.py")])
    record = run_one(client, TASK, MODEL, seed=7, repair_rounds=0, defaults=DEFAULTS)

    assert record.solution_path is not None
    assert (REPO_ROOT / record.solution_path).exists()
