import json

path = "s3/reports-001.json"
with open(path, "r", encoding="utf-8") as f:
    cfg = json.load(f)

new_notification = {"prefix": "images/", "queue": "thumbnails-q"}
notifications = cfg.setdefault("notifications", [])

if new_notification not in notifications:
    notifications.append(new_notification)

with open(path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write("\n")

with open(path, "r", encoding="utf-8") as f:
    print(f.read())
