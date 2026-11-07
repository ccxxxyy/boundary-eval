import json

path = "s3/reports-001.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

new_statement = {
    "sid": "DenyInsecure",
    "effect": "Deny",
    "principal": "*",
    "action": "s3:*",
    "resource": "reports-001/*",
    "condition": {
        "aws:SecureTransport": False
    }
}

if "policy" not in data:
    data["policy"] = {"statements": []}
if "statements" not in data["policy"]:
    data["policy"]["statements"] = []

# Check if DenyInsecure already exists or update/append
existing_sids = [stmt.get("sid") for stmt in data["policy"]["statements"]]
if "DenyInsecure" not in existing_sids:
    data["policy"]["statements"].append(new_statement)

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("UPDATED_CONFIG:")
with open(path, "r", encoding="utf-8") as f:
    print(f.read())
