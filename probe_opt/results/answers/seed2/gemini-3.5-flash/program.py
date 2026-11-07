import json
import pulp

# 组合与市场数据
data = {
    "seed": 2,
    "cash": 357401.35,
    "stocks": [
        {
            "code": "000922",
            "sector": "银行",
            "price": 76.71,
            "target_weight": 0.0896,
            "holding": 15600,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "002433",
            "sector": "医药",
            "price": 16.78,
            "target_weight": 0.0891,
            "holding": 92200,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "601024",
            "sector": "电子",
            "price": 13.7,
            "target_weight": 0.0343,
            "holding": 35500,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "601915",
            "sector": "消费",
            "price": 26.28,
            "target_weight": 0.036,
            "holding": 10300,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "000370",
            "sector": "银行",
            "price": 41.95,
            "target_weight": 0.0822,
            "holding": 22100,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "002670",
            "sector": "医药",
            "price": 77.52,
            "target_weight": 0.0761,
            "holding": 12000,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "000677",
            "sector": "电子",
            "price": 375.95,
            "target_weight": 0.072,
            "holding": 3300,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "002498",
            "sector": "消费",
            "price": 227.52,
            "target_weight": 0.0498,
            "holding": 3700,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "000791",
            "sector": "银行",
            "price": 10.91,
            "target_weight": 0.0681,
            "holding": 54400,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "002319",
            "sector": "医药",
            "price": 386.36,
            "target_weight": 0.0681,
            "holding": 1800,
            "locked": 1000,
            "status": "正常",
        },
        {
            "code": "600803",
            "sector": "电子",
            "price": 197.31,
            "target_weight": 0.0666,
            "holding": 5600,
            "locked": 1600,
            "status": "涨停",
        },
        {
            "code": "600060",
            "sector": "消费",
            "price": 12.84,
            "target_weight": 0.0405,
            "holding": 43700,
            "locked": 13100,
            "status": "正常",
        },
        {
            "code": "600772",
            "sector": "银行",
            "price": 269.34,
            "target_weight": 0.0573,
            "holding": 1100,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "600433",
            "sector": "医药",
            "price": 9.27,
            "target_weight": 0.055,
            "holding": 25700,
            "locked": 0,
            "status": "停牌",
        },
        {
            "code": "601255",
            "sector": "电子",
            "price": 64.36,
            "target_weight": 0.0753,
            "holding": 14200,
            "locked": 4200,
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

cash0 = data["cash"]
stocks = data["stocks"]
sector_bounds = data["sector_bounds"]

holding_val = sum(s["holding"] * s["price"] for s in stocks)
NAV0 = cash0 + holding_val

# 建立混合整数线性规划模型
prob = pulp.LpProblem("Portfolio_Rebalance", pulp.LpMinimize)

y_vars = {}
u_vars = {}
v_vars = {}
B_vars = {}
S_vars = {}
C_vars = {}
D_vars = {}
dev_vars = {}

M = 100000

for s in stocks:
    code = s["code"]
    price = s["price"]
    holding = s["holding"]
    locked = s["locked"]
    status = s["status"]
    target_weight = s["target_weight"]

    # 交易股数为 100 的倍数 y (手)
    # T+1限制：持股不能少于今日已买入数 locked
    min_y = -((holding - locked) // 100)

    # 单只股票市值不超过 10% NAV0
    max_holding = int(0.10 * NAV0 / price)
    max_y = (max_holding - holding) // 100

    # 交易状态限制
    if status == "停牌":
        min_y = 0
        max_y = 0
    elif status == "涨停":
        max_y = min(max_y, 0)
    elif status == "跌停":
        min_y = max(min_y, 0)

    y = pulp.LpVariable(f"y_{code}", lowBound=min_y, upBound=max_y, cat="Integer")
    u = pulp.LpVariable(f"u_{code}", cat="Binary")  # 买入标识
    v = pulp.LpVariable(f"v_{code}", cat="Binary")  # 卖出标识

    y_vars[code] = y
    u_vars[code] = u
    v_vars[code] = v

    prob += u + v <= 1

    y_pos = pulp.LpVariable(f"y_pos_{code}", lowBound=0, cat="Integer")
    y_neg = pulp.LpVariable(f"y_neg_{code}", lowBound=0, cat="Integer")

    prob += y == y_pos - y_neg
    prob += y_pos <= M * u
    prob += y_pos >= u
    prob += y_neg <= M * v
    prob += y_neg >= v

    B = pulp.LpVariable(f"B_{code}", lowBound=0, cat="Continuous")
    S = pulp.LpVariable(f"S_{code}", lowBound=0, cat="Continuous")

    prob += B == 100 * price * y_pos
    prob += S == 100 * price * y_neg

    B_vars[code] = B
    S_vars[code] = S

    # 佣金 = max(5, 成交额 * 0.025%)
    C = pulp.LpVariable(f"C_{code}", lowBound=0, cat="Continuous")
    prob += C >= 5 * (u + v)
    prob += C >= 0.00025 * (B + S)
    C_vars[code] = C

    # 印花税 = 卖出成交额 * 0.05%
    D = pulp.LpVariable(f"D_{code}", lowBound=0, cat="Continuous")
    prob += D == 0.0005 * S
    D_vars[code] = D

    # 目标偏离度绝对值
    dev = pulp.LpVariable(f"dev_{code}", lowBound=0, cat="Continuous")
    target_val = target_weight * NAV0
    curr_val_expr = (holding + 100 * y) * price

    prob += dev >= curr_val_expr - target_val
    prob += dev >= target_val - curr_val_expr
    dev_vars[code] = dev

    # 单只股票上限约束
    prob += curr_val_expr <= 0.10 * NAV0
    prob += curr_val_expr >= 0

# 行业市值占比约束
for sector, bounds in sector_bounds.items():
    sector_stocks = [s for s in stocks if s["sector"] == sector]
    sector_val_expr = sum(
        (s["holding"] + 100 * y_vars[s["code"]]) * s["price"]
        for s in sector_stocks
    )
    prob += sector_val_expr >= bounds[0] * NAV0
    prob += sector_val_expr <= bounds[1] * NAV0

total_fee = sum(C_vars[c] + D_vars[c] for c in C_vars)

# 现金约束 >= 1% NAV0
prob += (
    cash0 - sum(B_vars.values()) + sum(S_vars.values()) - total_fee
    >= 0.01 * NAV0
)

# 总换手率（成交金额）约束 <= 25% NAV0
prob += sum(B_vars.values()) + sum(S_vars.values()) <= 0.25 * NAV0

# 目标函数：最小化 (偏离度之和 + 总费用)
prob += sum(dev_vars.values()) + total_fee

# 求解
try:
    solver = pulp.HiGHS_CMD(msg=False)
    prob.solve(solver)
except Exception:
    solver = pulp.PULP_CBC_CMD(msg=False)
    prob.solve(solver)

# 输出符合要求的 JSON 格式
res = {}
for s in stocks:
    code = s["code"]
    res[code] = int(round(pulp.value(y_vars[code]))) * 100

print(json.dumps(res))
