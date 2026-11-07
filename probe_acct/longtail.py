"""Long-tail China securities-rule application. Answers cited to the 2024 texts.

The prompt gives facts and allowed labels, not the article. Basis is recorded
so a practitioner can audit the key before treating a model miss as a finding.

Sources:
- 证监会令第224号《上市公司股东减持股份管理暂行办法》（2024-05-24）
- 沪深交易所《股票上市规则》（2024年4月修订）财务类/交易类退市

    python probe_acct/longtail.py --set bailian --model deepseek-v4.1-flash --out probe_acct/results/longtail.jsonl
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
    "你是中国证券律师。只依据题目指定时点仍然有效的证监会规章和沪深交易所"
    "股票上市规则作答。不要编造已废止的旧口径。只输出要求的 JSON。"
)

QUESTIONS = [
    {
        "id": "q_reduce",
        "basis": "证监会令第224号 第9–14、18、11条第3款",
        "answer": {
            "a": "禁止",
            "b": "允许",
            "c": "禁止",
            "d": "禁止",
            "e": "允许",
            "f": "禁止",
            "g": "禁止",
            "h": "允许",
        },
        "prompt": """时点：2024年12月。依据当时施行的《上市公司股东减持股份管理暂行办法》（证监会令第224号）。
下列主体拟通过证券交易所**集中竞价或大宗交易**减持。判断该减持在规则下是“允许”还是“禁止”。
（若仅因未满预披露满15个交易日而不能明天就卖，但题目没有说“明天立刻卖”，则预披露本身不构成禁止；本题问的是实体限制：破发/破净/分红/比例/锁定/融券等。未特别声明的，视为尚未披露减持计划。）

a. 某人是该公司**首次公开发行时的控股股东**，上市后已降为持股6%的普通大股东、不再是控股股东或实控人。最近20个交易日里，仅有1日向后复权收盘价低于发行价，其余19日均高于发行价。
b. 持股6%的股东，从来不是控股股东、实控人，也不是IPO时的控股股东。最近20个交易日中有多日收盘价低于最近一期每股净资产（破净）。问：是否因破净而被禁止集中竞价或大宗交易减持。
c. 现任控股股东。最近三个已披露年报年度：2022年归母净利润-8000万元、现金分红0；2023年归母净利润1亿元、现金分红1000万元；2024年归母净利润1亿元、现金分红1000万元。无其他例外。
d. 某投资者刚通过协议转让从大股东处受让股份，过户满3个月，拟减持该受让股份。
e. 大股东拟通过大宗交易在任意三个月内减持占公司股份总数2%的股份（受让方锁定另计，本题只问出让方数量上限）。
f. 大股东拟通过集中竞价在任意三个月内减持占公司股份总数1.2%的股份。
g. 持股8%的大股东拟融券卖出本公司股份。
h. 现任控股股东。最近三个已披露年报年度均盈利且均有现金分红，累计现金分红高于同期年均归母净利润的30%；最近20个交易日收盘价均高于每股净资产和发行价。

输出 ```json：{"a":"允许或禁止", ... "h":"..."}""",
    },
    {
        "id": "q_delist",
        "basis": "2024年4月沪深《股票上市规则》：主板营收3亿/创业板1亿；主板市值5亿/创业板3亿；一年造假2亿且30%",
        "answer": {
            "a": "触及",
            "b": "不触及",
            "c": "触及",
            "d": "不触及",
            "e": "触及",
            "f": "不触及",
            "g": "不触及",
            "h": "触及",
        },
        "prompt": """时点：适用2024年4月修订后的沪深交易所股票上市规则，财务类“利润+营收”组合指标以2024年度为首个适用会计年度。营业收入均为规则要求扣除后的金额。判断下列是否“触及”题述指标（触及/不触及）。

财务类退市风险警示的利润+营收组合：利润总额、净利润、扣非净利润三者孰低为负，且扣除后营业收入低于门槛（主板3亿元，创业板1亿元）。

a. 深市主板。2024年：利润总额-1000万元，净利润+2000万元，扣非净利润+1500万元，扣除后营收2.5亿元。
b. 创业板。同一套数字：利润总额-1000万元，净利润+2000万元，扣非+1500万元，扣除后营收2.5亿元。
c. 深市主板。利润总额+1000万元，净利润-500万元，扣非+2000万元，扣除后营收2.0亿元。
d. 深市主板。利润总额、净利润、扣非均为负，扣除后营收3.2亿元。
e. 沪市主板A股。连续20个交易日每日股票收盘总市值为4.2亿元（问：交易类市值退市指标）。
f. 创业板。连续20个交易日每日股票收盘总市值为4.2亿元（问：交易类市值退市指标）。
g. 仅2024年一年存在虚假记载，造假金额1.8亿元，占当年该科目披露金额的35%（问：是否触及“一年严重造假”重大违法退市标准：金额达到2亿元以上且占比超过30%）。
h. 仅2024年一年存在虚假记载，造假金额2.1亿元，占当年该科目披露金额的32%。

输出 ```json：{"a":"触及或不触及", ... "h":"..."}""",
    },
]


def extract(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    if not blocks:
        raise ValueError("no json block")
    return json.loads(blocks[-1])


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
    save_root = HERE / "results" / "longtail_answers"
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
            print(f"  {q['id']:<12} {row['error'] or f'{n_ok}/{n}'}  错:{wrong}", flush=True)
        print(f"  TOTAL {grand_ok}/{grand_total}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
