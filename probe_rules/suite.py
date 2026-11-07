"""Jagged rule-interaction suite: same engine, six surface variants.

    python probe_rules/suite.py --set bailian --model deepseek-v4.1-flash --out probe_rules/results/suite.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from faultline.llm import LLMError  # noqa: E402
from faultline.run_eval import build_client, load_config  # noqa: E402

SYSTEM = "你是严谨的结算核算员。严格按规则手册逐条计算，特别注意覆盖条款、同义词和重复记录。"
FIELDS = [
    "qualifying_net_revenue",
    "base_commission",
    "clawback",
    "platform_fee",
    "new_logo_bonus",
    "net_payable",
]


@dataclass(frozen=True)
class Order:
    oid: str
    amount: int
    status: str
    customer: str
    first: bool


@dataclass(frozen=True)
class Adj:
    amount: int
    target: str
    prior: bool = False


@dataclass
class Case:
    id: str
    note: str
    prompt: str
    orders: list[Order]
    adjs: list[Adj]
    included: frozenset[str]
    tier_cut: int = 400_000
    low_rate: float = 0.08
    high_rate: float = 0.12
    last_rate: float = 0.08
    bonus: int = 2_500
    new_logo_min: int = 5_000
    fee_rate: float = 0.05
    fee_share: float = 0.40


def settle(case: Case) -> dict:
    unique: dict[str, Order] = {}
    for order in case.orders:
        unique.setdefault(order.oid, order)
    kept = [o for o in unique.values() if o.status in case.included]
    kept_ids = {o.oid for o in kept}
    gross = {o.oid: o.amount for o in kept}
    customer_of = {o.oid: o.customer for o in kept}
    this_cut = 0
    clawback_base = 0
    customer_cut: dict[str, int] = defaultdict(int)
    for adj in case.adjs:
        if adj.prior:
            clawback_base += adj.amount
            continue
        if adj.target in kept_ids:
            this_cut += adj.amount
            customer_cut[customer_of[adj.target]] += adj.amount
    qnr = sum(gross.values()) - this_cut
    if qnr <= case.tier_cut:
        base = qnr * case.low_rate
    else:
        base = case.tier_cut * case.low_rate + (qnr - case.tier_cut) * case.high_rate
    clawback = clawback_base * case.last_rate
    customer_gross: dict[str, int] = defaultdict(int)
    for order in kept:
        customer_gross[order.customer] += order.amount
    customer_qnr = {c: customer_gross[c] - customer_cut[c] for c in customer_gross}
    disputed = {o.customer for o in unique.values() if o.status == "disputed"}
    first_this_month = {o.customer for o in unique.values() if o.first}
    logos = [
        c
        for c in first_this_month
        if customer_qnr.get(c, 0) >= case.new_logo_min and c not in disputed
    ]
    logo_qnr = sum(customer_qnr.get(c, 0) for c in logos)
    fee = 0.0 if qnr and logo_qnr / qnr >= case.fee_share else base * case.fee_rate
    bonus = case.bonus * len(logos)
    return {
        "qualifying_net_revenue": qnr,
        "base_commission": base,
        "clawback": clawback,
        "platform_fee": fee,
        "new_logo_bonus": bonus,
        "net_payable": int(base - clawback - fee + bonus),
    }


def _json_line() -> str:
    keys = ", ".join(f'"{f}": 数值' for f in FIELDS)
    return (
        "最后输出一个 ```json 代码块，字段如下（纯数字，不要千分位逗号、不要单位）：\n"
        "{" + keys + "}"
    )


BASE_ORDERS = [
    Order("O1", 500_000, "completed", "C1", False),
    Order("O2", 350_000, "settled", "C2", True),
    Order("O2", 350_000, "settled", "C2", True),
    Order("O3", 80_000, "pending", "C3", True),
    Order("O4", 40_000, "disputed", "C4", True),
    Order("O5", 2_000_000, "cancelled", "C5", False),
]
BASE_ADJS = [
    Adj(30_000, "O1"),
    Adj(10_000, "O2"),
    Adj(40_000, "P9", prior=True),
]
INCLUDED = frozenset({"completed", "settled"})


CASES: list[Case] = [
    Case(
        id="s1_baseline",
        note="v2 wording, already passed once",
        orders=BASE_ORDERS,
        adjs=BASE_ADJS,
        included=INCLUDED,
        prompt="""下面是一份自包含的销售提成结算规则手册（与任何现实制度无关，只按本手册计算），以及销售代表 R1 本月的业务明细。请算出本月应付净额（元）。

# 规则手册 RevShare v4（条款从上到下适用，除非某条写明“覆盖”）
1. 基础提成按合格净收入计：不超过 400,000 的部分 8%，超过 400,000 的部分 12%。
2. 合格净收入 = 本月订单毛额 − 本月退款 − 本月拒付。状态为 pending、disputed、cancelled 的订单一律不计入（其毛额、及其退款/拒付都不计）。状态 settled 视同 completed，计入。
3. 同一 order_id 出现两次时只计一次；若金额不同，以第一次出现为准。
4. 新客奖励：每个本月新客 +2,500 元。本月新客 = 有史以来第一笔订单在本月，且该客户本月合格净收入 ≥ 5,000。若该客户本月有任何 disputed 订单，取消新客资格。
5. 【覆盖规则 2】往月订单的退款不从收入扣减，按上月档位费率从提成回拨。R1 上月档位费率 8%。
6. 【覆盖】平台服务费 = 基础提成（阶梯后、回拨前）的 5%。若新客贡献的合格净收入占全部合格净收入 ≥ 40%，服务费免收。新客奖励不受服务费影响。
7. 应付净额 = 基础提成 − 回拨 − 平台服务费 + 新客奖励，向下取整到整数元。

# R1 本月明细
订单 (order_id, 毛额, 状态, 客户, 是否该客户有史以来第一笔)：
- O1, 500,000, completed, C1, 否
- O2, 350,000, settled, C2, 是
- O2, 350,000, settled, C2, 是
- O3, 80,000, pending, C3, 是
- O4, 40,000, disputed, C4, 是
- O5, 2,000,000, cancelled, C5, 否
退款与拒付：
- Ra 30,000 针对 O1（本月）
- CBa 10,000 针对 O2（本月）
- Rb 40,000 针对 P9（上月订单）
""" + _json_line(),
    ),
    Case(
        id="s2_rephrase",
        note="same numbers, 已结清, fee phrased as charge-if-under-40%",
        orders=BASE_ORDERS,
        adjs=BASE_ADJS,
        included=frozenset({"completed", "settled", "已结清"}),
        prompt="""按《提成办法（内部稿）》给 R1 算本月应付净额，单位元。办法与事实都在下面，不要套用别的制度。

办法：
A. 计入口径：仅统计本月、且状态属于 {completed, 已结清} 的订单。pending / disputed / cancelled 整单剔除，连同它们身上的退款和拒付一起剔除。已结清 = completed。
B. 重复单号只留第一条。
C. 合格净收入 = 计入订单毛额 − 这些订单上的本月退款 − 这些订单上的本月拒付。
D. 提成：合格净收入 40 万及以内 8%，超出部分 12%。
E. 上月订单的退款改走回拨：金额 × 上月费率。R1 上月费率 8%。不要把它从合格净收入里扣。
F. 新客奖 2500/人。新客 = 本月才有第一笔单，且该客户本月合格净收入 ≥ 5000；本月只要有过 disputed 单就取消。
G. 服务费：提成（D 的结果）× 5%。仅当新客带来的合格净收入 / 总合格净收入 **低于 40%** 时收取；达到或超过 40% 则免收。奖金不参与服务费。
H. 应付 = D − E − 服务费 + F，向下取整。

明细：
O1 500000 completed C1 老客
O2 350000 已结清 C2 该客户第一笔
O2 350000 已结清 C2 该客户第一笔（重复行）
O3 80000 pending C3 该客户第一笔
O4 40000 disputed C4 该客户第一笔
O5 2000000 cancelled C5 老客
Ra 退款 30000 → O1 本月
CBa 拒付 10000 → O2 本月
Rb 退款 40000 → P9 上月
""" + _json_line(),
    ),
    Case(
        id="s3_fee_applies",
        note="O2 smaller so new-logo share < 40% and fee is charged",
        orders=[
            Order("O1", 500_000, "completed", "C1", False),
            Order("O2", 200_000, "settled", "C2", True),
            Order("O2", 200_000, "settled", "C2", True),
            Order("O3", 80_000, "pending", "C3", True),
            Order("O4", 40_000, "disputed", "C4", True),
            Order("O5", 2_000_000, "cancelled", "C5", False),
        ],
        adjs=BASE_ADJS,
        included=INCLUDED,
        prompt="""自包含规则，只按本文计算 R1 本月应付净额（元）。

规则：
1. 基础提成：合格净收入 ≤400,000 部分 8%，超出部分 12%。
2. 合格净收入 = 本月计入订单毛额 − 本月退款 − 本月拒付。pending / disputed / cancelled 不计入（毛额和其退款/拒付都不计）。settled 视同 completed。
3. 同一 order_id 只计一次；金额不同时以第一次为准。
4. 新客奖 +2,500。新客 = 本月第一笔订单且该客户本月合格净收入 ≥5,000；本月有 disputed 则取消。
5. 往月订单退款不扣收入，按上月费率 8% 回拨。
6. 平台服务费 = 基础提成 × 5%；新客合格净收入占比 ≥40% 时免收。
7. 应付 = 基础提成 − 回拨 − 服务费 + 新客奖，向下取整。

订单：
- O1, 500,000, completed, C1, 老客
- O2, 200,000, settled, C2, 第一笔
- O2, 200,000, settled, C2, 第一笔
- O3, 80,000, pending, C3, 第一笔
- O4, 40,000, disputed, C4, 第一笔
- O5, 2,000,000, cancelled, C5, 老客
调整：Ra 30,000→O1 本月；CBa 10,000→O2 本月；Rb 40,000→P9 上月。
""" + _json_line(),
    ),
    Case(
        id="s4_lost_logo",
        note="C2 also has a disputed order, so bonus and fee-waiver both vanish",
        orders=[
            Order("O1", 500_000, "completed", "C1", False),
            Order("O2", 350_000, "settled", "C2", True),
            Order("O2", 350_000, "settled", "C2", True),
            Order("O3", 80_000, "pending", "C3", True),
            Order("O4", 40_000, "disputed", "C4", True),
            Order("O5", 2_000_000, "cancelled", "C5", False),
            Order("O6", 1_000, "disputed", "C2", True),
        ],
        adjs=BASE_ADJS,
        included=INCLUDED,
        prompt="""只按下列手册计算 R1 本月应付净额（元）。

手册：
1. 提成：合格净收入 400,000 及以内 8%，超出 12%。
2. 合格净收入来自本月 completed/settled 订单，减去这些订单上的本月退款和拒付。pending、disputed、cancelled 整单排除。
3. 重复 order_id 保留第一次。
4. 新客 +2,500。条件：本月才有第一笔订单，该客户本月合格净收入 ≥5,000，且该客户本月没有任何 disputed 订单。
5. 往月退款按 8% 回拨，不进合格净收入。
6. 服务费 5%（按提成、回拨前）。新客合格净收入 / 总合格净收入 ≥40% 才免。
7. 应付 = 提成 − 回拨 − 服务费 + 新客奖，向下取整。

订单：
O1 500000 completed C1 老客
O2 350000 settled C2 第一笔
O2 350000 settled C2 第一笔
O3 80000 pending C3 第一笔
O4 40000 disputed C4 第一笔
O5 2000000 cancelled C5 老客
O6 1000 disputed C2 第一笔
Ra 30000→O1 本月；CBa 10000→O2 本月；Rb 40000→P9 上月。
""" + _json_line(),
    ),
    Case(
        id="s5_chatty",
        note="conversational wrap plus a refund on a cancelled order",
        orders=BASE_ORDERS,
        adjs=BASE_ADJS + [Adj(99_000, "O5")],
        included=INCLUDED,
        prompt="""同事把这个月的提成核算丢过来了，说“按附件办法算，别发明规则”。请给出应付净额。

附件办法（摘要）：计入 completed 和 settled；pending/disputed/cancelled 整单不要；settled=completed。重复单号只留首次。合格净收入=计入毛额−计入订单上的本月退款/拒付。40 万以内 8%，超出 12%。上月单的退款按 8% 回拨、不冲收入。新客奖 2500，要求本月第一笔且该客本月合格净收入≥5000，有 disputed 就没奖。服务费=提成×5%，新客份额≥40%免。最后向下取整：提成−回拨−服务费+奖金。

数据（他从系统导出的，可能有垃圾行）：
O1 500000 completed 老客C1
O2 350000 settled 新客C2
O2 350000 settled 新客C2（导出重复了）
O3 80000 pending 新客C3
O4 40000 disputed 新客C4
O5 2000000 cancelled 老客C5
退款 30000 打在 O1 上（本月单）
拒付 10000 打在 O2 上（本月单）
退款 40000 打在 P9 上（那是上个月的单）
还有一笔退款 99000 打在 O5 上
""" + _json_line(),
    ),
    Case(
        id="s6_dup_amount",
        note="duplicate O2 lists 380000 the second time; first amount must win",
        orders=[
            Order("O1", 500_000, "completed", "C1", False),
            Order("O2", 350_000, "settled", "C2", True),
            Order("O2", 380_000, "settled", "C2", True),
            Order("O3", 80_000, "pending", "C3", True),
            Order("O4", 40_000, "disputed", "C4", True),
            Order("O5", 2_000_000, "cancelled", "C5", False),
        ],
        adjs=BASE_ADJS,
        included=INCLUDED,
        prompt="""按手册计算 R1 本月应付净额（元）。手册写明：同一 order_id 出现两次且金额不同时，以第一次出现的金额为准。

1. 提成：合格净收入 400,000 及以内 8%，超出 12%。
2. 合格净收入 = 本月 completed/settled 毛额 − 这些订单的本月退款/拒付。pending、disputed、cancelled 排除。settled 视同 completed。
3. 重复 order_id：只留第一次，包括金额。
4. 新客 +2,500（本月第一笔、该客本月合格净收入≥5,000、本月无 disputed）。
5. 往月退款按 8% 回拨。
6. 服务费 5%，新客合格净收入占比≥40% 免收。
7. 应付 = 提成 − 回拨 − 服务费 + 新客奖，向下取整。

订单出现顺序：
1) O1 500,000 completed C1 老客
2) O2 350,000 settled C2 第一笔
3) O2 380,000 settled C2 第一笔
4) O3 80,000 pending C3 第一笔
5) O4 40,000 disputed C4 第一笔
6) O5 2,000,000 cancelled C5 老客
Ra 30,000→O1 本月；CBa 10,000→O2 本月；Rb 40,000→P9 上月。
""" + _json_line(),
    ),
]


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
    parser.add_argument("--case", action="append", default=None)
    args = parser.parse_args()

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    client = build_client(group, group.get("provider", "openrouter"), False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cases = [c for c in CASES if args.case is None or c.id in args.case]
    save_root = HERE / "results" / "suite_answers"
    save_root.mkdir(parents=True, exist_ok=True)

    total = right = 0
    for case in cases:
        want = settle(case)
        print(f"\n== {case.id}  truth net={want['net_payable']} ({case.note})", flush=True)
        for model in args.model:
            print(f"{model:<24} calling...", flush=True)
            row = {"case": case.id, "model": model, "error": None, "results": {}}
            try:
                done = client.complete(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": case.prompt},
                    ],
                    temperature=defaults.get("temperature", 0.0),
                    max_tokens=int(defaults.get("max_tokens", 16000)),
                    seed=1,
                    reasoning_effort=None,
                )
                (save_root / f"{case.id}_{model.replace('/', '__')}.md").write_text(
                    done.text, encoding="utf-8"
                )
                got = extract(done.text)
                for field in FIELDS:
                    try:
                        ok = abs(float(got.get(field)) - want[field]) <= max(
                            0.5, 0.001 * abs(want[field] or 1)
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
            total += 1
            net_ok = row["results"]["net_payable"]["ok"]
            right += int(net_ok)
            print(f"{model:<24} net_payable {'OK' if net_ok else 'WRONG'}", flush=True)
            for field in FIELDS:
                item = row["results"][field]
                if not item["ok"]:
                    print(f"    {field}: got={item['got']} want={item['want']}", flush=True)
    print(f"\nnet_payable {right}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
