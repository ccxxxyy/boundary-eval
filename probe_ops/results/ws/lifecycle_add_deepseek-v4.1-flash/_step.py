from pathlib import Path
import json, os, shutil

p = Path("s3/reports-001.json")
data = json.loads(p.read_text())

lifecycle = data.setdefault("lifecycle", [])
if any(r.get("id") == "expire-tmp" for r in lifecycle):
    print("already exists, no change")
else:
    lifecycle.append({"id": "expire-tmp", "prefix": "tmp/", "days": 7})
    backup = p.with_suffix(".json.bak")
    shutil.copy2(p, backup)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, p)
    print("updated; backup at", backup)

print(json.dumps(json.loads(p.read_text()), indent=2, ensure_ascii=False))
