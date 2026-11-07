"""No-tool reasoning pilot: unique answers computed by enumeration / simulation.

The model is told not to write code. Grading reads only the JSON. Truth comes
from reference() in this file, so the tasks are solvable and the grader is
checked against a passing input.

    python probe_reason/pilot.py --set bailian --model deepseek-v4.1-flash --out probe_reason/results/pilot.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import permutations, product
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from faultline.llm import LLMError  # noqa: E402
from faultline.run_eval import build_client, load_config  # noqa: E402

SYSTEM = (
    "你必须只凭推理作答。禁止编写或运行任何代码（包括伪代码当计算器）。"
    "最后只输出题目要求的 ```json 代码块。"
)

DAYS = ["周一", "周二", "周三", "周四", "周五"]
PEOPLE = ["E17", "E29", "E33", "E41", "E58"]


def roster_ok(assign: tuple[str, ...]) -> bool:
    pos = {p: i for i, p in enumerate(assign)}
    if pos["E17"] in (0, 1):
        return False
    if abs(pos["E29"] - pos["E33"]) != 1:
        return False
    if not (pos["E41"] < pos["E58"]):
        return False
    if pos["E58"] == 4:
        return False
    if assign[2] in ("E17", "E41"):
        return False
    if pos["E29"] == 3:
        return False
    if pos["E33"] == 0:
        return False
    if assign[4] != "E17":
        return False
    if pos["E29"] == 1:
        return False
    if pos["E58"] == 1:
        return False
    return True


def simulate_boxes() -> dict[str, int]:
    boxes = {"A": 7, "B": 2, "C": 0, "D": 5}

    def move(src: str, dst: str, n: int) -> None:
        if boxes[src] < n:
            return
        boxes[src] -= n
        boxes[dst] += n

    move("A", "B", 3)
    move("B", "C", 4)
    if boxes["C"] > boxes["D"]:
        move("C", "D", 2)
    else:
        move("D", "C", 1)
    move("D", "A", 3)
    move("C", "B", 2)
    if boxes["A"] % 2 == 0:
        boxes["A"] *= 2
    else:
        boxes["B"] += 1
    move("B", "D", 6)
    move("A", "C", 5)
    if boxes["B"] == boxes["D"]:
        move("A", "B", 1)
    else:
        move("C", "A", 2)
    move("D", "C", 4)
    if boxes["A"] >= 3 and boxes["C"] + 3 <= 10:
        move("A", "C", 3)
    move("C", "B", 1)
    return boxes


def best_plan() -> dict[str, int]:
    tops: list[tuple[int, int, int, int]] = []
    for a, b, c in product(range(0, 16), range(0, 16), range(0, 16)):
        if 8 * a + 5 * b + 3 * c > 47:
            continue
        if 2 * a + 4 * b + 6 * c > 38:
            continue
        if a + b + c < 8:
            continue
        if a % 2:
            continue
        if b % 3:
            continue
        if c < 1:
            continue
        if a < 2:
            continue
        if c > 4 and a < 5:
            continue
        leftover_h = 47 - (8 * a + 5 * b + 3 * c)
        if leftover_h > 3:
            continue
        score = 4 * a + 5 * b + 7 * c
        tops.append((score, a, b, c))
    mx = max(x[0] for x in tops)
    best = [x for x in tops if x[0] == mx]
    assert len(best) == 1, best
    _, a, b, c = best[0]
    return {"jia": a, "yi": b, "bing": c, "score": mx}


def reference_roster() -> dict[str, str]:
    sols = [a for a in permutations(PEOPLE) if roster_ok(a)]
    assert len(sols) == 1, sols
    return dict(zip(DAYS, sols[0]))


TASKS = [
    {
        "id": "t_roster",
        "want": None,  # filled at runtime from reference
        "prompt": """排一张唯一的值班表。5 名员工 E17、E29、E33、E41、E58，5 个工作日周一至周五，每人值且仅值一天，每天恰好一人。

约束（全部要满足）：
1. E17 不在周一、不在周二。
2. E29 与 E33 的值班日必须相邻（例如周二和周三）。
3. E41 的值班日必须严格早于 E58。
4. E58 不在周五。
5. 周三不是 E17，也不是 E41。
6. E29 不在周四，也不在周二。
7. E33 不在周一。
8. 周五必须是 E17。
9. E58 不在周二。

输出一个 ```json 代码块，五个键为“周一”…“周五”，值为工号字符串，例如 {"周一":"E..","周二":"E..","周三":"E..","周四":"E..","周五":"E.."}。
""",
    },
    {
        "id": "t_boxes",
        "want": None,
        "prompt": """四个箱子 A、B、C、D 的初始数量为 A=7、B=2、C=0、D=5。按顺序执行下列指令。规则：
- 任何一次“从 X 移 n 到 Y”，若 X 当前数量 < n，则**整条指令跳过**（其他箱子不变）。
- 指令按编号 1→12 执行，每条看的是执行到该条时的当前数量。

1. 从 A 移 3 到 B
2. 从 B 移 4 到 C
3. 若此时 C > D，从 C 移 2 到 D；否则从 D 移 1 到 C
4. 从 D 移 3 到 A
5. 从 C 移 2 到 B
6. 若此时 A 为偶数，把 A 变成原来的 2 倍；否则 B 加 1
7. 从 B 移 6 到 D
8. 从 A 移 5 到 C
9. 若此时 B 等于 D，从 A 移 1 到 B；否则从 C 移 2 到 A
10. 从 D 移 4 到 C
11. 仅当（A ≥ 3 且 C+3 ≤ 10）时，从 A 移 3 到 C；否则跳过
12. 从 C 移 1 到 B

给出执行完全部指令后四个箱子的数量。输出 ```json：{"A":整数,"B":整数,"C":整数,"D":整数}
""",
    },
    {
        "id": "t_plan",
        "want": None,
        "prompt": """一个车间本周只生产甲、乙、丙三种产品，产量为非负整数（乙可以为 0）。要同时满足：

- 机器工时：8×甲 + 5×乙 + 3×丙 ≤ 47
- 人工工时：2×甲 + 4×乙 + 6×丙 ≤ 38
- 甲+乙+丙 ≥ 8
- 甲为偶数，且甲 ≥ 2
- 乙为 3 的倍数（0、3、6…）
- 丙 ≥ 1；并且若丙 > 4，则甲必须 ≥ 5
- 未使用的机器工时（47 减去实际机器工时）不得超过 3
- 在所有可行方案中，使目标 4×甲 + 5×乙 + 7×丙 **最大**。最大方案是唯一的。

输出 ```json：{"jia":甲产量,"yi":乙产量,"bing":丙产量,"score":目标值}
""",
    },
]


def extract(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    if not blocks:
        raise ValueError("no json block")
    return json.loads(blocks[-1])


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", str(value))


def grade_item(got: dict, want: dict) -> dict:
    items = {}
    for key, expected in want.items():
        raw = got.get(key)
        if isinstance(expected, int):
            try:
                ok = int(raw) == expected
            except (TypeError, ValueError):
                ok = False
        else:
            ok = _norm(raw) == _norm(expected)
        items[key] = {"got": raw, "want": expected, "ok": ok}
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", dest="model_set", required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    wants = {
        "t_roster": reference_roster(),
        "t_boxes": simulate_boxes(),
        "t_plan": best_plan(),
    }
    print("truth:", json.dumps(wants, ensure_ascii=False), flush=True)

    config = load_config()
    group = config[args.model_set]
    defaults = {**config.get("defaults", {}), **group.get("defaults", {})}
    client = build_client(group, group.get("provider", "openrouter"), False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_root = HERE / "results" / "answers"
    save_root.mkdir(parents=True, exist_ok=True)

    for model in args.model:
        print(f"\n#### {model}", flush=True)
        n_ok = n_total = 0
        for task in TASKS:
            want = wants[task["id"]]
            row = {"model": model, "task": task["id"], "error": None, "items": {}}
            try:
                done = client.complete(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": task["prompt"]},
                    ],
                    temperature=defaults.get("temperature", 0.0),
                    max_tokens=int(defaults.get("max_tokens", 16000)),
                    seed=1,
                    reasoning_effort=None,
                )
                (save_root / f"{task['id']}_{model.replace('/', '__')}.md").write_text(
                    done.text, encoding="utf-8"
                )
                got = extract(done.text)
                row["items"] = grade_item(got, want)
            except (LLMError, ValueError, json.JSONDecodeError) as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if row["error"]:
                print(f"  {task['id']:<12} ERROR {row['error']}", flush=True)
                continue
            ok = all(i["ok"] for i in row["items"].values())
            n_total += 1
            n_ok += int(ok)
            wrong = {
                k: (i["got"], i["want"])
                for k, i in row["items"].items()
                if not i["ok"]
            }
            print(
                f"  {task['id']:<12} {'OK' if ok else 'WRONG'}  {wrong or ''}",
                flush=True,
            )
        print(f"  tasks {n_ok}/{n_total}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
