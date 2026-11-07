"""Download 2025 annual reports from cninfo and convert them to page-tagged text.

    python probe_fin/fetch.py 600519 000333 300750
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import fitz

HERE = Path(__file__).resolve().parent
REPORTS = HERE / "reports"
UA = {"User-Agent": "Mozilla/5.0"}


def post(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def org_id(code: str) -> tuple[str, str]:
    hits = post("http://www.cninfo.com.cn/new/information/topSearch/query", {"keyWord": code, "maxNum": 10})
    for hit in hits:
        if hit["code"] == code:
            return hit["orgId"], hit["zwjc"]
    raise SystemExit(f"no orgId for {code}")


def fetch(code: str) -> None:
    org, name = org_id(code)
    column = "sse" if code.startswith("6") else "szse"
    result = post("http://www.cninfo.com.cn/new/hisAnnouncement/query", {
        "stock": f"{code},{org}", "tabName": "fulltext", "pageSize": "30", "pageNum": "1",
        "column": column, "category": "category_ndbg_szsh;", "seDate": "2026-01-01~2026-11-07",
    })
    picks = [a for a in result["announcements"] or []
             if "2025年年度报告" in a["announcementTitle"].replace("<em>", "").replace("</em>", "")
             and "摘要" not in a["announcementTitle"] and "英文" not in a["announcementTitle"]]
    if not picks:
        raise SystemExit(f"no 2025 annual report for {code}")
    ann = picks[0]
    REPORTS.mkdir(parents=True, exist_ok=True)
    pdf = REPORTS / f"{code}.pdf"
    req = urllib.request.Request("http://static.cninfo.com.cn/" + ann["adjunctUrl"], headers=UA)
    with urllib.request.urlopen(req, timeout=300) as resp:
        pdf.write_bytes(resp.read())
    doc = fitz.open(pdf)
    pages = [f"=== 第{i + 1}页 ===\n{page.get_text()}" for i, page in enumerate(doc)]
    text = "\n".join(pages)
    (REPORTS / f"{code}.txt").write_text(text, encoding="utf-8")
    print(f"{code} {name} {ann['announcementTitle']} pages={len(doc)} chars={len(text)}")


if __name__ == "__main__":
    for code in sys.argv[1:]:
        fetch(code)
