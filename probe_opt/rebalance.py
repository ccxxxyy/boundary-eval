"""A-share rebalancing probe: can a model produce a compliant, near-optimal trade list?

    python probe_opt/rebalance.py --solve-only            # instances + solver optimum
    python probe_opt/rebalance.py --set bailian --model kimi-k3.1-pro --mode direct --mode code

Instances come from a fixed seeded generator (sizes fixed in GEN below, chosen
before any model was run). The verifier checks every rule in the prompt
mechanically; the optimum comes from a MILP solved by HiGHS. A run counts as
"qualified" only if it is feasible and its objective is within 1% of optimum.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pulp

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

OUT = HERE / "results"
ENV_PY = HERE / "env" / "Scripts" / "python.exe"

GEN = {"n_stocks": 15, "sectors": ["银行", "医药", "电子", "消费"], "seeds": [1, 2, 3, 4]}
COMMISSION, MIN_COMMISSION, STAMP = 0.00025, 5.0, 0.0005
SINGLE_CAP, TURNOVER_CAP, RESERVE = 0.10, 0.25, 0.01
PASS_GAP = 0.01


def generate(seed: int) -> dict:
    rng = random.Random(seed)
    while True:
        stocks = []
        raw = [rng.uniform(0.5, 1.5) for _ in range(GEN["n_stocks"])]
        total = sum(raw)
        for i in range(GEN["n_stocks"]):
            price = round(rng.choice([rng.uniform(3, 15), rng.uniform(15, 80), rng.uniform(80, 400)]), 2)
            stocks.append({
                "code": f"{rng.choice(['600', '601', '000', '002'])}{rng.randint(0, 999):03d}",
                "sector": GEN["sectors"][i % len(GEN["sectors"])],
                "price": price,
                "target_weight": round(0.96 * raw[i] / total, 4),
            })
        nav_guess = 10_000_000
        for s in stocks:
            drift = s["target_weight"] * rng.uniform(0.4, 1.8)
            s["holding"] = int(drift * nav_guess / s["price"] / 100) * 100
            s["locked"] = int(s["holding"] * rng.choice([0, 0, 0, 0.3, 0.6]) / 100) * 100
            s["status"] = rng.choice(["正常"] * 8 + ["停牌", "涨停", "跌停"])
        if len({s["code"] for s in stocks}) != len(stocks):
            continue
        cash = round(rng.uniform(0.01, 0.06) * nav_guess, 2)
        inst = {"seed": seed, "cash": cash, "stocks": stocks,
                "sector_bounds": {sec: [0.15, 0.32] for sec in GEN["sectors"]}}
        if solve(inst) is not None:
            return inst


def nav0(inst: dict) -> float:
    return inst["cash"] + sum(s["price"] * s["holding"] for s in inst["stocks"])


def fees(price: float, shares: int) -> float:
    if shares == 0:
        return 0.0
    value = abs(shares) * price
    fee = max(MIN_COMMISSION, COMMISSION * value)
    if shares < 0:
        fee += STAMP * value
    return fee


def objective(inst: dict, trades: dict) -> float:
    nav = nav0(inst)
    total = 0.0
    for s in inst["stocks"]:
        x = trades.get(s["code"], 0)
        total += abs(s["price"] * (s["holding"] + x) - s["target_weight"] * nav) + fees(s["price"], x)
    return total


def violations(inst: dict, trades: dict) -> list[str]:
    nav = nav0(inst)
    codes = {s["code"] for s in inst["stocks"]}
    bad = [f"未知代码 {c}" for c in trades if c not in codes]
    cash_out = 0.0
    turnover = 0.0
    sector_value = {sec: 0.0 for sec in inst["sector_bounds"]}
    for s in inst["stocks"]:
        x = trades.get(s["code"], 0)
        if not isinstance(x, int) or isinstance(x, bool):
            bad.append(f"{s['code']} 股数不是整数: {x!r}")
            continue
        if x % 100:
            bad.append(f"{s['code']} 非100股整数倍: {x}")
        if s["status"] == "停牌" and x != 0:
            bad.append(f"{s['code']} 停牌仍交易")
        if s["status"] == "涨停" and x > 0:
            bad.append(f"{s['code']} 涨停仍买入")
        if s["status"] == "跌停" and x < 0:
            bad.append(f"{s['code']} 跌停仍卖出")
        final = s["holding"] + x
        if final < s["locked"]:
            bad.append(f"{s['code']} 卖出了T+1锁定股份 (剩{final} < 锁定{s['locked']})")
        value = s["price"] * final
        if value > SINGLE_CAP * nav + 1e-6:
            bad.append(f"{s['code']} 单票 {value / nav:.4%} > 10%")
        sector_value[s["sector"]] += value
        cash_out += s["price"] * x + fees(s["price"], x)
        turnover += abs(x) * s["price"]
    for sec, (lo, hi) in inst["sector_bounds"].items():
        w = sector_value[sec] / nav
        if w < lo - 1e-9 or w > hi + 1e-9:
            bad.append(f"行业{sec} {w:.4%} 不在[{lo:.0%},{hi:.0%}]")
    if inst["cash"] - cash_out < RESERVE * nav - 1e-6:
        bad.append(f"交易后现金 {inst['cash'] - cash_out:.2f} < 留存 {RESERVE * nav:.2f}")
    if turnover > TURNOVER_CAP * nav + 1e-6:
        bad.append(f"成交额 {turnover / nav:.4%} > 25%")
    return bad


def solve(inst: dict) -> tuple[float, dict] | None:
    nav = nav0(inst)
    prob = pulp.LpProblem("rebalance", pulp.LpMinimize)
    terms, cash_out, turnover = [], [], []
    sector_value = {sec: [] for sec in inst["sector_bounds"]}
    lots = {}
    for i, s in enumerate(inst["stocks"]):
        p, h = s["price"], s["holding"]
        max_buy = 0 if s["status"] in ("停牌", "涨停") else int(SINGLE_CAP * nav / p / 100) + 1
        max_sell = 0 if s["status"] in ("停牌", "跌停") else (h - s["locked"]) // 100
        b = pulp.LpVariable(f"b{i}", 0, max_buy, cat="Integer")
        sl = pulp.LpVariable(f"s{i}", 0, max_sell, cat="Integer")
        yb = pulp.LpVariable(f"yb{i}", cat="Binary")
        ys = pulp.LpVariable(f"ys{i}", cat="Binary")
        prob += b <= max_buy * yb
        prob += sl <= max_sell * ys
        prob += yb + ys <= 1
        comm = pulp.LpVariable(f"c{i}", 0)
        prob += comm >= COMMISSION * 100 * p * (b + sl)
        prob += comm >= MIN_COMMISSION * (yb + ys)
        stamp = STAMP * 100 * p * sl
        value = p * (h + 100 * b - 100 * sl)
        dev = pulp.LpVariable(f"d{i}", 0)
        prob += dev >= value - s["target_weight"] * nav
        prob += dev >= s["target_weight"] * nav - value
        prob += value <= SINGLE_CAP * nav
        sector_value[s["sector"]].append(value)
        terms += [dev, comm, stamp]
        cash_out.append(100 * p * (b - sl) + comm + stamp)
        turnover.append(100 * p * (b + sl))
        lots[s["code"]] = (b, sl)
    prob += pulp.lpSum(terms)
    for sec, (lo, hi) in inst["sector_bounds"].items():
        prob += pulp.lpSum(sector_value[sec]) >= lo * nav
        prob += pulp.lpSum(sector_value[sec]) <= hi * nav
    prob += inst["cash"] - pulp.lpSum(cash_out) >= RESERVE * nav
    prob += pulp.lpSum(turnover) <= TURNOVER_CAP * nav
    prob.solve(pulp.HiGHS(msg=False, gapRel=0.0))
    if pulp.LpStatus[prob.status] != "Optimal":
        return None
    trades = {code: 100 * (round(b.value()) - round(sl.value())) for code, (b, sl) in lots.items()}
    if violations(inst, trades):
        return None
    return objective(inst, trades), trades


def render(inst: dict, mode: str) -> str:
    nav = nav0(inst)
    rows = "\n".join(
        f"| {s['code']} | {s['sector']} | {s['price']:.2f} | {s['holding']} | {s['locked']} | {s['status']} | {s['target_weight']:.2%} |"
        for s in inst["stocks"]
    )
    bounds = "、".join(f"{sec} {lo:.0%}–{hi:.0%}" for sec, (lo, hi) in inst["sector_bounds"].items())
    data = json.dumps(inst, ensure_ascii=False)
    body = f"""# 任务：A 股组合今日调仓

你是一家公募基金的交易员助理。请为下面这个组合给出今天的调仓指令。

## 组合现状

当前现金：{inst['cash']:.2f} 元。按当前价格计算，组合总资产（现金 + 持仓市值）NAV0 = {nav:.2f} 元。
下面所有"占比"都以 NAV0 为分母（不随交易变化）。

| 代码 | 行业 | 价格(元) | 当前持股(股) | 其中今日买入(股) | 状态 | 目标权重 |
|---|---|---|---|---|---|---|
{rows}

## 必须满足的规则（任何一条违反，指令即作废）

1. 每只股票的交易股数必须是 100 的整数倍（正数买入，负数卖出，0 不交易）。成交价就是表中价格。
2. 状态为"停牌"的不能交易；"涨停"的不能买入；"跌停"的不能卖出。
3. T+1：表中"其中今日买入"的股份今天不能卖出，即交易后持股不得少于这个数。
4. 交易后单只股票市值不得超过 NAV0 的 10%。
5. 交易后每个行业的股票市值合计占 NAV0 的比例必须在区间内：{bounds}。
6. 费用：每只有交易的股票收一次佣金 = max(5 元, 成交金额 × 0.025%)；卖出另收印花税 = 卖出成交金额 × 0.05%。费用不取整。
7. 交易后现金 = 当前现金 − 买入金额 + 卖出金额 − 全部费用，必须不少于 NAV0 的 1%。
8. 总成交金额（买入金额 + 卖出金额）不得超过 NAV0 的 25%。

## 目标

在满足全部规则的前提下，使下面的值最小：

    Σ_每只股票 |交易后市值 − 目标权重 × NAV0|  +  全部费用

## 数据（与上表相同，JSON 形式）

```json
{data}
```
"""
    if mode == "direct":
        return body + """
## 输出

只输出一个 ```json 代码块，内容是一个对象：键为股票代码（字符串），值为交易股数（整数，买入为正、卖出为负）。不交易的股票可以省略或写 0。
"""
    return body + """
## 输出

写一个完整的 Python 程序，放在一个 ```python 代码块里。程序运行时会在一个装有 Python 3.11、numpy、pulp（自带 CBC 与 HiGHS 求解器）的环境中被执行一次，限时 120 秒，没有网络。
程序必须向标准输出打印且只打印一行 JSON：键为股票代码（字符串），值为交易股数（整数，买入为正、卖出为负）。
"""


SYSTEM = "你是严谨的量化交易工程师。严格按要求的格式作答。"


def extract(text: str, lang: str) -> str | None:
    blocks = re.findall(rf"```{lang}\s*\n(.*?)```", text, re.S)
    return blocks[-1] if blocks else None


def parse_trades(raw: str) -> dict:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return {str(k): v for k, v in data.items()}


@dataclass
class Row:
    seed: int
    model: str
    mode: str
    feasible: bool
    qualified: bool
    gap: float | None
    violations: list
    error: str | None
    completion_tokens: int


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-only", action="store_true")
    parser.add_argument("--set", dest="model_set", default="bailian")
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--mode", action="append", default=[])
    parser.add_argument("--seeds", type=int, nargs="+", default=GEN["seeds"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    OUT.mkdir(exist_ok=True)
    instances = {}
    for seed in args.seeds:
        inst = generate(seed)
        opt, trades = solve(inst)
        instances[seed] = (inst, opt)
        (OUT / f"instance{seed}.json").write_text(json.dumps({"instance": inst, "optimum": opt, "trades": trades},
                                                             ensure_ascii=False, indent=1), encoding="utf-8")
        hold = objective(inst, {})
        print(f"seed {seed}: NAV0={nav0(inst):.0f} optimum={opt:.2f} do-nothing={hold:.2f} "
              f"do-nothing-violations={len(violations(inst, {}))}", flush=True)
    if args.solve_only:
        return 0

    from faultline.llm import LLMError
    from faultline.run_eval import build_client, load_config

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    client = build_client(group, group.get("provider", "openrouter"), False)
    out = Path(args.out) if args.out else OUT / f"runs_{args.model_set}.jsonl"
    rows = []
    for seed, (inst, opt) in instances.items():
        for model in args.model:
            for mode in args.mode or ["direct", "code"]:
                print(f"seed={seed} {model:<24} {mode:<6} calling...", flush=True)
                error, bad, gap, tokens = None, [], None, 0
                try:
                    done = client.complete(
                        model=model,
                        messages=[{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": render(inst, mode)}],
                        temperature=defaults.get("temperature", 0.0),
                        max_tokens=int(defaults.get("max_tokens", 16000)),
                        seed=1,
                        reasoning_effort=None,
                    )
                    tokens = done.completion_tokens
                    save = OUT / "answers" / f"seed{seed}" / model.replace("/", "__")
                    save.mkdir(parents=True, exist_ok=True)
                    (save / f"{mode}.md").write_text(done.text, encoding="utf-8")
                    if mode == "direct":
                        raw = extract(done.text, "json")
                        if raw is None:
                            raise ValueError(f"no json block (finish_reason={done.finish_reason})")
                    else:
                        code = extract(done.text, "python")
                        if code is None:
                            raise ValueError(f"no python block (finish_reason={done.finish_reason})")
                        (save / "program.py").write_text(code, encoding="utf-8")
                        ran = subprocess.run([str(ENV_PY), str(save / "program.py")],
                                             capture_output=True, text=True, timeout=120, cwd=str(save))
                        lines = [ln for ln in ran.stdout.splitlines() if ln.strip()]
                        if ran.returncode != 0 or not lines:
                            raise ValueError(f"program failed rc={ran.returncode}: {ran.stderr.strip()[-200:]}")
                        raw = lines[-1]
                    trades = parse_trades(raw)
                    bad = violations(inst, trades)
                    if not bad:
                        gap = (objective(inst, trades) - opt) / opt
                except (LLMError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
                    error = f"{type(exc).__name__}: {exc}"[:300]
                row = Row(seed, model, mode, error is None and not bad, gap is not None and gap <= PASS_GAP,
                          gap, bad[:8], error, tokens)
                rows.append(row)
                status = ("ERROR " + error) if error else (f"INFEASIBLE {len(bad)}: {bad[:2]}" if bad
                                                           else f"feasible gap={gap:.3%}")
                print(f"seed={seed} {model:<24} {mode:<6} {status}", flush=True)
                with out.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")

    print()
    for mode in sorted({r.mode for r in rows}):
        sub = [r for r in rows if r.mode == mode]
        print(f"{mode}: qualified {sum(r.qualified for r in sub)}/{len(sub)}, "
              f"feasible {sum(r.feasible for r in sub)}/{len(sub)}, errors {sum(bool(r.error) for r in sub)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
