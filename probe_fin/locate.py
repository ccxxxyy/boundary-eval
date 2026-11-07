"""Print every occurrence of the key line items with page number and the next lines, for manual ground truth."""

import re
import sys
from pathlib import Path

REPORTS = Path(__file__).resolve().parent / "reports"
LABELS = [r"营业收入", r"经营活动产生的现金流量净额", r"购建固定资产", r"利润表|现金流量表"]
sys.stdout = open(Path(__file__).resolve().parent / "locate_out.txt", "w", encoding="utf-8")

for code in sys.argv[1:]:
    lines = (REPORTS / f"{code}.txt").read_text(encoding="utf-8").splitlines()
    page = 0
    print(f"################ {code}")
    for i, line in enumerate(lines):
        m = re.match(r"=== 第(\d+)页 ===", line)
        if m:
            page = int(m.group(1))
            continue
        if re.search(LABELS[0], line) and not re.search(r"其中：营业收入|^\s*营业收入\s*$|一、营业总收入|一、营业收入", line):
            continue
        if any(re.search(p, line) for p in LABELS):
            nxt = " | ".join(s.strip() for s in lines[i + 1:i + 5])
            print(f"p{page} L{i + 1}: {line.strip()[:40]} -> {nxt[:120]}")
