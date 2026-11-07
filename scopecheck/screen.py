"""Open-book, high-volume compliance screen.

The full rule text is in every prompt (open-book: this is NOT a memorization
gotcha). The task is realistic compliance work: screen a batch of proposed
share reductions against ALL the rules at once and output, per item, the set of
restrictions that apply. A deterministic reference solver (`evaluate`) encodes
the articles, so every answer is defensible and the grader never false-passes.

The failure we probe is state-tracking at scale: each item needs several
interacting conditions combined correctly, and there are many items, so small
per-item error compounds into near-certain batch failure.

    python scopecheck/screen.py --set gemini --model gemini-3.5-flash --out scopecheck/results/screen.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from faultline.llm import LLMError  # noqa: E402
from faultline.run_eval import build_client, load_config  # noqa: E402

# ---------------------------------------------------------------------------
# Rule text shown to the model (open-book).
# ---------------------------------------------------------------------------
LAW = """《上市公司股东减持股份管理暂行办法》（证监会令第224号，2024年5月24日施行）节选：

第二条 上市公司持有百分之五以上股份的股东、实际控制人（以下统称大股东），以及其他股东减持其持有的公司首次公开发行前发行的股份，适用本办法。
　　大股东减持其通过证券交易所集中竞价交易买入的上市公司股份，仅适用本办法第四条至第八条、第十八条、第二十八条至第三十条的规定（即不适用第九条、第十条、第十一条、第十二条）。

第九条 大股东计划通过集中竞价交易或者大宗交易方式减持股份的，应当在首次卖出的十五个交易日前向证券交易所报告并披露减持计划。

第十条 存在下列情形之一的，控股股东、实际控制人不得通过集中竞价交易或者大宗交易方式减持股份，但已经按照第九条披露减持计划，或者中国证监会另有规定的除外：
　　（一）最近三个已披露经审计年度未实施现金分红，或者累计现金分红金额低于同期年均归母净利润的百分之三十；其中净利润为负的会计年度不纳入计算；
　　（二）最近二十个交易日中任一日股票收盘价（向后复权）低于最近一期每股归母净资产。

第十一条 最近二十个交易日中任一日股票收盘价（向后复权）低于首次公开发行时发行价格的，公司首次公开发行时的控股股东、实际控制人及其一致行动人不得通过集中竞价交易或者大宗交易方式减持股份，但已按第九条披露减持计划，或证监会另有规定的除外。前述主体不再具有相关身份后，应当继续遵守本条规定。

第十二条 大股东通过集中竞价交易减持股份的，在任意连续三个月内减持股份的总数不得超过公司股份总数的百分之一。

第十五条 大股东所持股份被人民法院通过集中竞价或大宗交易方式强制执行的，不适用第九条的预披露要求（但其余限制仍适用）。

第二十三条 上市公司披露无控股股东、实际控制人的，第一大股东应当遵守本办法关于控股股东、实际控制人的规定，但是持有上市公司股份低于百分之五的除外。
"""

CODE_DEFS = """限制代码（每笔减持输出适用的全部代码，按字母排序；都不适用则输出空列表 []）：
- PREFILE：违反第九条，未在卖出前十五个交易日预披露减持计划。
- DIV：触发第十条第一项，最近三年分红不达标被禁止（亏损年度不计入）。
- NAV：触发第十条第二项，近二十日任一日破净被禁止。
- IPOPRICE：触发第十一条，近二十日任一日破发被禁止（IPO时的控股股东/实控人及一致行动人，身份丧失后仍适用）。
- QUOTA：触发第十二条，集中竞价连续三个月减持超过公司总股本1%。
"""


@dataclass
class Case:
    id: str
    role: str  # controller | big | ipo_ex_controller | first_no_controller | other_preipo
    method: str  # auction | block | agreement | court
    source: str  # preipo | auction_bought | placement
    stake_pct: float  # 第一大股东等的持股比例（用于第二十三条<5%判断）
    plan_filed: bool  # 已按第九条披露减持计划
    div_short: bool  # 分红不达标（已排除亏损年度后仍不达标）
    break_nav: bool  # 近二十日任一日破净
    break_ipo: bool  # 近二十日任一日破发
    quarter_pct: float  # 连续三个月拟集中竞价减持占总股本比例
    note: str = ""


def evaluate(c: Case) -> list[str]:
    """Deterministic reference: the set of restriction codes that apply."""
    codes: set[str] = set()

    # 第二十三条：无控股股东情形下，第一大股东持股<5%完全除外。
    if c.role == "first_no_controller" and c.stake_pct < 5:
        return []

    # 第二条第二款：减持“集中竞价买入”的股份，仅适用少数条款，
    # 第九/十/十一/十二条均不适用。
    auction_bought = c.source == "auction_bought"

    is_controller = c.role in {"controller", "first_no_controller"}
    is_ipo_controller = c.role in {"controller", "ipo_ex_controller"}
    # 大股东（适用第九、十二条）：控股股东、普通大股东、第一大股东、IPO原控股股东。
    is_big = c.role in {"controller", "big", "ipo_ex_controller", "first_no_controller"}

    exchange_method = c.method in {"auction", "block"}

    # 第九条：大股东通过竞价/大宗减持须预披露；司法强制执行(court)除外；竞价买入来源除外。
    if is_big and exchange_method and not c.plan_filed and not auction_bought:
        if c.method != "court":
            codes.add("PREFILE")
    # court 本身不是 exchange_method 取值，这里保留显式语义：
    if c.method == "court":
        codes.discard("PREFILE")

    blocked_carveout = c.plan_filed or auction_bought

    # 第十条：仅控股股东/实控人；竞价或大宗；有计划披露则除外。
    if is_controller and exchange_method and not blocked_carveout:
        if c.div_short:
            codes.add("DIV")
        if c.break_nav:
            codes.add("NAV")

    # 第十一条：IPO时控股股东/实控人（身份丧失后仍适用）；竞价或大宗；破发。
    if is_ipo_controller and exchange_method and not blocked_carveout and c.break_ipo:
        codes.add("IPOPRICE")

    # 第十二条：集中竞价连续三个月>1%；竞价买入来源不适用。
    if is_big and c.method == "auction" and not auction_bought and c.quarter_pct > 1.0:
        codes.add("QUOTA")

    return sorted(codes)


# ---------------------------------------------------------------------------
# The batch. Hand-built to cover each interaction, plus compounding filler.
# ---------------------------------------------------------------------------
CASES: list[Case] = [
    Case("s01", "controller", "auction", "preipo", 30, False, True, False, False, 0.4,
         "控股股东；分红不达标；未披露计划"),
    Case("s02", "controller", "block", "preipo", 30, True, True, True, False, 0.0,
         "已披露计划→第十条除外，分红破净均豁免"),
    Case("s03", "big", "auction", "preipo", 8, False, True, True, False, 0.5,
         "普通大股东：第十条只约束控股股东→DIV/NAV不适用"),
    Case("s04", "controller", "auction", "auction_bought", 30, False, True, True, True, 3.0,
         "竞价买入来源→第九/十/十一/十二全不适用"),
    Case("s05", "ipo_ex_controller", "block", "preipo", 6, False, False, False, True, 0.0,
         "已非控股股东，但IPO原控股股东破发仍受第十一条约束"),
    Case("s06", "first_no_controller", "auction", "preipo", 4, False, True, True, False, 2.0,
         "无控股股东，第一大股东持股<5%→全除外"),
    Case("s07", "first_no_controller", "auction", "preipo", 7, False, True, False, False, 0.3,
         "无控股股东，第一大股东持股≥5%→视为控股股东，分红不达标"),
    Case("s08", "big", "court", "preipo", 9, False, False, False, False, 0.0,
         "司法强制执行→第九条预披露豁免"),
    Case("s09", "controller", "auction", "preipo", 30, False, False, False, False, 1.5,
         "控股股东竞价三个月>1%→QUOTA；未披露→PREFILE"),
    Case("s10", "big", "block", "preipo", 10, False, False, False, False, 0.0,
         "普通大股东大宗未披露→仅PREFILE"),
    Case("s11", "controller", "block", "preipo", 30, False, False, True, True, 0.0,
         "控股股东大宗未披露；破净+破发(且为IPO原控股)→PREFILE/NAV/IPOPRICE"),
    Case("s12", "ipo_ex_controller", "auction", "preipo", 6, False, True, True, False, 2.0,
         "已非控股股东：第十条不适用(DIV/NAV无)，第十一条无破发→仅PREFILE+QUOTA"),
    Case("s13", "controller", "agreement", "preipo", 30, False, True, True, True, 5.0,
         "协议转让：非竞价/大宗→第九/十/十一/十二均不触发"),
    Case("s14", "controller", "auction", "placement", 30, True, True, True, True, 0.5,
         "定增取得股份，已披露计划→第十/十一除外；竞价但quota未超"),
    Case("s15", "big", "auction", "preipo", 12, False, False, False, False, 1.2,
         "普通大股东竞价>1%未披露→PREFILE+QUOTA"),
    Case("s16", "controller", "block", "preipo", 30, False, True, False, False, 3.0,
         "大宗：quota只约束集中竞价→无QUOTA；未披露+分红不达标→PREFILE+DIV"),
]


def build_prompt() -> str:
    lines = ["case_id | 减持主体 | 减持方式 | 股份来源 | 持股% | 已披露计划 | 分红不达标 | 近20日破净 | 近20日破发 | 三个月竞价减持占比%"]
    role_cn = {
        "controller": "控股股东/实控人",
        "big": "普通大股东(>5%,非控股)",
        "ipo_ex_controller": "IPO原控股股东(现已非控股,持股>5%)",
        "first_no_controller": "无控股股东公司的第一大股东",
        "other_preipo": "持首发前股份的其他股东",
    }
    method_cn = {"auction": "集中竞价", "block": "大宗交易", "agreement": "协议转让", "court": "司法强制执行"}
    source_cn = {"preipo": "首发前老股", "auction_bought": "二级市场竞价买入", "placement": "定增/配售取得"}
    for c in CASES:
        lines.append(
            f"{c.id} | {role_cn[c.role]} | {method_cn[c.method]} | {source_cn[c.source]} | "
            f"{c.stake_pct:g} | {'是' if c.plan_filed else '否'} | {'是' if c.div_short else '否'} | "
            f"{'是' if c.break_nav else '否'} | {'是' if c.break_ipo else '否'} | {c.quarter_pct:g}"
        )
    table = "\n".join(lines)
    return (
        LAW
        + "\n" + CODE_DEFS
        + "\n【待筛查减持清单】逐笔依据上述条文判断适用的全部限制代码。\n"
        + table
        + "\n\n请输出 ```json，键为 case_id，值为该笔适用的限制代码列表（字母排序，空列表表示合规可减持）："
        + '\n例如 {"s01": ["DIV"], "s10": ["PREFILE"], "s06": []}'
    )


def extract(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    raw = blocks[-1] if blocks else text.strip()
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", dest="model_set", required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    reference = {c.id: evaluate(c) for c in CASES}

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    client = build_client(group, group.get("provider", "openrouter"), False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    save = HERE / "results" / "screen_answers"
    save.mkdir(parents=True, exist_ok=True)

    for model in args.model:
        print(f"\n#### {model}", flush=True)
        try:
            done = client.complete(
                model=model,
                messages=[
                    {"role": "system", "content": "你是中国证券合规专员，只依据所给条文逐笔判断，只输出要求的 JSON。"},
                    {"role": "user", "content": build_prompt()},
                ],
                temperature=defaults.get("temperature", 0.0),
                max_tokens=int(defaults.get("max_tokens", 16000)),
                seed=1,
                reasoning_effort=None,
            )
        except LLMError as exc:
            print(f"  LLMError: {exc}"[:300], flush=True)
            continue
        (save / f"{model.replace('/', '__')}.md").write_text(done.text, encoding="utf-8")
        try:
            got = extract(done.text)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"  parse error: {exc}", flush=True)
            continue

        per_item = []
        n_ok = 0
        for c in CASES:
            want = reference[c.id]
            g = sorted(set(got.get(c.id, []))) if isinstance(got.get(c.id), list) else None
            ok = g == want
            n_ok += int(ok)
            per_item.append({"id": c.id, "ok": ok, "got": g, "want": want, "note": c.note})
            mark = "OK " if ok else "XX "
            print(f"  {mark}{c.id}  got={g}  want={want}", flush=True)
        batch_ok = n_ok == len(CASES)
        print(f"  ITEM {n_ok}/{len(CASES)}   BATCH {'PASS' if batch_ok else 'FAIL'}", flush=True)
        with out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {"model": model, "item_ok": n_ok, "item_total": len(CASES),
                 "batch_ok": batch_ok, "items": per_item}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
