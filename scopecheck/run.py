"""Run the eight scope-carveout tasks.

    python scopecheck/run.py --set bailian --model deepseek-v4.1-flash --out scopecheck/results/runs.jsonl
    python scopecheck/run.py --set gemini --model gemini-3.5-flash --out scopecheck/results/runs.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from faultline.llm import LLMError  # noqa: E402
from faultline.run_eval import build_client, load_config  # noqa: E402
from tasks import TASKS  # noqa: E402

SYSTEM = (
    "你是中国证券律师。只依据题目指定时点有效的证监会规章和沪深交易所规则作答。"
    "只输出要求的 JSON。"
)


def extract(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    raw = blocks[-1] if blocks else text.strip()
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", str(value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", dest="model_set", required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--task", action="append", default=None)
    args = parser.parse_args()

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    client = build_client(group, group.get("provider", "openrouter"), False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    save = HERE / "results" / "answers"
    save.mkdir(parents=True, exist_ok=True)
    chosen = [t for t in TASKS if args.task is None or t["id"] in args.task]

    for model in args.model:
        print(f"\n#### {model}", flush=True)
        n_ok = n_total = 0
        for task in chosen:
            row = {"model": model, "task": task["id"], "error": None, "ok": False}
            try:
                done = client.complete(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": task["prompt"]},
                    ],
                    temperature=defaults.get("temperature", 0.0),
                    max_tokens=int(defaults.get("max_tokens", 16000)),
                    seed=1,
                    reasoning_effort=None,
                )
                (save / f"{task['id']}_{model.replace('/', '__')}.md").write_text(
                    done.text, encoding="utf-8"
                )
                got = extract(done.text)
                want = task["want"]["verdict"]
                verdict = _norm(got.get("verdict"))
                ok = verdict == _norm(want)
                row.update({"got": got.get("verdict"), "want": want, "ok": ok})
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_total += 1
            n_ok += int(bool(row.get("ok")))
            mark = "OK" if row.get("ok") else "WRONG"
            print(
                f"  {task['id']:<28} {row.get('error') or mark}  "
                f"got={row.get('got')} want={row.get('want')}",
                flush=True,
            )
        print(f"  TOTAL {n_ok}/{n_total}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
