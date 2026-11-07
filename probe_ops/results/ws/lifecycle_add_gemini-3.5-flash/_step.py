import json

path = "s3/reports-001.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

new_rule = {
    "id": "expire-tmp",
    "prefix": "tmp/",
    "days": 7
}

# Ensure lifecycle list exists and append the new rule if not already present
if "lifecycle" not in data or not isinstance(data["lifecycle"], list):
    data["lifecycle"] = []

# Check if rule with id "expire-tmp" already exists
exists = False
for rule in data["lifecycle"]:
    if rule.get("id") == "expire-tmp":
        rule.update(new_rule)
        exists = True
        break

if not exists:
    data["lifecycle"].append(new_rule)

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("Updated config:")
print(json.dumps(data, indent=2, ensure_ascii=False))
