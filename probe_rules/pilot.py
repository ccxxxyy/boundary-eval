"""Pilot for a rule-interaction eval: a self-contained rulebook + one fact pattern.

The hard part is not arithmetic; it is two override clauses (rule 5 and rule 6)
that reverse the default handling of prior-month refunds and of the cap, plus
distractor orders (pending / disputed) and a new customer that does not qualify.
A model that skims applies the defaults and gets a different, plausible number.

Everything the grader checks is stated in the prompt. Truth is computed in
reference() below, not hand-typed, so the task is provably solvable.

    python probe_rules/pilot.py --set bailian --model deepseek-v4.1-flash --out probe_rules/results/pilot.jsonl
    python probe_rules/pilot.py --set gemini-frontier --model gemini-3.1-pro-preview --out probe_rules/results/pilot.jsonl
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

SYSTEM = "你是严谨的结算核算员。严格按规则手册逐条计算，特别注意带有“覆盖/例外”的条款。"

PROMPT = """下面是一份**自包含**的销售提成结算规则手册（与任何现实制度无关，只按本手册计算），以及某销售代表（R1）本月的业务明细。请算出本月**应付净额**（单位：元），并给出分解。

# 规则手册 RevShare v3（条款从上到下适用，除非某条写明“覆盖”）

1. 基础提成 = “合格净收入”的 8%。
2. 合格净收入 = 本月订单的毛额 − 退款 − 拒付（chargeback）。但**状态为 pending 或 disputed 的订单一律不计入**（其毛额、及其退款/拒付都不计）。
3. 阶梯加速：合格净收入中**超过 500,000 的部分**按 12% 计（而非 8%）；不超过 500,000 的部分仍按 8%。
4. 新客奖励：每个“本月新客”+2,000 元固定奖励。“本月新客”指其**有史以来第一笔订单发生在本月**、且该客户**本月的合格净收入 ≥ 1,000** 的客户。
5. 【覆盖规则 2】规则 2 中的“退款”**只包含对本月订单的退款**。对**往月订单**的退款不从收入中扣减，而是按该代表的**上月档位费率**作为**提成回拨（clawback）**从提成中直接扣除。R1 上月档位费率为 8%。
6. 【覆盖】总提成（即第 1、3、5 条计算后的结果）**上限为 90,000**。但第 4 条的新客奖励**不受此上限限制，且在封顶之后额外叠加支付**。
7. 最终应付净额向下取整到整数元。

# R1 本月业务明细

订单：
- O1：本月下单，毛额 800,000，状态 completed，客户 C1（老客户，往月已有订单）
- O2：本月下单，毛额 600,000，状态 completed，客户 C2（该客户有史以来第一笔订单就是 O2）
- O3：本月下单，毛额 120,000，状态 pending，客户 C3（该客户此前从无订单）
- O4：本月下单，毛额 90,000，状态 disputed，客户 C1

退款与拒付：
- 退款 Ra：60,000，针对 O1（本月订单）
- 拒付 CBa：20,000，针对 O2（本月订单）
- 退款 Rb：25,000，针对订单 P9（P9 是**上月**下单的订单）

请只依据本手册计算，最后输出一个 ```json 代码块，字段如下（数值为纯数字、不要千分位逗号、不要单位）：
{"qualifying_net_revenue": 数值, "base_commission": 数值, "clawback": 数值, "commission_after_cap": 数值, "new_logo_bonus": 数值, "net_payable": 数值}
"""


def reference() -> dict:
    # Rule 2: this-month, non-excluded orders only; subtract this-month refunds/chargebacks.
    qnr = 800_000 + 600_000 - 60_000 - 20_000  # O1,O2; O3 pending & O4 disputed excluded
    # Rules 1+3: tiered.
    base = 500_000 * 0.08 + (qnr - 500_000) * 0.12
    # Rule 5: prior-month refund -> clawback at last month's tier rate (8%), not a revenue cut.
    clawback = 25_000 * 0.08
    after_clawback = base - clawback
    # Rule 6: cap the commission (not the bonus) at 90,000.
    after_cap = min(after_clawback, 90_000)
    # Rule 4: C2 is a new logo (first-ever order this month) and its this-month QNR = 600k-20k >= 1000.
    #         C3's only order is pending -> excluded -> QNR_C3 = 0 < 1000 -> not a qualifying new logo.
    bonus = 2_000
    net = int(after_cap + bonus)  # rule 7 floor
    return {
        "qualifying_net_revenue": qnr,
        "base_commission": base,
        "clawback": clawback,
        "commission_after_cap": after_cap,
        "new_logo_bonus": bonus,
        "net_payable": net,
    }


FIELDS = ["qualifying_net_revenue", "base_commission", "clawback",
          "commission_after_cap", "new_logo_bonus", "net_payable"]


def extract(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    if not blocks:
        raise ValueError("no json block")
    return json.loads(blocks[-1])


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
    want = reference()

    for model in args.model:
        print(f"{model:<24} calling...", flush=True)
        row = {"model": model, "error": None, "results": {}}
        try:
            done = client.complete(
                model=model,
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": PROMPT}],
                temperature=defaults.get("temperature", 0.0),
                max_tokens=int(defaults.get("max_tokens", 16000)),
                seed=1, reasoning_effort=None,
            )
            save = HERE / "results" / "answers"
            save.mkdir(parents=True, exist_ok=True)
            (save / f"{model.replace('/', '__')}.md").write_text(done.text, encoding="utf-8")
            got = extract(done.text)
            for f in FIELDS:
                try:
                    ok = abs(float(got.get(f)) - want[f]) <= max(0.5, 0.001 * abs(want[f]))
                except (TypeError, ValueError):
                    ok = False
                row["results"][f] = {"got": got.get(f), "want": round(want[f], 2), "ok": ok}
        except (LLMError, ValueError, json.JSONDecodeError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]

        with out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        if row["error"]:
            print(f"{model:<24} ERROR {row['error']}", flush=True)
        else:
            key_ok = row["results"]["net_payable"]["ok"]
            print(f"{model:<24} net_payable {'OK' if key_ok else 'WRONG'}", flush=True)
            for f in FIELDS:
                r = row["results"][f]
                print(f"    {f}: got={r['got']} want={r['want']} -> {'OK' if r['ok'] else 'WRONG'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
