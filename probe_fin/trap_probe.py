"""Quick trap probe: same reports, but questions that need the *right statement*, not search.

Two traps the plain-extraction set never had:
  t1  母公司（个别报表）口径的资本开支 —— 模型习惯抓合并现金流量表
  t2  合并利润表的“营业总收入” —— 模型习惯抓“其中：营业收入”

    python probe_fin/trap_probe.py --set bailian --model deepseek-v4.1-flash --out probe_fin/results/trap.jsonl
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

NAMES = {"600519": "贵州茅台", "000333": "美的集团", "300750": "宁德时代"}
SYSTEM = "你是严谨的证券分析师。只依据提供的年报原文作答，注意区分合并报表与母公司（个别）报表。"

# Hand-read from each report, with the line where it appears.
TRAPS = [
    {
        "id": "t1_parent_capex",
        "text": ("母公司（本公司个别报表，**不是合并报表**）2025年度现金流量表中"
                 "“购建固定资产、无形资产和其他长期资产支付的现金”，单位：元"
                 "（报表若以千元/万元列示，请换算为元；金额取绝对值，即实际支付金额）。"),
        "kind": "amount",
        "truth": {"600519": 3_104_346_428.46, "000333": 386_032_000.0, "300750": 2_056_300_000.0},
        # 对照合并口径：600519=3,127,594,916.41  000333=11,141,889,000  300750=42,344,558,000
    },
    {
        "id": "t2_total_revenue",
        "text": ("合并利润表中“营业总收入”（注意：是“一、营业总收入”这一行本身，"
                 "不是它下面“其中：营业收入”那一行），2025年度，单位：元。"),
        "kind": "amount",
        "truth": {"600519": 172_054_171_890.91, "000333": 458_502_407_000.0, "300750": 423_701_834_000.0},
        # 对照“其中：营业收入”：600519=168,838,102,514.79  000333=456,451,731,000  300750 两者相等（对照项）
    },
]


def build_prompt(code: str) -> str:
    report = (HERE / "reports" / f"{code}.txt").read_text(encoding="utf-8")
    qs = "\n".join(f"- {t['id']}: {t['text']}" for t in TRAPS)
    keys = ", ".join(f'"{t["id"]}": 数值' for t in TRAPS)
    return (
        f"下面是{NAMES[code]}（{code}）2025年年度报告全文（由PDF转为文本，每页以“=== 第N页 ===”开头）。\n\n"
        f"<年报>\n{report}\n</年报>\n\n"
        "请根据这份年报回答下列问题。注意报告中的金额单位（元/千元/万元等），答案一律换算为元。\n\n"
        f"{qs}\n\n"
        "最后输出一个 ```json 代码块，格式为 {" + keys + "}，数值为纯数字（不要千分位逗号、不要单位）。"
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
        for model in args.model:
            print(f"{code} {model:<22} calling...", flush=True)
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
                save = HERE / "results" / "trap_answers" / code
                save.mkdir(parents=True, exist_ok=True)
                (save / f"{model.replace('/', '__')}.md").write_text(done.text, encoding="utf-8")
                got = extract(done.text)
                for t in TRAPS:
                    want = t["truth"][code]
                    value = got.get(t["id"])
                    try:
                        ok = abs(float(value) - want) <= 0.005 * abs(want)
                    except (TypeError, ValueError):
                        ok = False
                    row["results"][t["id"]] = {"got": value, "want": want, "ok": ok}
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            n_ok = sum(r["ok"] for r in row["results"].values())
            if not row["error"]:
                total += len(TRAPS)
                right += n_ok
            wrong = [qid for qid, r in row["results"].items() if not r["ok"]]
            print(f"{code} {model:<22} {row['error'] or f'{n_ok}/{len(TRAPS)} ok, missed: {wrong}'}", flush=True)
            for qid, r in row["results"].items():
                print(f"    {qid}: got={r['got']} want={r['want']} -> {'OK' if r['ok'] else 'WRONG'}", flush=True)
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\ntotal correct {right}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
