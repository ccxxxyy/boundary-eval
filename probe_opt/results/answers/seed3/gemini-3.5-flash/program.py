import json
import pulp


def main():
    NAV0 = 11210129.48
    start_cash = 394688.48

    stocks = [
        {
            "code": "002759",
            "sector": "银行",
            "price": 357.77,
            "target_weight": 0.0482,
            "holding": 1600,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "600308",
            "sector": "医药",
            "price": 131.01,
            "target_weight": 0.0682,
            "holding": 9200,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "002731",
            "sector": "电子",
            "price": 166.22,
            "target_weight": 0.0568,
            "holding": 3000,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "002987",
            "sector": "消费",
            "price": 313.00,
            "target_weight": 0.0720,
            "holding": 2100,
            "locked": 1200,
            "status": "正常",
        },
        {
            "code": "002222",
            "sector": "银行",
            "price": 14.23,
            "target_weight": 0.0735,
            "holding": 67200,
            "locked": 40300,
            "status": "跌停",
        },
        {
            "code": "002519",
            "sector": "医药",
            "price": 58.68,
            "target_weight": 0.0369,
            "holding": 7400,
            "locked": 4400,
            "status": "停牌",
        },
        {
            "code": "601925",
            "sector": "电子",
            "price": 52.31,
            "target_weight": 0.0335,
            "holding": 4900,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "601715",
            "sector": "消费",
            "price": 74.52,
            "target_weight": 0.0873,
            "holding": 11800,
            "locked": 0,
            "status": "停牌",
        },
        {
            "code": "600730",
            "sector": "银行",
            "price": 369.50,
            "target_weight": 0.0496,
            "holding": 1100,
            "locked": 0,
            "status": "正常",
        },
        {
            "code": "000127",
            "sector": "医药",
            "price": 56.14,
            "target_weight": 0.0479,
            "holding": 12800,
            "locked": 7600,
            "status": "正常",
        },
        {
            "code": "000819",
            "sector": "电子",
            "price": 3.76,
            "target_weight": 0.0976,
            "holding": 111100,
            "locked": 66600,
            "status": "涨停",
        },
        {
            "code": "002893",
            "sector": "消费",
            "price": 73.31,
            "target_weight": 0.0633,
            "holding": 11000,
            "locked": 0,
            "status": "跌停",
        },
        {
            "code": "000564",
            "sector": "银行",
            "price": 54.32,
            "target_weight": 0.0872,
            "holding": 20500,
            "locked": 6100,
            "status": "正常",
        },
        {
            "code": "000007",
            "sector": "医药",
            "price": 13.57,
            "target_weight": 0.0637,
            "holding": 63400,
            "locked": 0,
            "status": "涨停",
        },
        {
            "code": "002298",
            "sector": "电子",
            "price": 3.92,
            "target_weight": 0.0743,
            "holding": 263400,
            "locked": 79000,
            "status": "正常",
        },
    ]

    sector_bounds = {
        "银行": [0.15, 0.32],
        "医药": [0.15, 0.32],
        "电子": [0.15, 0.32],
        "消费": [0.15, 0.32],
    }

    prob = pulp.LpProblem("PortfolioRebalance", pulp.LpMinimize)

    x_plus = {}
    x_minus = {}
    b_plus = {}
    b_minus = {}
    comm = {}
    fee = {}
    dev = {}

    M = 100000

    for s in stocks:
        code = s["code"]
        status = s["status"]

        b_plus[code] = pulp.LpVariable(f"b_plus_{code}", cat=pulp.LpBinary)
        b_minus[code] = pulp.LpVariable(f"b_minus_{code}", cat=pulp.LpBinary)

        prob += b_plus[code] + b_minus[code] <= 1

        x_plus[code] = pulp.LpVariable(f"x_plus_{code}", lowBound=0, cat=pulp.LpInteger)
        x_minus[code] = pulp.LpVariable(
            f"x_minus_{code}", lowBound=0, cat=pulp.LpInteger
        )

        prob += x_plus[code] >= b_plus[code]
        prob += x_plus[code] <= M * b_plus[code]

        prob += x_minus[code] >= b_minus[code]
        prob += x_minus[code] <= M * b_minus[code]

        if status == "停牌":
            prob += b_plus[code] == 0
            prob += b_minus[code] == 0
        elif status == "涨停":
            prob += b_plus[code] == 0
        elif status == "跌停":
            prob += b_minus[code] == 0

        # T+1 constraint
        prob += 100 * (x_minus[code] - x_plus[code]) <= s["holding"] - s["locked"]

        # Single stock max weight <= 10% NAV0
        prob += (s["holding"] + 100 * (x_plus[code] - x_minus[code])) * s[
            "price"
        ] <= 0.10 * NAV0

        # Fee modelling
        V_i = 100 * (x_plus[code] + x_minus[code]) * s["price"]
        comm[code] = pulp.LpVariable(f"comm_{code}", lowBound=0)
        prob += comm[code] >= 5.0 * (b_plus[code] + b_minus[code])
        prob += comm[code] >= 0.00025 * V_i

        fee[code] = pulp.LpVariable(f"fee_{code}", lowBound=0)
        prob += comm[code] + 0.0005 * (100 * x_minus[code] * s["price"]) == fee[code]

        # Deviation modelling
        target_val = s["target_weight"] * NAV0
        new_val = (s["holding"] + 100 * (x_plus[code] - x_minus[code])) * s["price"]

        dev[code] = pulp.LpVariable(f"dev_{code}", lowBound=0)
        prob += dev[code] >= new_val - target_val
        prob += dev[code] >= target_val - new_val

    # Sector weight bounds
    for sector, (min_w, max_w) in sector_bounds.items():
        sector_val = pulp.lpSum(
            (s["holding"] + 100 * (x_plus[s["code"]] - x_minus[s["code"]]))
            * s["price"]
            for s in stocks
            if s["sector"] == sector
        )
        prob += sector_val >= min_w * NAV0
        prob += sector_val <= max_w * NAV0

    # Cash constraint
    buy_val = pulp.lpSum(100 * x_plus[s["code"]] * s["price"] for s in stocks)
    sell_val = pulp.lpSum(100 * x_minus[s["code"]] * s["price"] for s in stocks)
    total_fee = pulp.lpSum(fee[s["code"]] for s in stocks)

    end_cash = start_cash - buy_val + sell_val - total_fee
    prob += end_cash >= 0.01 * NAV0

    # Turnover constraint
    total_turnover = buy_val + sell_val
    prob += total_turnover <= 0.25 * NAV0

    # Objective
    prob += pulp.lpSum(dev[s["code"]] for s in stocks) + total_fee

    solver = pulp.PULP_CBC_CMD(msg=False)
    prob.solve(solver)

    result = {}
    for s in stocks:
        code = s["code"]
        xp = round(pulp.value(x_plus[code]))
        xm = round(pulp.value(x_minus[code]))
        result[code] = int((xp - xm) * 100)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
