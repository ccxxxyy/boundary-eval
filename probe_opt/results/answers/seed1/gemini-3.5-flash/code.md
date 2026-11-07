```python
import json
import pulp

# 输入数据
data = {
    "seed": 1,
    "cash": 179812.76,
    "stocks": [
        {
            "code": "600022",
            "sector": "银行",
            "price": 29.87,
            "target_weight": 0.042,
            "holding": 20900,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "601992",
            "sector": "医药",
            "price": 50.19,
            "target_weight": 0.0893,
            "holding": 30700,
            "locked": 9200,
            "status": "正常",
        },
        {
            "code": "002566",
            "sector": "电子",
            "price": 16.89,
            "target_weight": 0.0837,
            "holding": 59300,
            "locked": 0,
            "status": "停牌",
        },
        {
            "code": "000948",
            "sector": "消费",
            "price": 30.01,
            "target_weight": 0.05,
            "holding": 16300,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "600190",
            "sector": "银行",
            "price": 258.07,
            "target_weight": 0.066,
            "holding": 2200,
            "locked": 1300,
            "status": "停牌",
        },
        {
            "code": "000917",
            "sector": "医药",
            "price": 174.84,
            "target_weight": 0.0629,
            "holding": 4500,
            "locked": 2700,
            "status": "正常",
        },
        {
            "code": "601310",
            "sector": "电子",
            "price": 61.23,
            "target_weight": 0.0763,
            "holding": 12900,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "002603",
            "sector": "消费",
            "price": 239.8,
            "target_weight": 0.0854,
            "holding": 4500,
            "locked": 2700,
            "status": "涨停",
        },
        {
            "code": "002680",
            "sector": "银行",
            "price": 46.21,
            "target_weight": 0.0394,
            "holding": 5500,
            "locked": 0,
            "status": "停牌",
        },
        {
            "code": "000088",
            "sector": "医药",
            "price": 304.97,
            "target_weight": 0.035,
            "holding": 1700,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "002379",
            "sector": "电子",
            "price": 329.1,
            "target_weight": 0.0885,
            "holding": 4200,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "002662",
            "sector": "消费",
            "price": 93.92,
            "target_weight": 0.0618,
            "holding": 10600,
            "locked": 3100,
            "status": "正常",
        },
        {
            "code": "601414",
            "sector": "银行",
            "price": 5.04,
            "target_weight": 0.0837,
            "holding": 241700,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "000675",
            "sector": "医药",
            "price": 76.91,
            "target_weight": 0.0333,
            "holding": 3300,
            "locked": 1900,
            "status": "正常",
        },
        {
            "code": "601531",
            "sector": "电子",
            "price": 81.83,
            "target_weight": 0.0626,
            "holding": 6700,
            "locked": 0,
            "status": "正常",
        },
    ],
    "sector_bounds": {
        "银行": [0.15, 0.32],
        "医药": [0.15, 0.32],
        "电子": [0.15, 0.32],
        "消费": [0.15, 0.32],
    },
}

nav0 = 12229777.76
initial_cash = data["cash"]
stocks = data["stocks"]
sector_bounds = data["sector_bounds"]

# 创建 MILP 优化模型
prob = pulp.LpProblem("Portfolio_Rebalance", pulp.LpMinimize)

buy_lots = {}
sell_lots = {}
is_buy = {}
is_sell = {}
abs_dev = {}
comm = {}
stamp = {}

total_fees_list = []

for s in stocks:
    code = s["code"]
    price = s["price"]
    holding = s["holding"]
    locked = s["locked"]
    status = s["status"]
    target_w = s["target_weight"]
    target_val = target_w * nav0

    # 计算单只股票买入/卖出手数上限
    max_buy_lots = int(max(0, (0.10 * nav0 - holding * price) // (100 * price)))
    max_sell_lots = int(max(0, (holding - locked) // 100))

    if status == "停牌":
        max_buy_lots = 0
        max_sell_lots = 0
    elif status == "涨停":
        max_buy_lots = 0
    elif status == "跌停":
        max_sell_lots = 0

    buy_lots[code] = pulp.LpVariable(
        f"buy_{code}", lowBound=0, upBound=max_buy_lots, cat=pulp.LpInteger
    )
    sell_lots[code] = pulp.LpVariable(
        f"sell_{code}", lowBound=0, upBound=max_sell_lots, cat=pulp.LpInteger
    )

    is_buy[code] = pulp.LpVariable(f"is_buy_{code}", cat=pulp.LpBinary)
    is_sell[code] = pulp.LpVariable(f"is_sell_{code}", cat=pulp.LpBinary)

    prob += is_buy[code] + is_sell[code] <= 1

    if max_buy_lots > 0:
        prob += buy_lots[code] <= max_buy_lots * is_buy[code]
    else:
        prob += buy_lots[code] == 0
        prob += is_buy[code] == 0

    if max_sell_lots > 0:
        prob += sell_lots[code] <= max_sell_lots * is_sell[code]
    else:
        prob += sell_lots[code] == 0
        prob += is_sell[code] == 0

    # 交易后持股与市值
    trade_lots = buy_lots[code] - sell_lots[code]
    new_holding = holding + 100 * trade_lots
    new_val = new_holding * price

    # 规则4: 单只股票市值不超过 10% NAV0
    prob += new_val <= 0.10 * nav0

    # 规则6: 费用计算
    is_traded = is_buy[code] + is_sell[code]
    comm[code] = pulp.LpVariable(f"comm_{code}", lowBound=0)
    prob += comm[code] >= 5.0 * is_traded
    prob += (
        comm[code] >= 100 * (buy_lots[code] + sell_lots[code]) * price * 0.00025
    )

    stamp[code] = 100 * sell_lots[code] * price * 0.0005
    fee_i = comm[code] + stamp[code]
    total_fees_list.append(fee_i)

    # 目标函数中的绝对偏离度
    abs_dev[code] = pulp.LpVariable(f"abs_dev_{code}", lowBound=0)
    prob += abs_dev[code] >= new_val - target_val
    prob += abs_dev[code] >= target_val - new_val

total_fees = pulp.lpSum(total_fees_list)

# 目标函数：最小化绝对偏离度之和 + 总费用
prob += pulp.lpSum([abs_dev[c] for c in abs_dev]) + total_fees

# 规则5: 行业市值比例约束
for sector, (min_w, max_w) in sector_bounds.items():
    sec_val = pulp.lpSum(
        [
            (s["holding"] + 100 * (buy_lots[s["code"]] - sell_lots[s["code"]]))
            * s["price"]
            for s in stocks
            if s["sector"] == sector
        ]
    )
    prob += sec_val >= min_w * nav0
    prob += sec_val <= max_w * nav0

# 规则7: 交易后现金 >= 1% NAV0
buy_val_total = pulp.lpSum(
    [100 * buy_lots[s["code"]] * s["price"] for s in stocks]
)
sell_val_total = pulp.lpSum(
    [100 * sell_lots[s["code"]] * s["price"] for s in stocks]
)

cash_after = initial_cash - buy_val_total + sell_val_total - total_fees
prob += cash_after >= 0.01 * nav0

# 规则8: 总成交金额 <= 25% NAV0
total_turnover = buy_val_total + sell_val_total
prob += total_turnover <= 0.25 * nav0

# 求解
try:
    solver = pulp.PULP_CBC_CMD(msg=False)
    prob.solve(solver)
except Exception:
    prob.solve()

# 构建输出
result = {}
for s in stocks:
    code = s["code"]
    b = int(round(pulp.value(buy_lots[code])))
    sl = int(round(pulp.value(sell_lots[code])))
    result[code] = (b - sl) * 100

print(json.dumps(result))
```