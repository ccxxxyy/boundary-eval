"""Harder no-tool reasoning: long state traces. Truth from the same simulator.

    python probe_reason/hard.py --set bailian --model deepseek-v4.1-flash --out probe_reason/results/hard.jsonl
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
    "你必须只凭推理作答。禁止编写或运行任何代码（包括伪代码当计算器）。"
    "逐步心算时不要跳步。最后只输出题目要求的 ```json 代码块。"
)

# --- warehouse: 8 bins, 26 steps, several skips and branches ---

BINS = ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"]
WAREHOUSE_START = [6, 1, 8, 3, 0, 4, 2, 5]


def apply_wh(state: list[int], op: tuple) -> None:
    kind = op[0]
    if kind == "move":
        src, dst, n = op[1], op[2], op[3]
        if state[src] < n:
            return
        state[src] -= n
        state[dst] += n
    elif kind == "add":
        state[op[1]] += op[2]
    elif kind == "if_ge":
        i, thresh, yes, no = op[1], op[2], op[3], op[4]
        apply_wh(state, yes if state[i] >= thresh else no)
    elif kind == "if_even":
        i, yes, no = op[1], op[2], op[3]
        apply_wh(state, yes if state[i] % 2 == 0 else no)
    elif kind == "cap_add":
        i, n, cap = op[1], op[2], op[3]
        if state[i] + n <= cap:
            state[i] += n
    elif kind == "give_half_down":
        src, dst = op[1], op[2]
        n = state[src] // 2
        if n == 0:
            return
        state[src] -= n
        state[dst] += n
    elif kind == "swap":
        i, j = op[1], op[2]
        state[i], state[j] = state[j], state[i]


WAREHOUSE_OPS: list[tuple] = [
    ("move", 0, 1, 2),
    ("add", 4, 3),
    ("if_ge", 0, 5, ("move", 0, 2, 3), ("add", 7, 1)),
    ("move", 2, 3, 4),
    ("if_even", 1, ("add", 1, 1), ("move", 1, 5, 1)),
    ("move", 5, 6, 5),
    ("give_half_down", 2, 4),
    ("move", 7, 0, 4),
    ("if_ge", 3, 6, ("swap", 3, 6), ("add", 3, 2)),
    ("move", 1, 7, 3),
    ("cap_add", 4, 4, 10),
    ("move", 6, 2, 2),
    ("if_even", 0, ("give_half_down", 0, 5), ("add", 0, 3)),
    ("move", 4, 1, 6),
    ("add", 7, 2),
    ("if_ge", 5, 4, ("move", 5, 3, 2), ("move", 3, 5, 1)),
    ("move", 2, 7, 5),
    ("swap", 1, 4),
    ("move", 0, 6, 1),
    ("cap_add", 6, 3, 8),
    ("if_even", 7, ("move", 7, 2, 2), ("give_half_down", 7, 0)),
    ("move", 3, 1, 4),
    ("add", 2, 1),
    ("if_ge", 1, 8, ("move", 1, 5, 3), ("add", 5, 2)),
    ("move", 6, 3, 2),
    ("give_half_down", 5, 7),
]


def render_wh_prompt() -> str:
    names = BINS
    lines = [
        "八个库位 W1–W8 的初始件数是：",
        "W1=6, W2=1, W3=8, W4=3, W5=0, W6=4, W7=2, W8=5。",
        "按顺序执行 26 条指令。通用规则：",
        "- 「从 X 移 n 到 Y」：若 X 当前件数 < n，则整条跳过。",
        "- 「X 的一半（向下取整）给 Y」：n = floor(X当前/2)；若 n=0 则跳过，否则 X 减 n、Y 加 n。",
        "- 「X 加 n，但上限 cap」：仅当 X+n ≤ cap 时才加，否则跳过。",
        "- 条件看的是**执行该条时**的当前件数。",
        "",
        "指令：",
    ]
    for i, op in enumerate(WAREHOUSE_OPS, 1):
        lines.append(f"{i}. {describe_op(op, names)}")
    lines.append(
        "给出全部执行完后八个库位的件数。"
        '输出 ```json：{"W1":n,"W2":n,"W3":n,"W4":n,"W5":n,"W6":n,"W7":n,"W8":n}'
    )
    return "\n".join(lines)


def describe_op(op: tuple, names: list[str]) -> str:
    kind = op[0]
    if kind == "move":
        return f"从 {names[op[1]]} 移 {op[3]} 到 {names[op[2]]}"
    if kind == "add":
        return f"{names[op[1]]} 加 {op[2]}"
    if kind == "swap":
        return f"交换 {names[op[1]]} 与 {names[op[2]]} 的件数"
    if kind == "give_half_down":
        return f"把 {names[op[1]]} 的一半（向下取整）给 {names[op[2]]}"
    if kind == "cap_add":
        return f"{names[op[1]]} 加 {op[2]}，但 {names[op[1]]} 不得超过 {op[3]}"
    if kind == "if_ge":
        return (
            f"若 {names[op[1]]} ≥ {op[2]}，则：{describe_op(op[3], names)}；"
            f"否则：{describe_op(op[4], names)}"
        )
    if kind == "if_even":
        return (
            f"若 {names[op[1]]} 为偶数，则：{describe_op(op[2], names)}；"
            f"否则：{describe_op(op[3], names)}"
        )
    raise ValueError(op)


def simulate_warehouse() -> dict[str, int]:
    state = list(WAREHOUSE_START)
    for op in WAREHOUSE_OPS:
        apply_wh(state, op)
    return {name: n for name, n in zip(BINS, state)}


# --- trading tape: skip vs fill, fee floor, cash/inventory ---

TRADES = [
    ("buy", 12, 80),
    ("sell", 5, 90),
    ("buy", 40, 75),
    ("sell", 20, 88),
    ("buy", 8, 70),
    ("sell", 15, 95),
    ("buy", 3, 200),
    ("sell", 10, 60),
    ("buy", 25, 50),
    ("sell", 30, 55),
    ("buy", 7, 48),
    ("sell", 6, 120),
    ("buy", 18, 52),
    ("sell", 9, 51),
    ("buy", 11, 49),
    ("sell", 40, 47),
    ("buy", 4, 46),
    ("sell", 2, 100),
    ("buy", 15, 45),
    ("sell", 8, 44),
]


def simulate_tape() -> dict[str, int]:
    cash, inv, skipped, filled = 10_000, 0, 0, 0
    for side, qty, price in TRADES:
        gross = qty * price
        fee = gross * 2 // 100  # 2%, floor
        if side == "buy":
            need = gross + fee
            if cash < need:
                skipped += 1
                continue
            cash -= need
            inv += qty
            filled += 1
        else:
            if inv < qty:
                skipped += 1
                continue
            cash += gross - fee
            inv -= qty
            filled += 1
    return {"cash": cash, "inventory": inv, "skipped": skipped, "filled": filled}


def render_tape_prompt() -> str:
    lines = [
        "你是清算员，手工过账。期初现金 10000，库存 0。共 20 笔成交意图，必须按顺序处理。",
        "规则：",
        "- 买：支付 数量×单价，另加 2% 手续费（手续费对「数量×单价」向下取整到整数）。现金不足则**整笔跳过**，库存不变。",
        "- 卖：收入 数量×单价，减去 2% 手续费（同样向下取整）。库存不足则**整笔跳过**，现金不变。",
        "- 没有部分成交。跳过不改变任何数字。",
        "",
        "顺序（side, qty, price）：",
    ]
    for i, (side, qty, price) in enumerate(TRADES, 1):
        tag = "买" if side == "buy" else "卖"
        lines.append(f"{i}. {tag} {qty} @ {price}")
    lines.append(
        "全部处理完后输出 ```json："
        '{"cash":整数,"inventory":整数,"skipped":跳过笔数,"filled":成交笔数}'
    )
    return "\n".join(lines)


# --- ring of 9 stations, 22 token moves ---

RING_OPS = [
    ("fwd", 3),
    ("if_load_ge", 4, ("drop", 2), ("pick", 3)),
    ("fwd", 1),
    ("pick", 5),
    ("fwd", 4),
    ("drop", 4),
    ("if_token_even", ("fwd", 2), ("fwd", 1)),
    ("pick", 2),
    ("fwd", 3),
    ("if_load_ge", 6, ("drop", 3), ("pick", 1)),
    ("fwd", 2),
    ("drop", 5),
    ("fwd", 5),
    ("pick", 4),
    ("if_token_even", ("drop", 1), ("fwd", 2)),
    ("fwd", 1),
    ("drop", 2),
    ("fwd", 6),
    ("pick", 3),
    ("fwd", 2),
    ("if_load_ge", 5, ("drop", 4), ("drop", 1)),
    ("fwd", 3),
]


def simulate_ring() -> dict[str, int]:
    # 9 stations with initial piles; token starts at station 0 carrying 0
    pile = [4, 1, 7, 0, 6, 2, 8, 3, 5]
    pos, load = 0, 0
    skipped = 0

    def apply(op: tuple) -> None:
        nonlocal pos, load, skipped
        kind = op[0]
        if kind == "fwd":
            pos = (pos + op[1]) % 9
        elif kind == "pick":
            n = op[1]
            if pile[pos] < n:
                skipped += 1
                return
            pile[pos] -= n
            load += n
        elif kind == "drop":
            n = op[1]
            if load < n:
                skipped += 1
                return
            load -= n
            pile[pos] += n
        elif kind == "if_load_ge":
            apply(op[2] if load >= op[1] else op[3])
        elif kind == "if_token_even":
            apply(op[1] if load % 2 == 0 else op[2])

    for op in RING_OPS:
        apply(op)
    return {
        "pos": pos,
        "load": load,
        "skipped": skipped,
        "pile_sum": sum(pile),
        "S0": pile[0],
        "S4": pile[4],
        "S8": pile[8],
    }


def render_ring_prompt() -> str:
    lines = [
        "一条环形传送线有 9 个工位 S0–S8（S8 的下一个是 S0）。",
        "各工位地上的件数初始为：S0=4, S1=1, S2=7, S3=0, S4=6, S5=2, S6=8, S7=3, S8=5。",
        "一辆小车从 S0 出发，车上载货 load=0。按顺序执行 22 条指令。",
        "规则：",
        "- fwd k：小车沿环向前移动 k 个工位。",
        "- pick n：若当前工位地上件数 < n，则跳过；否则地上减 n，load 加 n。",
        "- drop n：若 load < n，则跳过；否则 load 减 n，当前工位地上加 n。",
        "- 条件看执行该条时的 load。",
        "",
        "指令：",
    ]
    for i, op in enumerate(RING_OPS, 1):
        lines.append(f"{i}. {describe_ring(op)}")
    lines.append(
        "结束后输出 ```json："
        '{"pos":当前工位编号0-8,"load":车上件数,"skipped":跳过的pick或drop次数,'
        '"pile_sum":九个工位地上件数之和,"S0":n,"S4":n,"S8":n}'
    )
    return "\n".join(lines)


def describe_ring(op: tuple) -> str:
    kind = op[0]
    if kind == "fwd":
        return f"fwd {op[1]}"
    if kind == "pick":
        return f"pick {op[1]}"
    if kind == "drop":
        return f"drop {op[1]}"
    if kind == "if_load_ge":
        return f"若 load ≥ {op[1]}，则 {describe_ring(op[2])}；否则 {describe_ring(op[3])}"
    if kind == "if_token_even":
        return f"若 load 为偶数，则 {describe_ring(op[1])}；否则 {describe_ring(op[2])}"
    raise ValueError(op)


def extract(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    if not blocks:
        raise ValueError("no json block")
    return json.loads(blocks[-1])


def grade(got: dict, want: dict) -> dict:
    items = {}
    for key, expected in want.items():
        raw = got.get(key)
        try:
            ok = int(raw) == int(expected)
        except (TypeError, ValueError):
            ok = False
        items[key] = {"got": raw, "want": expected, "ok": ok}
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", dest="model_set", required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    tasks = [
        ("t_warehouse", render_wh_prompt(), simulate_warehouse()),
        ("t_tape", render_tape_prompt(), simulate_tape()),
        ("t_ring", render_ring_prompt(), simulate_ring()),
    ]
    print("truth:", json.dumps({i: w for i, _, w in tasks}, ensure_ascii=False), flush=True)

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    client = build_client(group, group.get("provider", "openrouter"), False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    save = HERE / "results" / "hard_answers"
    save.mkdir(parents=True, exist_ok=True)

    for model in args.model:
        print(f"\n#### {model}", flush=True)
        n_ok = n_total = 0
        for tid, prompt, want in tasks:
            row = {"model": model, "task": tid, "error": None, "items": {}}
            try:
                done = client.complete(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=defaults.get("temperature", 0.0),
                    max_tokens=int(defaults.get("max_tokens", 16000)),
                    seed=1,
                    reasoning_effort=None,
                )
                (save / f"{tid}_{model.replace('/', '__')}.md").write_text(
                    done.text, encoding="utf-8"
                )
                got = extract(done.text)
                row["items"] = grade(got, want)
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if row["error"]:
                print(f"  {tid:<14} ERROR {row['error']}", flush=True)
                continue
            ok = all(i["ok"] for i in row["items"].values())
            n_total += 1
            n_ok += int(ok)
            wrong = {k: (i["got"], i["want"]) for k, i in row["items"].items() if not i["ok"]}
            print(f"  {tid:<14} {'OK' if ok else 'WRONG'}  {wrong or ''}", flush=True)
        print(f"  tasks {n_ok}/{n_total}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
