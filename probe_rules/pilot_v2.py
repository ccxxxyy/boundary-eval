"""Harder rule-interaction probe. Cap no longer hides a missed tier.

Changes vs v1:
- No binding cap. Every wrong override moves net_payable.
- Status synonym: "settled" counts as completed.
- Duplicate order id: count once.
- Platform fee waived only if new-logo share of QNR >= 40%.
- Disputed customer is disqualified from the new-logo bonus.

    python probe_rules/pilot_v2.py --set gemini --model gemini-3.5-flash --out probe_rules/results/pilot_v2.jsonl
    python probe_rules/pilot_v2.py --set bailian --model deepseek-v4.1-flash --out probe_rules/results/pilot_v2.jsonl
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

# 规则手册 RevShare v4（条款从上到下适用，除非某条写明“覆盖”）

1. 基础提成按“合格净收入”计：不超过 400,000 的部分 8%，**超过 400,000 的部分 12%**。
2. 合格净收入 = 本月订单毛额 − 本月退款 − 本月拒付。状态为 pending、disputed、cancelled 的订单一律不计入（其毛额、及其退款/拒付都不计）。状态 **settled 视同 completed**，计入。
3. 同一 `order_id` 在明细中出现两次时，只计一次（取列出的金额；两条金额相同则任意一条）。
4. 新客奖励：每个“本月新客”+2,500 元。“本月新客”指其有史以来第一笔订单发生在本月，且该客户本月合格净收入 ≥ 5,000。若该客户本月有任何 disputed 订单，取消新客资格。
5. 【覆盖规则 2】规则 2 中的“退款”只包含对本月订单的退款。对**往月订单**的退款不从收入中扣减，而是按该代表的上月档位费率作为提成回拨从提成中直接扣除。R1 上月档位费率为 8%。
6. 【覆盖】平台服务费 = 基础提成（阶梯后、回拨前）的 5%。但若“新客贡献的合格净收入”占全部合格净收入的比例 **≥ 40%**，服务费免收。新客奖励不受服务费影响。
7. 应付净额 = 基础提成 − 回拨 − 平台服务费 + 新客奖励，向下取整到整数元。

# R1 本月业务明细

订单（字段：order_id, 毛额, 状态, 客户, 是否该客户有史以来第一笔）：
- O1, 500,000, completed, C1, 否（老客户）
- O2, 350,000, settled, C2, 是
- O2, 350,000, settled, C2, 是   ← 同一订单重复列出
- O3, 80,000, pending, C3, 是
- O4, 40,000, disputed, C4, 是
- O5, 2,000,000, cancelled, C5, 否

退款与拒付：
- 退款 Ra：30,000，针对 O1（本月订单）
- 拒付 CBa：10,000，针对 O2（本月订单）
- 退款 Rb：40,000，针对订单 P9（P9 是上月下单的订单）

请只依据本手册计算，最后输出一个 ```json 代码块，字段如下（数值为纯数字、不要千分位逗号、不要单位）：
{"qualifying_net_revenue": 数值, "base_commission": 数值, "clawback": 数值, "platform_fee": 数值, "new_logo_bonus": 数值, "net_payable": 数值}
"""

FIELDS = [
    "qualifying_net_revenue",
    "base_commission",
    "clawback",
    "platform_fee",
    "new_logo_bonus",
    "net_payable",
]


def reference() -> dict:
    # O1 completed 500k, O2 settled 350k once, others excluded.
    qnr = 500_000 + 350_000 - 30_000 - 10_000
    over = qnr - 400_000
    base = 400_000 * 0.08 + over * 0.12
    clawback = 40_000 * 0.08
    # C2 is the only new logo: first order this month, QNR = 350k-10k, no disputed.
    new_logo_qnr = 350_000 - 10_000
    fee = 0.0 if new_logo_qnr / qnr >= 0.40 else base * 0.05
    bonus = 2_500
    net = int(base - clawback - fee + bonus)
    return {
        "qualifying_net_revenue": qnr,
        "base_commission": base,
        "clawback": clawback,
        "platform_fee": fee,
        "new_logo_bonus": bonus,
        "net_payable": net,
    }


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
    print("truth:", {k: round(v, 2) for k, v in want.items()}, flush=True)

    for model in args.model:
        print(f"{model:<24} calling...", flush=True)
        row = {"model": model, "error": None, "results": {}}
        try:
            done = client.complete(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": PROMPT},
                ],
                temperature=defaults.get("temperature", 0.0),
                max_tokens=int(defaults.get("max_tokens", 16000)),
                seed=1,
                reasoning_effort=None,
            )
            save = HERE / "results" / "answers_v2"
            save.mkdir(parents=True, exist_ok=True)
            (save / f"{model.replace('/', '__')}.md").write_text(done.text, encoding="utf-8")
            got = extract(done.text)
            for field in FIELDS:
                try:
                    ok = abs(float(got.get(field)) - want[field]) <= max(
                        0.5, 0.001 * abs(want[field])
                    )
                except (TypeError, ValueError):
                    ok = False
                row["results"][field] = {
                    "got": got.get(field),
                    "want": round(want[field], 2),
                    "ok": ok,
                }
        except (LLMError, ValueError, json.JSONDecodeError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]

        with out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        if row["error"]:
            print(f"{model:<24} ERROR {row['error']}", flush=True)
            continue
        key_ok = row["results"]["net_payable"]["ok"]
        print(f"{model:<24} net_payable {'OK' if key_ok else 'WRONG'}", flush=True)
        for field in FIELDS:
            item = row["results"][field]
            print(
                f"    {field}: got={item['got']} want={item['want']} -> "
                f"{'OK' if item['ok'] else 'WRONG'}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
