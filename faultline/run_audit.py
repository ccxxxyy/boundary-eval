"""Ask models to review code that already passes its tests.

    python -m faultline.run_audit --set gemini --seeds 1 --out results/audit_probe.jsonl

This is a different question from `run_eval`. `run_eval` asks the model to
write a handler. This asks it to look at a handler a colleague already wrote,
which has already passed the public self-check, and say whether it is
crash-safe. The cases that matter are the known-broken solutions that pass
every public scenario: if the model calls those SAFE, it is making the same
mistake a reviewer makes when they merge the PR.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import AuditCase, parse_verdict, probe_cases, review_prompt
from .llm import LLMError
from .run_eval import (
    CLIENTS,
    RESULTS_DIR,
    REPO_ROOT,
    build_client,
    load_config,
)

SYSTEM = (
    "You are reviewing a production Python change. "
    "Reply with one JSON object: "
    '{"verdict": "SAFE" or "UNSAFE", "reason": "..."}. '
    "No other prose."
)


@dataclass
class AuditRecord:
    task_id: str
    name: str
    expected: str
    actually_safe: bool
    model: str
    label: str
    seed: int
    verdict: str | None
    reason: str
    load_error: str | None
    approved_but_unsafe: bool
    rejected_but_safe: bool
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


def run_one(client: Any, case: AuditCase, model: dict[str, Any], seed: int,
            defaults: dict[str, Any]) -> AuditRecord:
    try:
        completion = client.complete(
            model=model["id"],
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": review_prompt(case)},
            ],
            temperature=defaults.get("temperature", 0.0),
            max_tokens=min(int(defaults.get("max_tokens", 8000)), 4096),
            seed=seed,
            reasoning_effort=model.get("reasoning_effort"),
        )
        load_error = None
        verdict, reason = parse_verdict(completion.text)
        if verdict is None:
            load_error = "no SAFE/UNSAFE verdict in the response"
        prompt_tokens = completion.prompt_tokens
        completion_tokens = completion.completion_tokens
        cost = completion.cost_usd
    except LLMError as exc:
        load_error = f"api error: {exc}"
        verdict, reason = None, ""
        prompt_tokens = completion_tokens = 0
        cost = 0.0

    approved = verdict == "SAFE" and not case.actually_safe
    rejected = verdict == "UNSAFE" and case.actually_safe
    return AuditRecord(
        task_id=case.task_id,
        name=case.name,
        expected=case.expected,
        actually_safe=case.actually_safe,
        model=model["id"],
        label=model.get("label", model["id"]),
        seed=seed,
        verdict=verdict,
        reason=reason,
        load_error=load_error,
        approved_but_unsafe=approved,
        rejected_but_safe=rejected,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=round(cost, 6),
    )


def summarise(records: list[AuditRecord]) -> str:
    by_model: dict[str, list[AuditRecord]] = {}
    for record in records:
        by_model.setdefault(record.label, []).append(record)

    width = max((len(label) for label in by_model), default=5)
    header = (
        f"{'model'.ljust(width)}  correct  approved unsafe code  "
        f"rejected safe code  unusable"
    )
    lines = [header, "-" * len(header)]
    for label, group in by_model.items():
        total = len(group)
        usable = [r for r in group if r.load_error is None and r.verdict]
        correct = sum(1 for r in usable if r.verdict == r.expected)
        approved = sum(1 for r in group if r.approved_but_unsafe)
        rejected = sum(1 for r in group if r.rejected_but_safe)
        unusable = total - len(usable)
        n = len(usable)
        lines.append(
            f"{label.ljust(width)}  {correct:>3}/{n:<4} {approved:>20}/{total:<4} "
            f"{rejected:>18}/{total:<4} {unusable:>8}"
        )

    approved = sum(1 for r in records if r.approved_but_unsafe)
    lines.append("")
    lines.append(
        f"{approved} of {len(records)} reviews approved code that passes its tests "
        "and is not crash-safe"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    model_sets = [k for k in config if k != "defaults"]
    parser.add_argument("--set", dest="model_set", default="gemini", choices=model_sets)
    parser.add_argument("--model", action="append")
    parser.add_argument("--provider", default=None, choices=sorted(CLIENTS))
    parser.add_argument("--seeds", type=int, nargs="+", default=None)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    group = config[args.model_set]
    defaults = {
        **config.get("defaults", {}),
        **(group.get("defaults", {}) if isinstance(group, dict) else {}),
    }
    seeds = args.seeds or [1]
    entries = group["models"] if isinstance(group, dict) else group
    models = [{"id": m, "label": m} for m in args.model] if args.model else entries
    provider = args.provider or (
        group.get("provider", "openrouter") if isinstance(group, dict) else "openrouter"
    )
    client = build_client(group, provider, args.offline)
    cases = probe_cases()

    records: list[AuditRecord] = []
    for case in cases:
        for model in models:
            for seed in seeds:
                record = run_one(client, case, model, seed, defaults)
                records.append(record)
                mark = (
                    "unusable"
                    if record.load_error
                    else (
                        "APPROVED UNSAFE"
                        if record.approved_but_unsafe
                        else (
                            "rejected safe"
                            if record.rejected_but_safe
                            else "correct"
                        )
                    )
                )
                print(
                    f"{case.task_id}  {case.name:<42} {record.label:<22} "
                    f"said={record.verdict or '-':<6} truth={case.expected:<6}  {mark}"
                )
                sys.stdout.flush()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        (REPO_ROOT / args.out).resolve()
        if args.out
        else RESULTS_DIR / f"audit_{args.model_set}_{stamp}.jsonl"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    print()
    print(summarise(records))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
