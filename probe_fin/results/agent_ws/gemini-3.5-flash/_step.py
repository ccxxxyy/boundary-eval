# Look at line 123 of 比亚迪 (002594):
# "财务附注中报表的单位为：千元" -> So the unit of financial statements in BYD 002594 is 千元!
# Let's verify:
# In summary table:
# Revenue: 803,964,958,000.00 元 = 803,964,958 千元
# Net OP Cash Flow: 59,135,544,000.00 元 = 59,135,544 千元
# CaPex: 156,807,853 千元 = 156,807,853,000.00 元

# Now, let's write a python script to calculate revenue, op_cf, capex, fcf for ALL 11 companies and print them clearly.

data = [
    {
        "code": "600519", "name": "贵州茅台",
        "unit": 1, # 元
        "revenue": 168838102514.79,
        "op_cf": 61522204989.35,
        "capex": 3127594916.41
    },
    {
        "code": "000333", "name": "美的集团",
        "unit": 1000, # 千元
        "revenue": 456451731 * 1000,
        "op_cf": 53345930 * 1000,
        "capex": 11141889 * 1000
    },
    {
        "code": "300750", "name": "宁德时代",
        "unit": 1000, # 千元
        "revenue": 423701834 * 1000,
        "op_cf": 133219982 * 1000,
        "capex": 42344558 * 1000
    },
    {
        "code": "002594", "name": "比亚迪",
        "unit": 1000, # 千元
        "revenue": 803964958 * 1000,
        "op_cf": 59135544 * 1000,
        "capex": 156807853 * 1000
    },
    {
        "code": "600900", "name": "长江电力",
        "unit": 1, # 元
        "revenue": 86241940222.20,
        "op_cf": 60562925570.41,
        "capex": 18488466859.29
    },
    {
        "code": "000858", "name": "五粮液",
        "unit": 1, # 元
        "revenue": 40528509770.23,
        "op_cf": 29706259919.13,
        "capex": 1967407316.36
    },
    {
        "code": "600309", "name": "万华化学",
        "unit": 1, # 元
        "revenue": 203234573814.42,
        "op_cf": 33105189455.82,
        "capex": 30711201211.89
    },
    {
        "code": "000651", "name": "格力电器",
        "unit": 1, # 元
        "revenue": 170447058533.57,
        "op_cf": 46383114754.02,
        "capex": 1717311068.10
    },
    {
        "code": "600276", "name": "恒瑞医药",
        "unit": 1, # 元
        "revenue": 31629416193.83,
        "op_cf": 11235378130.63,
        "capex": 2961906284.58
    },
    {
        "code": "002415", "name": "海康威视",
        "unit": 1, # 元
        "revenue": 92507796069.94,
        "op_cf": 25339411083.10,
        "capex": 3622046664.67
    },
    {
        "code": "601012", "name": "隆基绿能",
        "unit": 1, # 元
        "revenue": 70347049950.42,
        "op_cf": 4359382755.77,
        "capex": 5893972740.27
    }
]

for d in data:
    d['fcf'] = d['op_cf'] - d['capex']
    print(f"{d['code']} ({d['name']}): Revenue={d['revenue']:.2f}, OP_CF={d['op_cf']:.2f}, Capex={d['capex']:.2f}, FCF={d['fcf']:.2f}")

# Sort by FCF descending
sorted_data = sorted(data, key=lambda x: x['fcf'], reverse=True)
print("\nRANKING BY FCF DESCENDING:")
for rank, d in enumerate(sorted_data, 1):
    print(f"{rank}. {d['code']} ({d['name']}): FCF = {d['fcf']:.2f}")
