"""Long-tail accounting-knowledge pilot (Chinese CAS / CSRC rules).

Each item gives facts and terminology but NOT the governing rule. The model
must supply the classification from its own knowledge. Grading is exact-label
set matching. The `basis` note on each item cites the rule so a domain expert
can verify the reference answer before scaling.

    python probe_acct/pilot.py --set bailian --model deepseek-v4.1-flash --out probe_acct/results/pilot.jsonl
    python probe_acct/pilot.py --set gemini  --model gemini-3.5-flash     --out probe_acct/results/pilot.jsonl
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

SYSTEM = "你是中国注册会计师，精通企业会计准则(CAS)与证监会信息披露规则。只给出要求的分类标签，不要解释。"

# Each question: id, prompt (facts + allowed labels + output format, NO rule),
# answer dict {item_key: label}, basis (citation for the expert to verify).
QUESTIONS = [
    {
        "id": "q1_nonrecurring",
        "basis": "证监会《公开发行证券的公司信息披露解释性公告第1号——非经常性损益》",
        "labels": ["是", "否"],
        "answer": {"a": "是", "b": "是", "c": "否", "d": "是", "e": "是", "f": "是", "g": "是", "h": "否"},
        "prompt": """判断下列各项，对一家制造业上市公司而言，是否应计入“非经常性损益”。每项只回答“是”或“否”。

a. 处置一处不再使用的厂房（非流动性资产）产生的处置收益。
b. 公司收到的、越权审批或无正式批准文件的税收返还。
c. 计入当期损益、与公司正常经营业务密切相关、符合国家政策规定、按照一定标准定额或定量持续享受的政府补助。
d. 对单项金额重大的应收账款单独计提的坏账准备，本期因对方偿付而转回的部分。
e. 公司对外委托贷款取得的利息损益。
f. 采用公允价值模式后续计量的投资性房地产，本期公允价值变动产生的损益。
g. 与公司正常经营业务无关的或有事项产生的损益。
h. 公司因正常生产经营、按市场价格向关联方销售商品产生的毛利。

输出一个 ```json 代码块：{"a":"是/否","b":...,"c":...,"d":...,"e":...,"f":...,"g":...,"h":...}""",
    },
    {
        "id": "q2_fin_asset",
        "basis": "CAS 22 金融工具确认和计量：业务模式 + SPPI 测试",
        "labels": ["摊余成本", "FVOCI", "FVTPL"],
        "answer": {"a": "摊余成本", "b": "FVOCI", "c": "FVTPL", "d": "FVTPL", "e": "FVOCI"},
        "prompt": """把下列金融资产按 CAS 22 归入三类之一，用这三个确切标签作答：“摊余成本”“FVOCI”“FVTPL”。

a. 一笔企业债券，管理该资产的业务模式是“以收取合同现金流量为目标”；其合同现金流量在特定日期产生的仅为对本金和以未偿付本金为基础的利息的支付。
b. 一笔国债，业务模式是“既以收取合同现金流量为目标又以出售该金融资产为目标”；合同现金流量仅为本金和利息的支付。
c. 一笔债券，企业持有目的是短期买卖赚取差价（交易性），合同现金流量仅为本金和利息。
d. 一笔可转换公司债券投资（含转股权，现金流量与发行人股价挂钩，不满足仅为本金和利息）。
e. 一笔企业持有的非交易性权益工具投资，企业在初始确认时作出不可撤销的指定。

输出一个 ```json 代码块：{"a":"...","b":"...","c":"...","d":"...","e":"..."}""",
    },
    {
        "id": "q3_deferred_tax",
        "basis": "CAS 18 所得税：暂时性差异与递延确认（含商誉初始确认豁免）",
        "labels": ["递延所得税资产", "递延所得税负债", "不确认"],
        "answer": {"a": "递延所得税负债", "b": "递延所得税资产", "c": "不确认",
                   "d": "递延所得税资产", "e": "递延所得税负债"},
        "prompt": """判断下列各项按 CAS 18 应确认为哪一类，用这三个确切标签作答：“递延所得税资产”“递延所得税负债”“不确认”。假设未来很可能取得足够应纳税所得额。

a. 交易性金融资产期末公允价值高于其计税基础（账面价值大于计税基础）。
b. 本期按预计负债计提的产品质量保证费用，税法规定在实际发生时才准予税前扣除。
c. 非同一控制下企业合并中初始确认的商誉（其计税基础为零）。
d. 本期对存货计提的跌价准备，税法规定在实际发生损失时才准予扣除。
e. 采用公允价值模式计量的投资性房地产，本期公允价值上升使账面价值高于计税基础。

输出一个 ```json 代码块：{"a":"...","b":"...","c":"...","d":"...","e":"..."}""",
    },
]


def extract(text: str) -> dict:
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    if not blocks:
        raise ValueError("no json block")
    return json.loads(blocks[-1])


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", str(value)).replace("（", "(").replace("）", ")")


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
    save_root = HERE / "results" / "answers"
    save_root.mkdir(parents=True, exist_ok=True)

    for model in args.model:
        print(f"\n#### {model}", flush=True)
        grand_ok = grand_total = 0
        for q in QUESTIONS:
            row = {"model": model, "q": q["id"], "error": None, "items": {}}
            try:
                done = client.complete(
                    model=model,
                    messages=[{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": q["prompt"]}],
                    temperature=defaults.get("temperature", 0.0),
                    max_tokens=int(defaults.get("max_tokens", 16000)),
                    seed=1, reasoning_effort=None,
                )
                (save_root / f"{q['id']}_{model.replace('/', '__')}.md").write_text(
                    done.text, encoding="utf-8")
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
            wrong = {k: (i["got"], "应为", i["want"]) for k, i in row["items"].items() if not i["ok"]}
            print(f"  {q['id']:<16} {row['error'] or f'{n_ok}/{n}'}  错: {wrong}", flush=True)
        print(f"  TOTAL {grand_ok}/{grand_total}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
