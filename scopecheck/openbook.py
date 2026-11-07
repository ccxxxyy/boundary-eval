"""Open-book version: the governing article text is pasted into every prompt.

If models still misjudge, the failure is application-under-interacting-conditions,
not memorization — which is the defensible, non-gotcha finding the rubric wants.
Article text quoted verbatim from 证监会令第224号 (gov.cn 2024 公报).

    python scopecheck/openbook.py --set bailian --model deepseek-v4.1-flash --out scopecheck/results/openbook.jsonl
    python scopecheck/openbook.py --set gemini  --model gemini-3.5-flash     --out scopecheck/results/openbook.jsonl
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
    "你是中国证券合规专员。下面会给出《上市公司股东减持股份管理暂行办法》的相关条文原文，"
    "请只依据所给条文和事实作答，逐条核对适用范围与但书。只输出要求的 JSON。"
)

LAW = """《上市公司股东减持股份管理暂行办法》（证监会令第224号，2024年5月24日施行）节选：

第二条 上市公司持有百分之五以上股份的股东、实际控制人（以下统称大股东）、董事、监事、高级管理人员减持股份，以及其他股东减持其持有的公司首次公开发行前发行的股份，适用本办法。
　　大股东减持其通过证券交易所集中竞价交易买入的上市公司股份，仅适用本办法第四条至第八条、第十八条、第二十八条至第三十条的规定。

第九条 大股东计划通过证券交易所集中竞价交易或者大宗交易方式减持股份的，应当在首次卖出前十五个交易日向证券交易所报告并披露减持计划。

第十条 存在下列情形之一的，控股股东、实际控制人不得通过证券交易所集中竞价交易或者大宗交易方式减持股份，但已经按照本办法第九条规定披露减持计划，或者中国证监会另有规定的除外：
　　（一）最近三个已披露经审计的年度报告的会计年度未实施现金分红或者累计现金分红金额低于同期年均归属于上市公司股东净利润的百分之三十的，但其中净利润为负的会计年度不纳入计算；
　　（二）最近二十个交易日中，任一日股票收盘价（向后复权）低于最近一个会计年度或者最近一期财务报告期末每股归属于上市公司股东的净资产的。

第十一条 最近二十个交易日中，任一日股票收盘价（向后复权）低于首次公开发行时的股票发行价格的，上市公司首次公开发行时的控股股东、实际控制人及其一致行动人不得通过证券交易所集中竞价交易或者大宗交易方式减持股份，但已经按照本办法第九条规定披露减持计划，或者中国证监会另有规定的除外。
　　前两款规定的主体不具有相关身份后，应当继续遵守本条前两款规定。

第十二条 大股东通过证券交易所集中竞价交易减持股份……三个月内减持股份的总数不得超过公司股份总数的百分之一。

第十五条 股东因司法强制执行……减持股份的，应当根据具体减持方式分别适用本办法的相关规定。大股东所持股份被人民法院通过证券交易所集中竞价交易或者大宗交易方式强制执行的，应当在收到相关执行通知后二个交易日内披露，不适用本办法第九条第一款、第二款的规定。

第二十三条 上市公司披露无控股股东、实际控制人的，第一大股东应当遵守本办法关于控股股东、实际控制人的规定，但是持有上市公司股份低于百分之五的除外。
"""

TASKS = [
    {
        "id": "ob01_loss_year",
        "want": "禁止",
        "basis": "第十条（一）但书：净利润为负年度不纳入",
        "facts": """现任控股股东拟通过集中竞价或大宗交易减持，尚未披露减持计划。最近三个已披露经审计年报：
- 2022年：归母净利润 -8000万元，现金分红 0
- 2023年：归母净利润 1亿元，现金分红 1000万元
- 2024年：归母净利润 1亿元，现金分红 1000万元
最近20个交易日股价均高于每股净资产与发行价。""",
    },
    {
        "id": "ob02_sub5_first",
        "want": "允许",
        "basis": "第二十三条但书：第一大股东持股<5%除外",
        "facts": """公司已披露无控股股东、无实际控制人。持股4%的股东为第一大股东。公司最近三年现金分红不达标（累计分红低于年均归母净利润的30%，且相关年度均盈利）。该股东拟通过集中竞价或大宗交易减持，尚未披露减持计划。问：是否因分红不达标而被禁止以这两种方式减持。""",
    },
    {
        "id": "ob03_plan_filed_break_nav",
        "want": "允许",
        "basis": "第十条但书：已按第九条披露计划的除外",
        "facts": """控股股东已按第九条披露减持计划。计划实施期间公司出现破净（最近20个交易日中任一日向后复权收盘价低于最近一期每股净资产）。其拟继续按已披露计划通过大宗交易减持。不存在证监会另有规定的情形。""",
    },
    {
        "id": "ob04_secondary_lot",
        "want": "允许",
        "basis": "第二条第二款：竞价买入股份不适用第九条",
        "facts": """大股东拟减持的股份全部是其通过证券交易所集中竞价交易买入的（非首发前老股、非配股/增发取得）。尚未披露减持计划，拟于下一交易日集中竞价卖出，数量占公司股份总数0.3%。问：是否仅因未提前十五个交易日披露减持计划而被禁止该卖出。""",
    },
    {
        "id": "ob05_court",
        "want": "允许",
        "basis": "第十五条第二款：司法强制执行不适用第九条第一、二款",
        "facts": """人民法院将通过证券交易所集中竞价强制执行某大股东所持本公司股份。该大股东未提前十五个交易日披露减持计划。问：该强制执行是否仅因缺少该十五日预披露而被禁止。""",
    },
    {
        "id": "ob06_ex_controller",
        "want": "禁止",
        "basis": "第十一条：任一日破发 + 身份丧失仍适用",
        "facts": """某人为公司首次公开发行时的控股股东，上市后已降为持股6%的普通大股东，不再担任控股股东或实际控制人。最近20个交易日里仅有1日向后复权收盘价低于发行价，其余19日高于发行价。其拟通过集中竞价或大宗交易减持，尚未披露减持计划。""",
    },
]


def build_prompt(facts: str) -> str:
    return (
        LAW
        + "\n\n【事实情形】\n"
        + facts
        + "\n\n请判断该减持应为“允许”还是“禁止”，并给出所依据的条款号。"
        '\n“允许”=依所给条文不被禁止；“禁止”=依所给条文被禁止。'
        '\n输出 ```json：{"verdict":"允许或禁止","article":"条款号，如 第十条"}'
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
    args = parser.parse_args()

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    client = build_client(group, group.get("provider", "openrouter"), False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    save = HERE / "results" / "openbook_answers"
    save.mkdir(parents=True, exist_ok=True)

    for model in args.model:
        print(f"\n#### {model}", flush=True)
        n_ok = n_total = 0
        for task in TASKS:
            row = {"model": model, "task": task["id"], "error": None, "ok": False}
            try:
                done = client.complete(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": build_prompt(task["facts"])},
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
                ok = _norm(got.get("verdict")) == _norm(task["want"])
                row.update({"got": got.get("verdict"), "want": task["want"],
                            "article": got.get("article"), "ok": ok})
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_total += 1
            n_ok += int(bool(row.get("ok")))
            print(
                f"  {task['id']:<26} {row.get('error') or ('OK' if row['ok'] else 'WRONG')}"
                f"  got={row.get('got')}/{row.get('article')} want={task['want']}",
                flush=True,
            )
        print(f"  TOTAL {n_ok}/{n_total}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
