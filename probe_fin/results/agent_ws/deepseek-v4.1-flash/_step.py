import re
t=re.sub(r"\s+","",open("000651.txt",encoding="utf-8",errors="ignore").read())
for m in re.finditer("经营活动产生的现金流量净额",t):
    print("-- at",m.start(),"--")
    print(t[max(0,m.start()-180):m.start()+140])
