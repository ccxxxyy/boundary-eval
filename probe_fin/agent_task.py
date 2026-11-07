"""Long-horizon probe: 11 annual reports on disk, the model works through them with Python.

    python probe_fin/agent_task.py --set bailian --model kimi-k3.1-pro --out probe_fin/results/agent_bailian.jsonl

Each turn the model sends one ```python block; it runs in a fresh process with the
workspace as cwd, and the (truncated) output comes back. It finishes by sending a
```json block containing "final". Graded per company against multi_truth.py.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from faultline.llm import LLMError  # noqa: E402
from faultline.run_eval import build_client, load_config  # noqa: E402
from multi_truth import NAMES, ranking, truth  # noqa: E402

SANDBOX_PY = HERE.parent / "probe_opt" / "env" / "Scripts" / "python.exe"
MAX_STEPS = 50
MAX_OUTPUT = 6000
TOL = 0.005

TASK = """你在一个工作目录里工作，目录下有 11 家 A 股公司 2025 年年度报告的全文文本（由 PDF 转换，每页以“=== 第N页 ===”开头），文件名为 `<股票代码>.txt`：

{listing}

任务：对每家公司，依据其年报中的**合并**财务报表，给出：
- `revenue`：2025 年度合并利润表中的“营业收入”（是“营业收入”这一行，不是“营业总收入”），单位：元；
- `fcf`：2025 年度自由现金流 = 合并现金流量表“经营活动产生的现金流量净额” − “购建固定资产、无形资产和其他长期资产支付的现金”，单位：元。

注意各报告的金额单位可能不同（元/千元/万元），答案一律换算为元。然后把 11 家公司按 `fcf` 从高到低排序。

工作方式：每一轮你回复且只回复一个 ```python 代码块。它会在工作目录下用一个全新的 Python 3.11 进程执行（装有 numpy，无网络，限时 120 秒，变量不跨轮保留，但你可以把中间结果写到文件里），标准输出和错误会返回给你（超过 {max_output} 字符会被截断）。你最多有 {max_steps} 轮。

完成后，回复一个 ```json 代码块（不要再附带 python 代码块），格式：
{{"final": {{"results": {{"600519": {{"revenue": 数值, "fcf": 数值}}, ...全部 11 家...}}, "ranking": ["代码", ...]}}}}
数值为纯数字（元），不要逗号或单位。"""

SYSTEM = "你是严谨的证券分析师，擅长用 Python 处理文本数据。严格按要求的格式作答。"


def setup_workspace(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    for code in NAMES:
        shutil.copy(HERE / "reports" / f"{code}.txt", path / f"{code}.txt")


def run_code(code: str, cwd: Path) -> str:
    script = cwd / "_step.py"
    script.write_text(code, encoding="utf-8")
    try:
        done = subprocess.run([str(SANDBOX_PY), "-X", "utf8", script.name], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120, cwd=str(cwd))
        out = (done.stdout or "") + (("\n[stderr]\n" + done.stderr) if done.stderr else "")
    except subprocess.TimeoutExpired:
        out = "[timeout after 120s]"
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n...[truncated, {len(out)} chars total]"
    return out or "[no output]"


def grade(final: dict) -> dict:
    want = truth()
    got = final.get("results", {}) if isinstance(final, dict) else {}
    per = {}
    for code, w in want.items():
        g = got.get(code) or {}
        ok = {}
        for key in ("revenue", "fcf"):
            try:
                ok[key] = abs(float(g.get(key)) - w[key]) <= TOL * abs(w[key])
            except (TypeError, ValueError):
                ok[key] = False
        per[code] = {"ok": all(ok.values()), **{k: ok[k] for k in ok},
                     "got": g, "want": {k: round(v, 2) for k, v in w.items()}}
    return {"companies_ok": sum(p["ok"] for p in per.values()), "ranking_ok": final.get("ranking") == ranking(),
            "per": per}


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
    listing = "\n".join(f"- {code}.txt：{name}" for code, name in NAMES.items())
    prompt = TASK.format(listing=listing, max_output=MAX_OUTPUT, max_steps=MAX_STEPS)

    for model in args.model:
        work = HERE / "results" / "agent_ws" / model.replace("/", "__")
        setup_workspace(work)
        transcript = work.parent / f"{model.replace('/', '__')}.transcript.md"
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        final, error, steps = None, None, 0
        log = [f"# {model}\n"]
        while steps < MAX_STEPS:
            try:
                done = client.complete(model=model, messages=messages,
                                       temperature=defaults.get("temperature", 0.0),
                                       max_tokens=int(defaults.get("max_tokens", 16000)),
                                       seed=1, reasoning_effort=None)
            except LLMError as exc:
                error = f"api error at step {steps}: {exc}"[:300]
                break
            text = done.text or ""
            messages.append({"role": "assistant", "content": text})
            log.append(f"\n## assistant (step {steps})\n{text}\n")
            finals = re.findall(r"```json\s*\n(.*?)```", text, re.S)
            codes = re.findall(r"```python\s*\n(.*?)```", text, re.S)
            if finals and not codes:
                try:
                    final = json.loads(finals[-1])["final"]
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    error = f"bad final json: {exc}"
                break
            if not codes:
                observation = "未找到 ```python 代码块或最终 ```json 答案，请按要求格式回复。"
            else:
                steps += 1
                observation = run_code(codes[0], work)
            print(f"{model:<24} step {steps:>2}: {observation[:90]!r}", flush=True)
            log.append(f"\n## output\n```\n{observation}\n```\n")
            messages.append({"role": "user", "content": f"执行结果：\n```\n{observation}\n```\n（已用 {steps}/{MAX_STEPS} 轮）"})
        else:
            error = "ran out of steps"
        transcript.write_text("".join(log), encoding="utf-8")
        result = grade(final) if final else {"companies_ok": 0, "ranking_ok": False, "per": {}}
        row = {"model": model, "steps": steps, "error": error, **result}
        with Path(args.out).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        wrong = [c for c, p in result["per"].items() if not p["ok"]]
        print(f"{model:<24} DONE steps={steps} error={error} companies_ok={result['companies_ok']}/11 "
              f"ranking_ok={result['ranking_ok']} wrong={wrong}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
