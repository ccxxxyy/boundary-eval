import json, os
print(sorted(os.listdir('s3')))
print(json.load(open('s3/logs-003.json'))['bucket'])
