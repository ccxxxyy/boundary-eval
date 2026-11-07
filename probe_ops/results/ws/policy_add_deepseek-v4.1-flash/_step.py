import json
from pathlib import Path

p = Path("s3/reports-001.json")
data = json.loads(p.read_text())

policy = data.setdefault("policy", {})
stmts = policy.setdefault("statements", [])

new_stmt = {
    "sid": "DenyInsecure",
    "effect": "Deny",
    "principal": "*",
    "action": "s3:*",
    "resource": "reports-001/*",
    "condition": {"aws:SecureTransport": False},
}

if any(s.get("sid") == "DenyInsecure" for s in stmts):
    print("DenyInsecure already present; no change")
else:
    stmts.append(new_stmt)
    data["policy"]["statements"] = stmts
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print("appended")

print("---- VERIFY ----")
print(json.dumps(json.loads(p.read_text()), indent=2, ensure_ascii=False))
