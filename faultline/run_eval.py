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

from .gemini import GeminiClient
from .llm import CachedClient, LLMError
from .loader import TaskBundle, discover_tasks, load_task
from .openrouter import Completion, OpenRouterClient
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
# A block the model started and never closed, which is what truncated output
# looks like. Only consulted when no properly closed block is usable.
UNTERMINATED_BLOCK = re.compile(r"```(?:python|py)?[ \t]*\n(.*)\Z", re.DOTALL)


@dataclass
class RoundRecord:
    """One attempt by the model, graded.

    Recorded per round because the headline question is not only whether a
    model eventually gets there. It is how often it hands over code that passes
    its own self-check and is still unsafe - which is what a reviewer would
    have seen, and would have approved.
    """

    index: int
    public_passed: int
    public_total: int
    public_clean: bool
    crash_safe: bool
    load_error: str | None = None


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
    rounds: list[RoundRecord] = field(default_factory=list)
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


def extract_module(text: str, entrypoint: str) -> str | None:
    """Pull the candidate module out of a chat response.

    Models routinely include more than one code block - a fragment being
    explained, a diff, a usage example - so picking the longest one is not
    enough. Preferring a block that both compiles and defines the requested
    function keeps a formatting quirk from being scored as a crash-safety
    failure, which would be measuring the wrong thing.
    """
    candidates = [block.strip() for block in CODE_BLOCK.findall(text)]
    truncated = UNTERMINATED_BLOCK.search(text)
    if truncated:
        candidates.append(truncated.group(1).strip())
    if not candidates and f"def {entrypoint}" in text:
        candidates.append(text.strip())

    best: tuple[tuple[int, int, int], str] | None = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            compile(candidate, "<candidate>", "exec")
            compiles = 1
        except SyntaxError:
            compiles = 0
        defines = 1 if f"def {entrypoint}" in candidate else 0
        rank = (compiles + defines, defines, len(candidate))
        if best is None or rank > best[0]:
            best = (rank, candidate)

    return best[1] if best else None


def solution_path(task_id: str, model: str, seed: int, attempt: int) -> Path:
    safe_model = model.replace("/", "__").replace(":", "_")
    directory = RESULTS_DIR / "solutions" / task_id / safe_model
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"seed{seed}_r{attempt}.py"


CLIENTS: dict[str, type[CachedClient]] = {
    "openrouter": OpenRouterClient,
    "gemini": GeminiClient,
}


def run_one(
    client: CachedClient,
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
    rounds: list[RoundRecord] = []

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
        except LLMError as exc:
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
                rounds=rounds,
                load_error=f"api error: {exc}",
            )

        totals["prompt"] += completion.prompt_tokens
        totals["completion"] += completion.completion_tokens
        totals["cost"] += completion.cost_usd
        all_cached = all_cached and completion.cached

        code = extract_module(completion.text, getattr(task.module, "ENTRYPOINT", "handle"))
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
            rounds.append(
                RoundRecord(
                    index=attempt,
                    public_passed=0,
                    public_total=public_total,
                    public_clean=False,
                    crash_safe=False,
                    load_error=report["load_error"],
                )
            )
            break

        path = solution_path(task.task_id, model["id"], seed, attempt)
        path.write_text(code + "\n", encoding="utf-8")
        report = grade_in_subprocess(task.directory, path)

        public_ok = (
            report.get("load_error") is None
            and report["public_scenarios_passed"] == report["public_scenarios_total"]
        )
        rounds.append(
            RoundRecord(
                index=attempt,
                public_passed=int(report.get("public_scenarios_passed", 0)),
                public_total=int(report.get("public_scenarios_total", public_total)),
                public_clean=public_ok,
                crash_safe=bool(report.get("crash_safe")),
                load_error=report.get("load_error"),
            )
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
        rounds=rounds,
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


def _looked_done_but_was_not(record: RunRecord) -> bool:
    """Did the model, at some point, hand over code that passed every public
    scenario and was not crash-safe? That is the state a reviewer would have
    approved, so it is the number the eval is really about."""
    return any(r.public_clean and not r.crash_safe for r in record.rounds)


def _unusable(record: RunRecord) -> bool:
    """No gradable module came back - truncated output, a refusal, a syntax
    error. Reported separately from unsafe, because scoring a formatting
    problem as a crash-safety failure would overstate the finding."""
    return record.load_error is not None


def summarise(records: list[RunRecord]) -> str:
    by_model: dict[str, list[RunRecord]] = {}
    for record in records:
        by_model.setdefault(record.label, []).append(record)

    width = max((len(label) for label in by_model), default=5)
    header = (
        f"{'model'.ljust(width)}  first try  after repair  "
        f"passed own tests but unsafe  unusable  cost"
    )
    lines = [header, "-" * len(header)]
    for label, group in by_model.items():
        total = len(group)
        gradable = [r for r in group if not _unusable(r)]
        first = sum(1 for r in gradable if r.rounds and r.rounds[0].crash_safe)
        final = sum(1 for r in gradable if r.crash_safe)
        fooled = sum(1 for r in group if _looked_done_but_was_not(r))
        cost = sum(r.cost_usd for r in group)
        n = len(gradable)
        lines.append(
            f"{label.ljust(width)}  {first:>3}/{n:<6} {final:>8}/{n:<5} "
            f"{fooled:>20}/{total:<6} {total - n:>6}    ${cost:.4f}"
        )

    total = len(records)
    fooled = sum(1 for r in records if _looked_done_but_was_not(r))
    unsafe = sum(1 for r in records if not _unusable(r) and not r.crash_safe)
    lines.append("")
    lines.append(
        f"{unsafe} of {total} runs ended with code that is not crash-safe, after being shown "
        "its own failing tests and given a chance to fix them"
    )
    lines.append(
        f"{fooled} of {total} runs produced code that passed every public scenario and was "
        "still not crash-safe"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    model_sets = [k for k in config if k != "defaults"]
    parser.add_argument("--set", dest="model_set", default="dev", choices=model_sets)
    parser.add_argument("--model", action="append", help="override: an explicit model slug")
    parser.add_argument(
        "--provider",
        default=None,
        choices=sorted(CLIENTS),
        help="which API to call; defaults to the model set's own provider",
    )
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
    group = config[args.model_set]
    entries = group["models"] if isinstance(group, dict) else group
    models = [{"id": m, "label": m} for m in args.model] if args.model else entries
    tasks = [load_task(t) for t in args.task] if args.task else discover_tasks()

    provider = args.provider or (
        group.get("provider", "openrouter") if isinstance(group, dict) else "openrouter"
    )
    client = CLIENTS[provider](offline=args.offline)
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
    out = (
        (REPO_ROOT / args.out).resolve()
        if args.out
        else RESULTS_DIR / f"runs_{args.model_set}_{stamp}.jsonl"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    print()
    print(summarise(records))
    print(f"\nwrote {out}")
    if not args.offline:
        print(f"spent ${client.spent_usd:.4f} this run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
