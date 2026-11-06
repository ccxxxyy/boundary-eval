"""Run the eval: ask models to solve the tasks, then grade what they write.

    # build and debug cheaply
    python -m faultline.run_eval --set dev --seeds 1

    # reporting run
    python -m faultline.run_eval --set frontier

    # replay the shipped responses without spending anything
    python -m faultline.run_eval --set frontier --offline

Each model gets the same thing a developer would get: the task contract, the
list of public scenarios that will be run, and - if any of those fail - the
failures, with a chance to fix them. Only after that does the hidden fault
injection run. Fault-injection output is never fed back to the model, so a
model cannot grind against the grader; it has to get crash safety right from
the specification, which is the whole point.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .loader import TaskBundle, discover_tasks, load_task
from .openrouter import Completion, OpenRouterClient, OpenRouterError
from .sandbox import grade_in_subprocess
from .faults import TIMEOUT_VARIANTS
from .selftest import public_scenarios

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "models.yaml"
RESULTS_DIR = REPO_ROOT / "results"

SYSTEM_PROMPT = (
    "You are an experienced backend engineer writing production Python. "
    "Reply with one complete Python module inside a single ```python code block. "
    "The module must define the requested function. Do not include tests."
)

CODE_BLOCK = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL)


@dataclass
class RunRecord:
    task_id: str
    model: str
    label: str
    seed: int
    repair_rounds_used: int
    crash_safe: bool
    public_passed: int
    public_total: int
    traces_run: int
    violations: list[str] = field(default_factory=list)
    counterexample: str | None = None
    load_error: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = True
    solution_path: str | None = None


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def task_scenarios(task: TaskBundle) -> list[tuple[str, Any]]:
    return public_scenarios(getattr(task.module, "FAULT_VARIANTS", TIMEOUT_VARIANTS))


def public_scenario_list(task: TaskBundle) -> str:
    return "\n".join(f"- {name}" for name, _ in task_scenarios(task))


def build_user_prompt(task: TaskBundle) -> str:
    return (
        f"{task.prompt}\n\n"
        "## How your module will be checked\n\n"
        "A self-check will run your module against these scenarios and report "
        "any failures back to you so you can revise:\n\n"
        f"{public_scenario_list(task)}\n\n"
        "Your module will then be graded against every combination of the "
        "failures listed above, including process crashes at every point where "
        "one is possible. Write for that, not for the self-check.\n"
    )


def extract_module(text: str) -> str | None:
    blocks = CODE_BLOCK.findall(text)
    if blocks:
        return max(blocks, key=len).strip()
    if "def handle" in text:  # model answered with bare code
        return text.strip()
    return None


def solution_path(task_id: str, model: str, seed: int, attempt: int) -> Path:
    safe_model = model.replace("/", "__").replace(":", "_")
    directory = RESULTS_DIR / "solutions" / task_id / safe_model
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"seed{seed}_r{attempt}.py"


def run_one(
    client: OpenRouterClient,
    task: TaskBundle,
    model: dict[str, Any],
    seed: int,
    repair_rounds: int,
    defaults: dict[str, Any],
) -> RunRecord:
    public_total = len(task_scenarios(task))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(task)},
    ]
    totals = {"prompt": 0, "completion": 0, "cost": 0.0}
    all_cached = True
    report: dict[str, Any] = {}
    path: Path | None = None

    for attempt in range(repair_rounds + 1):
        try:
            completion: Completion = client.complete(
                model=model["id"],
                messages=messages,
                temperature=defaults.get("temperature", 0.0),
                max_tokens=defaults.get("max_tokens", 16000),
                seed=seed,
                reasoning_effort=model.get("reasoning_effort"),
            )
        except OpenRouterError as exc:
            return RunRecord(
                task_id=task.task_id,
                model=model["id"],
                label=model.get("label", model["id"]),
                seed=seed,
                repair_rounds_used=attempt,
                crash_safe=False,
                public_passed=0,
                public_total=public_total,
                traces_run=0,
                load_error=f"api error: {exc}",
            )

        totals["prompt"] += completion.prompt_tokens
        totals["completion"] += completion.completion_tokens
        totals["cost"] += completion.cost_usd
        all_cached = all_cached and completion.cached

        code = extract_module(completion.text)
        if code is None:
            report = {
                "load_error": "no python code block in the response",
                "crash_safe": False,
                "public_scenarios_passed": 0,
                "public_scenarios_total": public_total,
                "traces_run": 0,
                "violations": [],
                "counterexample": None,
                "public_results": [],
            }
            break

        path = solution_path(task.task_id, model["id"], seed, attempt)
        path.write_text(code + "\n", encoding="utf-8")
        report = grade_in_subprocess(task.directory, path)

        public_ok = (
            report.get("load_error") is None
            and report["public_scenarios_passed"] == report["public_scenarios_total"]
        )
        if public_ok or attempt == repair_rounds:
            break

        messages.append({"role": "assistant", "content": completion.text})
        messages.append({"role": "user", "content": _repair_message(report)})

    return RunRecord(
        task_id=task.task_id,
        model=model["id"],
        label=model.get("label", model["id"]),
        seed=seed,
        repair_rounds_used=attempt,
        crash_safe=bool(report.get("crash_safe")),
        public_passed=int(report.get("public_scenarios_passed", 0)),
        public_total=int(report.get("public_scenarios_total", public_total)),
        traces_run=int(report.get("traces_run", 0)),
        violations=list(report.get("violations") or []),
        counterexample=report.get("counterexample"),
        load_error=report.get("load_error"),
        prompt_tokens=totals["prompt"],
        completion_tokens=totals["completion"],
        cost_usd=round(totals["cost"], 6),
        cached=all_cached,
        solution_path=str(path.relative_to(REPO_ROOT)) if path else None,
    )


def _repair_message(report: dict[str, Any]) -> str:
    if report.get("load_error"):
        return (
            f"Your module could not be loaded: {report['load_error']}\n\n"
            "Reply with a corrected complete module in a single ```python block."
        )
    lines = ["Your module failed part of the self-check:", ""]
    for outcome in report.get("public_results", []):
        marker = "PASS" if outcome["passed"] else "FAIL"
        lines.append(f"[{marker}] {outcome['name']}")
        for violation in outcome["violations"]:
            lines.append(f"         {violation}")
    lines.append("")
    lines.append("Reply with a corrected complete module in a single ```python block.")
    return "\n".join(lines)


def summarise(records: list[RunRecord]) -> str:
    by_model: dict[str, list[RunRecord]] = {}
    for record in records:
        by_model.setdefault(record.label, []).append(record)

    width = max((len(label) for label in by_model), default=5)
    lines = [f"{'model'.ljust(width)}  crash-safe   public   cost"]
    for label, group in by_model.items():
        safe = sum(1 for r in group if r.crash_safe)
        public = sum(1 for r in group if r.public_passed == r.public_total and not r.load_error)
        cost = sum(r.cost_usd for r in group)
        lines.append(
            f"{label.ljust(width)}  {safe:>3}/{len(group):<7} {public:>3}/{len(group):<5} "
            f"${cost:.4f}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="model_set", default="dev", choices=["dev", "frontier"])
    parser.add_argument("--model", action="append", help="override: an explicit model slug")
    parser.add_argument("--task", action="append", help="task directory; repeatable")
    parser.add_argument("--seeds", type=int, nargs="+", default=None)
    parser.add_argument("--repair-rounds", type=int, default=None)
    parser.add_argument("--offline", action="store_true", help="cached responses only, no spending")
    parser.add_argument("--out", default=None, help="jsonl output path")
    args = parser.parse_args(argv)

    defaults = config.get("defaults", {})
    seeds = args.seeds or defaults.get("seeds", [1])
    repair_rounds = (
        args.repair_rounds if args.repair_rounds is not None else defaults.get("repair_rounds", 2)
    )
    models = (
        [{"id": m, "label": m} for m in args.model]
        if args.model
        else config[args.model_set]
    )
    tasks = [load_task(t) for t in args.task] if args.task else discover_tasks()

    client = OpenRouterClient(offline=args.offline)
    records: list[RunRecord] = []

    for task in tasks:
        for model in models:
            for seed in seeds:
                record = run_one(client, task, model, seed, repair_rounds, defaults)
                records.append(record)
                status = (
                    "LOAD ERROR"
                    if record.load_error
                    else ("crash-safe" if record.crash_safe else "UNSAFE")
                )
                print(
                    f"{record.task_id}  {record.label:<22} seed={seed}  "
                    f"public={record.public_passed}/{record.public_total}  {status}"
                )
                sys.stdout.flush()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else RESULTS_DIR / f"runs_{args.model_set}_{stamp}.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    print()
    print(summarise(records))
    print(f"\nwrote {out.relative_to(REPO_ROOT)}")
    if not args.offline:
        print(f"spent ${client.spent_usd:.4f} this run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
