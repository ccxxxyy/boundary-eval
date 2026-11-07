
import re

files = [
    "600519.txt", "000333.txt", "300750.txt", "002594.txt", 
    "600900.txt", "000858.txt", "600309.txt", "000651.txt", 
    "600276.txt", "002415.txt", "601012.txt"
]

for filename in files:
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    
    print(f"==================== {filename} ====================")
    
    # Let's search for lines containing "合并利润表"
    # Find table header
    matches_inc = list(re.finditer(r'合并利润表', text))
    print(f"Profit table matches: {len(matches_inc)}")
    for m in matches_inc:
        pos = m.start()
        # check surrounding text for "营业"
        sub = text[pos:pos+2500]
        if "营业" in sub:
            print("--- PROFIT TABLE SNIPPET ---")
            print(sub[:1000])
            print("..." + "-"*30)
            break
            
    matches_cf = list(re.finditer(r'合并现金流量表', text))
    print(f"Cash flow table matches: {len(matches_cf)}")
    for m in matches_cf:
        pos = m.start()
        sub = text[pos:pos+3500]
        if "经营活动产生的现金流量净额" in sub or "购建固定资产" in sub:
            print("--- CASH FLOW TABLE SNIPPET ---")
            print(sub[:1500])
            print("..." + "-"*30)
            break
