```python
import json
import math
from pulp import *

raw = r'''{"seed": 1, "cash": 179812.76, "stocks": [{"code": "600022", "sector": "银行", "price": 29.87, "target_weight": 0.042, "holding": 20900, "locked": 0, "status": "正常"}, {"code": "601992", "sector": "医药", "price": 50.19, "target_weight": 0.0893, "holding": 30700, "locked": 9200, "status": "正常"}, {"code": "002566", "sector": "电子", "price": 16.89, "target_weight": 0.0837, "holding": 59300, "locked": 0, "status": "停牌"}, {"code": "000948", "sector": "消费", "price": 30.01, "target_weight": 0.05, "holding": 16300, "locked": 0, "status": "正常"}, {"code": "600190", "sector": "银行", "price": 258.07, "target_weight": 0.066, "holding": 2200, "locked": 1300, "status": "停牌"}, {"code": "000917", "sector": "医药", "price": 174.84, "target_weight": 0.0629, "holding": 4500, "locked": 2700, "status": "正常"}, {"code": "601310", "sector": "电子", "price": 61.23, "target_weight": 0.0763, "holding": 12900, "locked": 0, "status": "正常"}, {"code": "002603", "sector": "消费", "price": 239.8, "target_weight": 0.0854, "holding": 4500, "locked": 2700, "status": "涨停"}, {"code": "002680", "sector": "银行", "price": 46.21, "target_weight": 0.0394, "holding": 5500, "locked": 0, "status": "停牌"}, {"code": "000088", "sector": "医药", "price": 304.97, "target_weight": 0.035, "holding": 1700, "locked": 0, "status": "正常"}, {"code": "002379", "sector": "电子", "price": 329.1, "target_weight": 0.0885, "holding": 4200, "locked": 0, "status": "正常"}, {"code": "002662", "sector": "消费", "price": 93.92, "target_weight": 0.0618, "holding": 10600, "locked": 3100, "status": "正常"}, {"code": "601414", "sector": "银行", "price": 5.04, "target_weight": 0.0837, "holding": 241700, "locked": 0, "status": "正常"}, {"code": "000675", "sector": "医药", "price": 76.91, "target_weight": 0.0333, "holding": 3300, "locked": 1900, "status": "正常"}, {"code": "601531", "sector": "电子", "price": 81.83, "target_weight": 0.0626, "holding": 6700, "locked": 0, "status": "正常"}], "sector_bounds": {"银行": [0.15, 0.32], "医药": [0.15, 0.32], "电子": [0.15, 0.32], "消费": [0.15, 0.32]}}'''

data = json.loads(raw)
stocks = data["stocks"]
cash = float(data["cash"])
NAV0 = 12229777.76

cash_min = 0.01 * NAV0
cap = 0.10 * NAV0
total_cap = 0.25 * NAV0

prob = LpProblem("rebalance", LpMinimize)

k_vars = []
m_expr = []
k_bounds = []

for i, s in enumerate(stocks):
    price = float(s["price"])
    holding = int(s["holding"])
    locked = int(s["locked"])
    status = s["status"]

    if status == "停牌":
        kmin = 0
        kmax = 0
    else:
        req_low = max(0, locked)
        kmin = math.ceil((req_low - holding) / 100.0 - 1e-12)

        kmax = math.floor((cap / price - holding) / 100.0 + 1e-12)

        if status == "涨停":
            kmax = min(kmax, 0)

        kmin = int(kmin)
        kmax = int(kmax)

    k = LpVariable(f"k_{i}", lowBound=kmin, upBound=kmax, cat=LpInteger)
    k_vars.append(k)
    k_bounds.append((kmin, kmax))
    m_expr.append(price * (holding + 100 * k))

obj = 0

for i, s in enumerate(stocks):
    target = float(s["target_weight"]) * NAV0
    m = m_expr[i]
    d = LpVariable(f"d_{i}", lowBound=0)
    prob += d >= m - target
    prob += d >= target - m
    obj += d

a_vars = []
fee_exprs = []

for i, s in enumerate(stocks):
    if s["status"] == "停牌":
        continue

    price = float(s["price"])
    kmin, kmax = k_bounds[i]
    max_abs = max(abs(price * 100 * kmin), abs(price * 100 * kmax))

    if max_abs <= 1e-9:
        continue

    k = k_vars[i]

    z = LpVariable(f"z_{i}", cat=LpBinary)
    a = LpVariable(f"a_{i}", lowBound=0)
    f = LpVariable(f"f_{i}", lowBound=0)
    sfee = LpVariable(f"s_{i}", lowBound=0)

    prob += a >= price * 100 * k
    prob += a >= -price * 100 * k
    prob += a <= max_abs * z

    prob += sfee >= -price * 100 * k

    prob += f >= 0.00025 * a
    prob += f >= 5 * z

    obj += f + 0.0005 * sfee

    a_vars.append(a)
    fee_exprs.append(f + 0.0005 * sfee)

for i in range(len(stocks)):
    prob += m_expr[i] <= cap

for sector, (lo, hi) in data["sector_bounds"].items():
    expr = lpSum(m_expr[i] for i, s in enumerate(stocks) if s["sector"] == sector)
    prob += expr >= lo * NAV0
    prob += expr <= hi * NAV0

cash_expr = (
    cash
    - lpSum(float(stocks[i]["price"]) * 100 * k_vars[i] for i in range(len(stocks)))
    - lpSum(fee_exprs)
)
prob += cash_expr >= cash_min

prob += lpSum(a_vars) <= total_cap
prob += obj

solver = PULP_CBC_CMD(msg=False, timeLimit=100)
prob.solve(solver)

result = {}

for i, s in enumerate(stocks):
    val = k_vars[i].varValue
    if val is None:
        val = 0

    ki = int(round(val))
    kmin, kmax = k_bounds[i]
    if ki < kmin:
        ki = kmin
    if ki > kmax:
        ki = kmax

    result[s["code"]] = int(100 * ki)

print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
```