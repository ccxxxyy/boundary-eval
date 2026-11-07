import os
import json

file_path = os.path.join("s3", "logs-003.json")
with open(file_path, "r", encoding="utf-8") as f:
    content = json.load(f)

print("Created content:")
print(json.dumps(content, indent=2))
