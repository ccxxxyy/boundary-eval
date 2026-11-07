"""Annual-report probe: full report text + 8 fixed analyst questions, graded against answers.py.

    python probe_fin/run_fin.py --set bailian --model kimi-k3.1-pro
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

from answers import correct, truth  # noqa: E402
from faultline.llm import LLMError  # noqa: E402
from faultline.run_eval import build_client, load_config  # noqa: E402

QUESTIONS = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
NAMES = {"600519": "贵州茅台", "000333": "美的集团", "300750": "宁德时代"}
SYSTEM = "你是严谨的证券分析师。只依据提供的年报原文作答。"


def build_prompt(code: str) -> str:
    report = (HERE / "reports" / f"{code}.txt").read_text(encoding="utf-8")
    qs = "\n".join(f"- {q['id']}: {q['text']}" for q in QUESTIONS)
    keys = ", ".join(f'"{q["id"]}": 数值' for q in QUESTIONS)
    return (
        f"下面是{NAMES[code]}（{code}）2025年年度报告全文（由PDF转为文本，每页以“=== 第N页 ===”开头）。\n\n"
        f"<年报>\n{report}\n</年报>\n\n"
        "请根据这份年报回答下列问题。除非题目另有说明，均为合并报表口径、2025年度/2025年末数据。"
        "注意报告中的金额单位（元/千元/万元等），答案一律换算为题目要求的单位。\n\n"
        f"{qs}\n\n"
        "最后输出一个 ```json 代码块，格式为 {" + keys + "}，数值为纯数字（不要千分位逗号、不要单位、不要百分号）。"
    )


def extract(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    if not blocks:
        raise ValueError("no json block")
    return json.loads(blocks[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", dest="model_set", required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--code", action="append", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    client = build_client(group, group.get("provider", "openrouter"), False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = right = 0
    for code in args.code or list(NAMES):
        want = truth(code)
        for model in args.model:
            print(f"{code} {model:<24} calling...", flush=True)
            row = {"code": code, "model": model, "error": None, "results": {}}
            try:
                done = client.complete(
                    model=model,
                    messages=[{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": build_prompt(code)}],
                    temperature=defaults.get("temperature", 0.0),
                    max_tokens=int(defaults.get("max_tokens", 16000)),
                    seed=1, reasoning_effort=None,
                )
                save = HERE / "results" / "answers" / code
                save.mkdir(parents=True, exist_ok=True)
                (save / f"{model.replace('/', '__')}.md").write_text(done.text, encoding="utf-8")
                got = extract(done.text)
                for q in QUESTIONS:
                    value = got.get(q["id"])
                    try:
                        ok = correct(q["kind"], float(value), want[q["id"]])
                    except (TypeError, ValueError):
                        ok = False
                    row["results"][q["id"]] = {"got": value, "want": round(want[q["id"]], 4), "ok": ok}
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            n_ok = sum(r["ok"] for r in row["results"].values())
            if not row["error"]:
                total += len(QUESTIONS)
                right += n_ok
            wrong = [qid for qid, r in row["results"].items() if not r["ok"]]
            print(f"{code} {model:<24} {row['error'] or f'{n_ok}/{len(QUESTIONS)} correct, wrong: {wrong}'}", flush=True)
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\ntotal correct {right}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
