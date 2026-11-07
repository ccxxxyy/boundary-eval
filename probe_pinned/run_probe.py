"""Probe: does code written for a pinned environment actually run in it?

    python probe_pinned/run_probe.py --set bailian --model kimi-k3.1-pro
    python probe_pinned/run_probe.py --check-references

Each item states the project's lock file. The model writes the module; the
hidden tests then run twice, in a real virtualenv built from that lock and in
one with current releases. The column that matters is "passes on current,
fails on the lock": code that works on a fresh developer machine and breaks
where it is deployed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from faultline.llm import LLMError  # noqa: E402
from faultline.run_eval import build_client, extract_module, load_config  # noqa: E402

ITEMS = HERE / "items"
ENVS = HERE / "envs"
OUT = HERE / "results"
TOOLING = {"pytest", "iniconfig", "pluggy", "pygments", "colorama", "packaging"}

REGISTRY = {
    "p01_pydantic_order": ("pydantic1", "parse_order"),
    "p02_pandas_report": ("pandas15", "category_counts"),
    "p03_marshmallow_signup": ("marsh2", "load_signup"),
    "p04_packaging_versions": ("packaging21", "stable_versions"),
    "p05_sqlalchemy_users": ("sqla14", "get_or_create_user"),
    "h01_partner_shipments": ("py39", "parse_shipment"),
    "h02_sales_rollup": ("pandas15", "region_totals"),
    "h03_log_latency": ("py39", "parse_line"),
}

SYSTEM = (
    "You are an experienced backend engineer writing production Python. "
    "Reply with one complete Python module inside a single ```python code block. "
    "Do not include tests."
)


def python_of(env: str) -> str:
    return str(ENVS / env / "Scripts" / "python.exe")


def lock_text(item: str) -> str:
    path = ITEMS / item / "lock.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    env = REGISTRY[item][0]
    frozen = subprocess.run(
        ["uv", "pip", "freeze", "-p", python_of(env)], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    keep = [line for line in frozen if line.split("==")[0].lower() not in TOOLING]
    if item == "p04_packaging_versions":
        keep = [line for line in frozen if line.split("==")[0].lower() in {"packaging", "pyparsing"}]
    text = "python==3.11\n" + "\n".join(sorted(keep, key=str.lower)) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def build_prompt(item: str) -> str:
    context = ITEMS / item / "context.md"
    if context.exists():
        return (
            (ITEMS / item / "prompt.md").read_text(encoding="utf-8").strip()
            + "\n\n## Where this runs\n\n"
            + context.read_text(encoding="utf-8").strip()
            + "\n"
        )
    return (
        (ITEMS / item / "prompt.md").read_text(encoding="utf-8").strip()
        + "\n\n## Where this runs\n\n"
        "This module is deployed into a production environment pinned by the "
        "project's lock file. It will run there, against exactly these versions:\n\n"
        f"```\n{lock_text(item).strip()}\n```\n"
    )


def run_tests(item: str, env: str, solution: Path) -> tuple[bool, str]:
    environ = {
        **os.environ,
        "SOLUTION_PATH": str(solution),
        "PYTHONPATH": str(ITEMS),
        "PYTHONWARNINGS": "ignore",
    }
    try:
        done = subprocess.run(
            [python_of(env), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x",
             str(ITEMS / item / "test_hidden.py")],
            capture_output=True, text=True, env=environ, timeout=120, cwd=str(ITEMS),
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    text = done.stdout + done.stderr
    return done.returncode == 0, _first_error(text)


def _first_error(text: str) -> str:
    for pattern in (r"^E\s+(\w+(?:Error|Exception|Warning)\b.*)$", r"^(\w+Error: .*)$", r"^E\s+(.*)$"):
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(1)[:200]
    tail = [line for line in text.splitlines() if line.strip()]
    return tail[-1][:200] if tail else ""


@dataclass
class Row:
    item: str
    model: str
    seed: int
    pinned_pass: bool
    latest_pass: bool
    pinned_error: str
    latest_error: str
    load_error: str | None
    completion_tokens: int


def check_references() -> int:
    bad = 0
    for item, (env, _) in REGISTRY.items():
        if not item.startswith("h"):
            continue
        ref = ITEMS / item / "reference.py"
        pinned, err = run_tests(item, env, ref)
        latest, lerr = run_tests(item, "latest", ref)
        print(f"{item:<26} pinned={'pass' if pinned else 'FAIL'}  latest={'pass' if latest else 'fail'}  {err or lerr}")
        bad += 0 if pinned else 1
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", dest="model_set", default="bailian")
    parser.add_argument("--model", action="append")
    parser.add_argument("--item", action="append")
    parser.add_argument("--seeds", type=int, nargs="+", default=[1])
    parser.add_argument("--check-references", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.check_references:
        return check_references()

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    models = [{"id": m, "label": m} for m in args.model] if args.model else group["models"]
    client = build_client(group, group.get("provider", "openrouter"), False)
    items = args.item or list(REGISTRY)

    OUT.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else OUT / f"probe_{args.model_set}.jsonl"
    rows: list[Row] = []
    for item in items:
        env, entry = REGISTRY[item]
        for model in models:
            for seed in args.seeds:
                print(f"{item:<26} {model['id']:<24} seed={seed} calling...", flush=True)
                load_error = None
                tokens = 0
                code = None
                try:
                    done = client.complete(
                        model=model["id"],
                        messages=[{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": build_prompt(item)}],
                        temperature=defaults.get("temperature", 0.0),
                        max_tokens=int(defaults.get("max_tokens", 16000)),
                        seed=seed,
                        reasoning_effort=model.get("reasoning_effort"),
                    )
                    tokens = done.completion_tokens
                    code = extract_module(done.text, entry)
                    if code is None:
                        load_error = f"no module (finish_reason={done.finish_reason})"
                except LLMError as exc:
                    load_error = f"api error: {exc}"[:300]

                if code is None:
                    row = Row(item, model["id"], seed, False, False, "", "", load_error, tokens)
                else:
                    path = OUT / "solutions" / item / model["id"].replace("/", "__") / f"seed{seed}.py"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(code + "\n", encoding="utf-8")
                    pinned, perr = run_tests(item, env, path)
                    latest, lerr = run_tests(item, "latest", path)
                    row = Row(item, model["id"], seed, pinned, latest, perr, lerr, None, tokens)
                rows.append(row)
                status = (
                    "unusable" if row.load_error
                    else "pass" if row.pinned_pass
                    else "FAIL (works on latest)" if row.latest_pass
                    else "FAIL"
                )
                print(f"{item:<26} {model['id']:<24} seed={seed} {status}  {row.pinned_error or row.load_error or ''}", flush=True)
                with out.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")

    usable = [r for r in rows if not r.load_error]
    print()
    print(f"usable {len(usable)}/{len(rows)}")
    print(f"pass on pinned env: {sum(r.pinned_pass for r in usable)}/{len(usable)}")
    print(f"fail on pinned env but pass on latest: {sum((not r.pinned_pass) and r.latest_pass for r in usable)}/{len(usable)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
