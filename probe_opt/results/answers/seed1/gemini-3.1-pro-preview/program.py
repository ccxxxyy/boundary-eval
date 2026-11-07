import pulp
import json

def solve():
    data_json = """{"seed": 1, "cash": 179812.76, "stocks": [{"code": "600022", "sector": "银行", "price": 29.87, "target_weight": 0.042, "holding": 20900, "locked": 0, "status": "正常"}, {"code": "601992", "sector": "医药", "price": 50.19, "target_weight": 0.0893, "holding": 30700, "locked": 9200, "status": "正常"}, {"code": "002566", "sector": "电子", "price": 16.89, "target_weight": 0.0837, "holding": 59300, "locked": 0, "status": "停牌"}, {"code": "000948", "sector": "消费", "price": 30.01, "target_weight": 0.05, "holding": 16300, "locked": 0, "status": "正常"}, {"code": "600190", "sector": "银行", "price": 258.07, "target_weight": 0.066, "holding": 2200, "locked": 1300, "status": "停牌"}, {"code": "000917", "sector": "医药", "price": 174.84, "target_weight": 0.0629, "holding": 4500, "locked": 2700, "status": "正常"}, {"code": "601310", "sector": "电子", "price": 61.23, "target_weight": 0.0763, "holding": 12900, "locked": 0, "status": "正常"}, {"code": "002603", "sector": "消费", "price": 239.8, "target_weight": 0.0854, "holding": 4500, "locked": 2700, "status": "涨停"}, {"code": "002680", "sector": "银行", "price": 46.21, "target_weight": 0.0394, "holding": 5500, "locked": 0, "status": "停牌"}, {"code": "000088", "sector": "医药", "price": 304.97, "target_weight": 0.035, "holding": 1700, "locked": 0, "status": "正常"}, {"code": "002379", "sector": "电子", "price": 329.1, "target_weight": 0.0885, "holding": 4200, "locked": 0, "status": "正常"}, {"code": "002662", "sector": "消费", "price": 93.92, "target_weight": 0.0618, "holding": 10600, "locked": 3100, "status": "正常"}, {"code": "601414", "sector": "银行", "price": 5.04, "target_weight": 0.0837, "holding": 241700, "locked": 0, "status": "正常"}, {"code": "000675", "sector": "医药", "price": 76.91, "target_weight": 0.0333, "holding": 3300, "locked": 1900, "status": "正常"}, {"code": "601531", "sector": "电子", "price": 81.83, "target_weight": 0.0626, "holding": 6700, "locked": 0, "status": "正常"}], "sector_bounds": {"银行": [0.15, 0.32], "医药": [0.15, 0.32], "电子": [0.15, 0.32], "消费": [0.15, 0.32]}}"""
    data = json.loads(data_json)
    
    # 计算初始 NAV0
    NAV0 = data["cash"] + sum(s["holding"] * s["price"] for s in data["stocks"])
    
    # 定义 MILP 问题
    prob = pulp.LpProblem("Portfolio_Optimization", pulp.LpMinimize)
    
    B = {}
    S = {}
    Y = {}
    C = {}
    D = {}
    M = {}
    E = {}
    
    for s in data["stocks"]:
        code = s["code"]
        price = s["price"]
        holding = s["holding"]
        locked = s["locked"]
        status = s["status"]
        target_val = s["target_weight"] * NAV0
        
        # 变量定义
        B[code] = pulp.LpVariable(f"B_{code}", lowBound=0, cat='Integer') # 买入的“手”数 (1手=100股)
        S[code] = pulp.LpVariable(f"S_{code}", lowBound=0, cat='Integer') # 卖出的“手”数
        Y[code] = pulp.LpVariable(f"Y_{code}", cat='Binary')              # 是否发生交易
        C[code] = pulp.LpVariable(f"C_{code}", lowBound=0)                # 佣金
        D[code] = pulp.LpVariable(f"D_{code}", lowBound=0)                # 印花税
        M[code] = pulp.LpVariable(f"M_{code}", lowBound=0)                # 交易后市值
        E[code] = pulp.LpVariable(f"E_{code}", lowBound=0)                # 市值偏离度绝对值
        
        # 状态限制
        if status == "停牌":
            prob += B[code] == 0
            prob += S[code] == 0
        elif status == "涨停":
            prob += B[code] == 0
        elif status == "跌停":
            prob += S[code] == 0
            
        # T+1 限制：交易后持股不得少于今日买入锁定的股份
        prob += holding - 100 * S[code] >= locked
        
        # 交易后市值计算
        prob += M[code] == (holding + 100 * B[code] - 100 * S[code]) * price
        
        # 单只股票市值不得超过 NAV0 的 10%
        prob += M[code] <= 0.10 * NAV0
        
        # 绝对值约束 E[code] = |M[code] - target_val|
        prob += E[code] >= M[code] - target_val
        prob += E[code] >= target_val - M[code]
        
        # 交易状态与最大交易量约束
        max_lots = int((0.25 * NAV0) / (100 * price)) + 1
        prob += B[code] + S[code] <= max_lots * Y[code]
        
        # 费用计算
        prob += C[code] >= 5 * Y[code]
        prob += C[code] >= (100 * B[code] * price + 100 * S[code] * price) * 0.00025
        prob += D[code] == 100 * S[code] * price * 0.0005
        
    # 行业市值比例限制
    for sector, bounds in data["sector_bounds"].items():
        sector_stocks = [s["code"] for s in data["stocks"] if s["sector"] == sector]
        sector_val = pulp.lpSum(M[code] for code in sector_stocks)
        prob += sector_val >= bounds[0] * NAV0
        prob += sector_val <= bounds[1] * NAV0
        
    # 汇总计算
    total_buy = pulp.lpSum(100 * B[s["code"]] * s["price"] for s in data["stocks"])
    total_sell = pulp.lpSum(100 * S[s["code"]] * s["price"] for s in data["stocks"])
    total_cost = pulp.lpSum(C[s["code"]] + D[s["code"]] for s in data["stocks"])
    
    # 现金限制
    prob += data["cash"] - total_buy + total_sell - total_cost >= 0.01 * NAV0
    
    # 总成交金额限制
    prob += total_buy + total_sell <= 0.25 * NAV0
    
    # 目标函数：最小化市值偏离度之和 + 全部费用
    prob += pulp.lpSum(E[s["code"]] for s in data["stocks"]) + total_cost
    
    # 求解
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=100))
    
    # 提取结果
    result = {}
    for s in data["stocks"]:
        code = s["code"]
        b_val = int(round(B[code].varValue)) if B[code].varValue is not None else 0
        s_val = int(round(S[code].varValue)) if S[code].varValue is not None else 0
        trade = (b_val - s_val) * 100
        if trade != 0:
            result[code] = trade
            
    # 输出 JSON
    print(json.dumps(result))

if __name__ == "__main__":
    solve()
