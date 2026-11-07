import pulp
import json

def solve():
    # 组合现状与数据
    data = {
        "seed": 2, 
        "cash": 357401.35, 
        "stocks": [
            {"code": "000922", "sector": "银行", "price": 76.71, "target_weight": 0.0896, "holding": 15600, "locked": 0, "status": "正常"}, 
            {"code": "002433", "sector": "医药", "price": 16.78, "target_weight": 0.0891, "holding": 92200, "locked": 0, "status": "正常"}, 
            {"code": "601024", "sector": "电子", "price": 13.7, "target_weight": 0.0343, "holding": 35500, "locked": 0, "status": "正常"}, 
            {"code": "601915", "sector": "消费", "price": 26.28, "target_weight": 0.036, "holding": 10300, "locked": 0, "status": "正常"}, 
            {"code": "000370", "sector": "银行", "price": 41.95, "target_weight": 0.0822, "holding": 22100, "locked": 0, "status": "正常"}, 
            {"code": "002670", "sector": "医药", "price": 77.52, "target_weight": 0.0761, "holding": 12000, "locked": 0, "status": "正常"}, 
            {"code": "000677", "sector": "电子", "price": 375.95, "target_weight": 0.072, "holding": 3300, "locked": 0, "status": "正常"}, 
            {"code": "002498", "sector": "消费", "price": 227.52, "target_weight": 0.0498, "holding": 3700, "locked": 0, "status": "正常"}, 
            {"code": "000791", "sector": "银行", "price": 10.91, "target_weight": 0.0681, "holding": 54400, "locked": 0, "status": "正常"}, 
            {"code": "002319", "sector": "医药", "price": 386.36, "target_weight": 0.0681, "holding": 1800, "locked": 1000, "status": "正常"}, 
            {"code": "600803", "sector": "电子", "price": 197.31, "target_weight": 0.0666, "holding": 5600, "locked": 1600, "status": "涨停"}, 
            {"code": "600060", "sector": "消费", "price": 12.84, "target_weight": 0.0405, "holding": 43700, "locked": 13100, "status": "正常"}, 
            {"code": "600772", "sector": "银行", "price": 269.34, "target_weight": 0.0573, "holding": 1100, "locked": 0, "status": "正常"}, 
            {"code": "600433", "sector": "医药", "price": 9.27, "target_weight": 0.055, "holding": 25700, "locked": 0, "status": "停牌"}, 
            {"code": "601255", "sector": "电子", "price": 64.36, "target_weight": 0.0753, "holding": 14200, "locked": 4200, "status": "正常"}
        ], 
        "sector_bounds": {
            "银行": [0.15, 0.32], 
            "医药": [0.15, 0.32], 
            "电子": [0.15, 0.32], 
            "消费": [0.15, 0.32]
        }
    }

    NAV0 = 12201442.35
    Cash0 = data["cash"]
    
    # 定义 MILP 问题
    prob = pulp.LpProblem("Portfolio_Optimization", pulp.LpMinimize)
    
    # 变量字典
    X = {}    # 买入的手数 (1手=100股)
    Y = {}    # 卖出的手数
    I_B = {}  # 是否买入 (0-1变量)
    I_S = {}  # 是否卖出 (0-1变量)
    I = {}    # 是否交易 (0-1变量)
    C = {}    # 佣金
    D = {}    # 偏离目标权重的绝对值
    
    for stock in data["stocks"]:
        code = stock["code"]
        P = stock["price"]
        H = stock["holding"]
        L = stock["locked"]
        
        # 计算最大可买卖手数
        max_buy = int((0.1 * NAV0) / (100 * P)) + 1
        max_sell = int((H - L) / 100)
        
        X[code] = pulp.LpVariable(f"X_{code}", 0, max_buy, cat="Integer")
        Y[code] = pulp.LpVariable(f"Y_{code}", 0, max_sell, cat="Integer")
        I_B[code] = pulp.LpVariable(f"I_B_{code}", 0, 1, cat="Binary")
        I_S[code] = pulp.LpVariable(f"I_S_{code}", 0, 1, cat="Binary")
        I[code] = pulp.LpVariable(f"I_{code}", 0, 1, cat="Binary")
        C[code] = pulp.LpVariable(f"C_{code}", 0, None)
        D[code] = pulp.LpVariable(f"D_{code}", 0, None)
        
        # 状态约束
        if stock["status"] == "停牌":
            prob += X[code] == 0
            prob += Y[code] == 0
        elif stock["status"] == "涨停":
            prob += X[code] == 0
        elif stock["status"] == "跌停":
            prob += Y[code] == 0
            
        # 逻辑约束 (Big-M)
        prob += X[code] <= max_buy * I_B[code]
        prob += Y[code] <= max_sell * I_S[code]
        prob += I_B[code] + I_S[code] <= 1
        prob += I[code] == I_B[code] + I_S[code]
        
        # 佣金约束: max(5, 成交金额 * 0.025%)
        prob += C[code] >= 5 * I[code]
        prob += C[code] >= P * 100 * (X[code] + Y[code]) * 0.00025
        
        # 单只股票市值不超过 NAV0 的 10%
        prob += P * (H + 100 * X[code] - 100 * Y[code]) <= 0.1 * NAV0
        
        # 绝对值偏差约束
        T_val = stock["target_weight"] * NAV0
        final_val = P * (H + 100 * X[code] - 100 * Y[code])
        prob += D[code] >= final_val - T_val
        prob += D[code] >= T_val - final_val

    # 行业权重约束
    for sector, bounds in data["sector_bounds"].items():
        sector_val = pulp.lpSum([
            stock["price"] * (stock["holding"] + 100 * X[stock["code"]] - 100 * Y[stock["code"]]) 
            for stock in data["stocks"] if stock["sector"] == sector
        ])
        prob += sector_val >= bounds[0] * NAV0
        prob += sector_val <= bounds[1] * NAV0

    # 费用与现金计算
    total_buy = pulp.lpSum([stock["price"] * 100 * X[stock["code"]] for stock in data["stocks"]])
    total_sell = pulp.lpSum([stock["price"] * 100 * Y[stock["code"]] for stock in data["stocks"]])
    total_commission = pulp.lpSum([C[stock["code"]] for stock in data["stocks"]])
    total_tax = pulp.lpSum([stock["price"] * 100 * Y[stock["code"]] * 0.0005 for stock in data["stocks"]])

    # 交易后现金不少于 NAV0 的 1%
    final_cash = Cash0 - total_buy + total_sell - total_commission - total_tax
    prob += final_cash >= 0.01 * NAV0

    # 总成交金额不得超过 NAV0 的 25%
    total_traded = pulp.lpSum([stock["price"] * 100 * (X[stock["code"]] + Y[stock["code"]]) for stock in data["stocks"]])
    prob += total_traded <= 0.25 * NAV0

    # 目标函数：最小化 (市值偏差绝对值之和 + 全部费用)
    prob += pulp.lpSum([D[stock["code"]] for stock in data["stocks"]]) + total_commission + total_tax

    # 求解
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=100)
    prob.solve(solver)

    # 提取结果
    result = {}
    for stock in data["stocks"]:
        code = stock["code"]
        x_val = int(round(X[code].varValue)) if X[code].varValue is not None else 0
        y_val = int(round(Y[code].varValue)) if Y[code].varValue is not None else 0
        trade = (x_val - y_val) * 100
        if trade != 0:
            result[code] = trade

    # 打印 JSON 结果
    print(json.dumps(result))

if __name__ == "__main__":
    solve()
