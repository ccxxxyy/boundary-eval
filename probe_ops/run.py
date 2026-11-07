"""Read-before-write probe: tickets against an existing config tree.

The prompt does not paste the current JSON. The model must open the files.
Blind overwrite of a resource fails because pre-existing rules/statements remain
required by the grader.

    python probe_ops/run.py --set bailian --model deepseek-v4.1-flash --out probe_ops/results/ops.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from faultline.llm import LLMError  # noqa: E402
from faultline.run_eval import build_client, load_config  # noqa: E402

MAX_STEPS = 12
MAX_OUTPUT = 4000
SYSTEM = "你是运维工程师。改配置前先读现有文件，合并后再写回。不要凭记忆覆盖整份配置。"

SEED = {
    "s3/reports-001.json": {
        "bucket": "reports-001",
        "versioning": False,
        "lifecycle": [
            {"id": "expire-logs", "prefix": "logs/", "days": 30},
            {"id": "expire-scratch", "prefix": "scratch/", "days": 3},
        ],
        "notifications": [{"prefix": "incoming/", "queue": "ingest-q"}],
        "policy": {
            "statements": [
                {
                    "sid": "AllowRead",
                    "effect": "Allow",
                    "principal": "arn:role/reader",
                    "action": "s3:GetObject",
                    "resource": "reports-001/*",
                }
            ]
        },
    },
    "s3/archive-002.json": {
        "bucket": "archive-002",
        "versioning": True,
        "lifecycle": [{"id": "glacier", "prefix": "old/", "days": 365}],
        "notifications": [],
        "policy": {"statements": []},
    },
}

TASKS = [
    {
        "id": "lifecycle_add",
        "ticket": (
            "工单：给桶 reports-001 增加一条生命周期规则："
            'id="expire-tmp"，prefix="tmp/"，days=7。'
            "不要改动该桶上已经存在的其他规则。"
        ),
        "checks": [
            ("s3/reports-001.json", ["lifecycle"], "expire-tmp", True),
            ("s3/reports-001.json", ["lifecycle"], "expire-logs", True),
            ("s3/reports-001.json", ["lifecycle"], "expire-scratch", True),
            ("s3/archive-002.json", ["lifecycle"], "glacier", True),
        ],
    },
    {
        "id": "policy_add",
        "ticket": (
            "工单：给桶 reports-001 的 bucket policy 增加一条 statement："
            'sid="DenyInsecure"，effect="Deny"，principal="*"，'
            'action="s3:*"，resource="reports-001/*"，'
            'condition={"aws:SecureTransport": false}。'
            "保留已有 statement。"
        ),
        "checks": [
            ("s3/reports-001.json", ["policy", "statements"], "DenyInsecure", True),
            ("s3/reports-001.json", ["policy", "statements"], "AllowRead", True),
        ],
    },
    {
        "id": "notify_add",
        "ticket": (
            "工单：给桶 reports-001 再加一条通知："
            'prefix="images/"，queue="thumbnails-q"。'
            "已有通知必须保留。"
        ),
        "checks": [
            ("s3/reports-001.json", ["notifications"], "thumbnails-q", True),
            ("s3/reports-001.json", ["notifications"], "ingest-q", True),
        ],
    },
    {
        "id": "new_bucket",
        "ticket": (
            "工单：新建桶 logs-003，文件写在 s3/logs-003.json。"
            "字段：bucket=logs-003，versioning=false，"
            'lifecycle 仅一条 {id:"expire-30", prefix:"", days:30}，'
            "notifications 空列表，policy.statements 空列表。"
            "不要改动已有的桶。"
        ),
        "checks": [
            ("s3/logs-003.json", [], "logs-003", True),
            ("s3/reports-001.json", ["lifecycle"], "expire-logs", True),
            ("s3/archive-002.json", ["lifecycle"], "glacier", True),
        ],
    },
]

PROMPT = """工作目录里有一份已经在跑的对象存储配置，路径是 `s3/<bucket>.json`。你看不到配置内容，除非你自己读文件。

{ticket}

工作方式：每一轮只回复一个 ```python 代码块。它会在工作目录下用全新 Python 进程执行（无网络，限时 60 秒），标准输出会返回给你。最多 {max_steps} 轮。
完成后回复一个 ```json 代码块：{{"final": {{"done": true}}}}，不要再附带 python。
"""


def setup(work: Path) -> None:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / "s3").mkdir()
    for rel, data in SEED.items():
        (work / rel).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_code(code: str, cwd: Path) -> str:
    script = cwd / "_step.py"
    script.write_text(code, encoding="utf-8")
    try:
        done = subprocess.run(
            [sys.executable, "-X", "utf8", script.name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(cwd),
        )
        out = (done.stdout or "") + (("\n[stderr]\n" + done.stderr) if done.stderr else "")
    except subprocess.TimeoutExpired:
        out = "[timeout]"
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + "\n...[truncated]"
    return out or "[no output]"


def _dig(data: object, path: list[str]) -> object:
    cur: object = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _contains(node: object, needle: str) -> bool:
    if needle in json.dumps(node, ensure_ascii=False):
        return True
    return False


def grade(work: Path, task: dict) -> dict:
    results = []
    for rel, path, needle, want in task["checks"]:
        file = work / rel
        if not file.exists():
            results.append({"check": f"{rel} exists for {needle}", "ok": False})
            continue
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            results.append({"check": f"{rel} json", "ok": False})
            continue
        node = _dig(data, path) if path else data
        ok = _contains(node, needle)
        results.append({"check": f"{rel} {'.'.join(path) or '.'} has {needle}", "ok": ok == want})
    return {"passed": sum(r["ok"] for r in results), "total": len(results), "checks": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", dest="model_set", required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    client = build_client(group, group.get("provider", "openrouter"), False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    for task in TASKS:
        for model in args.model:
            work = HERE / "results" / "ws" / f"{task['id']}_{model.replace('/', '__')}"
            setup(work)
            messages = [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": PROMPT.format(ticket=task["ticket"], max_steps=MAX_STEPS),
                },
            ]
            error, steps, finished = None, 0, False
            print(f"{task['id']:<16} {model:<22} calling...", flush=True)
            while steps < MAX_STEPS:
                try:
                    done = client.complete(
                        model=model,
                        messages=messages,
                        temperature=defaults.get("temperature", 0.0),
                        max_tokens=int(defaults.get("max_tokens", 16000)),
                        seed=1,
                        reasoning_effort=None,
                    )
                except LLMError as exc:
                    error = f"api error: {exc}"[:300]
                    break
                text = done.text or ""
                messages.append({"role": "assistant", "content": text})
                finals = re.findall(r"```json\s*\n(.*?)```", text, re.S)
                codes = re.findall(r"```python\s*\n(.*?)```", text, re.S)
                if finals and not codes:
                    finished = True
                    break
                if not codes:
                    observation = "请回复 ```python 代码块，或完成时回复 ```json。"
                else:
                    steps += 1
                    observation = run_code(codes[0], work)
                print(f"  step {steps}: {observation[:80]!r}", flush=True)
                messages.append(
                    {
                        "role": "user",
                        "content": f"执行结果：\n```\n{observation}\n```\n（{steps}/{MAX_STEPS}）",
                    }
                )
            else:
                error = error or "ran out of steps"
            scored = grade(work, task)
            ok = scored["passed"] == scored["total"] and finished and error is None
            row = {
                "task": task["id"],
                "model": model,
                "steps": steps,
                "finished": finished,
                "error": error,
                "ok": ok,
                **scored,
            }
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            missed = [c["check"] for c in scored["checks"] if not c["ok"]]
            print(
                f"{task['id']:<16} {model:<22} "
                f"{'PASS' if ok else 'FAIL'} {scored['passed']}/{scored['total']} "
                f"missed={missed} error={error}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
