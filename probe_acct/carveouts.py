"""More 2024 CSRC / exchange carve-outs: share source, plan already filed, ST dual gates.

    python probe_acct/carveouts.py --set bailian --model deepseek-v4.1-flash --out probe_acct/results/carveouts.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from faultline.llm import LLMError  # noqa: E402
from faultline.run_eval import build_client, load_config  # noqa: E402

SYSTEM = (
    "你是中国证券律师。只依据题目指定时点有效的证监会令第224号和2024年4月"
    "沪深交易所股票上市规则作答。只输出 JSON。"
)


def extract(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    raw = blocks[-1] if blocks else text.strip()
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)


QUESTIONS = [
    {
        "id": "q_source",
        "basis": "第224号第2条第2–3款、第9、12、15、18、21、23条",
        "answer": {
            "a": "否",
            "b": "否",
            "c": "是",
            "d": "是",
            "e": "否",
            "f": "是",
            "g": "否",
            "h": "是",
        },
        "prompt": """时点：2024年12月，证监会令第224号。下列判断题只答“是”或“否”。

a. 大股东减持的股份全部是其通过证券交易所集中竞价买入的（不是IPO老股、也不是再融资取得）。是否必须在首次卖出前十五个交易日披露减持计划？
b. 同上，该部分股份通过集中竞价减持，三个月内数量占公司股份总数1.2%。是否因超过“三个月1%”而被禁止？
c. 同上来源的股份，大股东拟融券卖出本公司股份。是否被禁止？
d. 控股股东已按办法第九条披露减持计划后，计划实施期间公司出现破净。其能否继续按已披露计划通过大宗交易减持？
e. 公司披露无控股股东、无实际控制人。持股4%的第一大股东，因公司分红不达标，是否被禁止集中竞价或大宗交易减持？
f. 公司披露无控股股东、无实际控制人。持股8%的第一大股东，因公司分红不达标，是否被禁止集中竞价或大宗交易减持？
g. 人民法院通过集中竞价强制执行大股东股份。是否必须先按第九条提前十五个交易日披露减持计划？
h. 大股东与一致行动人解除一致行动关系后的第三个月，相关方是否仍应共同遵守办法关于大股东减持的规定？

输出 ```json：{"a":"是或否",...,"h":"..."}""",
    },
    {
        "id": "q_st",
        "basis": "2024年4月上市规则：现金分红ST双门槛；资金占用2亿或净资产30%；两年造假3亿且20%",
        "answer": {
            "a": "触及",
            "b": "不触及",
            "c": "不触及",
            "d": "不触及",
            "e": "不触及",
            "f": "触及",
            "g": "不触及",
            "h": "触及",
            "i": "不触及",
            "j": "触及",
        },
        "prompt": """时点：适用2024年4月修订后的沪深交易所股票上市规则（分红ST以2024年度为第一个会计年度）。判断是否“触及”题述指标。

现金分红其他风险警示（ST）：最近一个会计年度净利润为正，且合并报表和母公司报表年末未分配利润均为正；并且最近三个会计年度累计现金分红低于同期年均净利润的30%，且累计分红金额低于5000万元（创业板为3000万元）。须同时满足利润门槛和两个分红门槛。

a. 沪市主板。净利润为正，合并与母公司未分配利润均为正。三年累计现金分红4000万元，三年年均净利润2亿元。
b. 沪市主板。同上正利润、两张未分配利润为正。三年累计现金分红5500万元，三年年均净利润2亿元。
c. 沪市主板。同上正利润、两张未分配利润为正。三年累计现金分红4000万元，三年年均净利润1亿元。
d. 沪市主板。净利润为正，合并未分配利润为正，但母公司年末未分配利润为负。三年累计现金分红0，年均净利润2亿元。
e. 创业板。净利润为正，两张未分配利润为正。三年累计现金分红3500万元，三年年均净利润2亿元。
f. 创业板。净利润为正，两张未分配利润为正。三年累计现金分红2500万元，三年年均净利润2亿元。

资金占用规范类退市门槛（余额达到2亿元以上，或者占最近一期经审计净资产绝对值30%以上；本题只问是否已经达到金额/比例门槛，不讨论是否已责令改正）：
g. 非经营性占用余额1.8亿元，最近一期经审计净资产10亿元。
h. 非经营性占用余额1.8亿元，最近一期经审计净资产5亿元。

两年财务造假重大违法退市（连续两年虚假记载金额达到3亿元以上且占比超过20%）：
i. 连续两年虚假记载金额合计2.8亿元，占比25%。
j. 连续两年虚假记载金额合计3.2亿元，占比22%。

输出 ```json：{"a":"触及或不触及",...,"j":"..."}""",
    },
]


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", str(value))


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
    save_root = HERE / "results" / "carveout_answers"
    save_root.mkdir(parents=True, exist_ok=True)

    for model in args.model:
        print(f"\n#### {model}", flush=True)
        grand_ok = grand_total = 0
        for q in QUESTIONS:
            row = {"model": model, "q": q["id"], "error": None, "items": {}}
            try:
                done = client.complete(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": q["prompt"]},
                    ],
                    temperature=defaults.get("temperature", 0.0),
                    max_tokens=int(defaults.get("max_tokens", 16000)),
                    seed=1,
                    reasoning_effort=None,
                )
                (save_root / f"{q['id']}_{model.replace('/', '__')}.md").write_text(
                    done.text, encoding="utf-8"
                )
                got = extract(done.text)
                for key, want in q["answer"].items():
                    ok = _norm(got.get(key)) == _norm(want)
                    row["items"][key] = {"got": got.get(key), "want": want, "ok": ok}
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_ok = sum(i["ok"] for i in row["items"].values())
            n = len(q["answer"])
            grand_ok += n_ok
            grand_total += n
            wrong = {
                k: (i["got"], i["want"])
                for k, i in row["items"].items()
                if not i["ok"]
            }
            print(
                f"  {q['id']:<12} {row['error'] or f'{n_ok}/{n}'}  错:{wrong}",
                flush=True,
            )
        print(f"  TOTAL {grand_ok}/{grand_total}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
