import json
import os

filepath = os.path.join("s3", "reports-001.json")

with open(filepath, "r", encoding="utf-8") as f:
    data = json.load(f)

new_notification = {
    "prefix": "images/",
    "queue": "thumbnails-q"
}

if "notifications" not in data:
    data["notifications"] = []

data["notifications"].append(new_notification)

with open(filepath, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("UPDATED CONFIG:")
print(json.dumps(data, indent=2, ensure_ascii=False))
