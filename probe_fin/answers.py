"""Ground truth, read by hand from each report's text (page/line noted), before any model run.

Amounts in the reports of 000333 and 300750 are in thousands of yuan (千元); converted to yuan here.
"""

K = 1000

RAW = {
    "600519": {  # 元
        "revenue": 168_838_102_514.79,          # 合并利润表 p61 其中：营业收入
        "cfo": 61_522_204_989.35,               # 合并现金流量表 p65-66 (p6 主要会计数据同)
        "capex": 3_127_594_916.41,              # 合并现金流量表 p66 (母公司表为 3,104,346,428.46)
        "debt": [0, 44_206_237.05, 0, 0, 189_504_942.77],  # 合并资产负债表 p57-58
        "ar_open": 18_974_192.75, "ar_close": 2_609_048.49,  # 合并资产负债表 p57
        "nonrecurring": 26_959_446.43,          # p7 非经常性损益 合计
        "q4_profit": 17_693_320_389.50,         # p7 分季度
        "top5": 10.10,                          # p12 前五名客户 占年度销售总额10.10%
        "selling": 7_253_499_600.68,            # 合并利润表 p61
    },
    "000333": {  # 千元
        "revenue": 456_451_731 * K,             # 合并及公司利润表 其中：营业收入 (营业总收入 458,502,407)
        "cfo": 53_345_930 * K,
        "capex": 11_141_889 * K,                # 合并列 (公司列 386,032)
        "debt": [43_904_550 * K, 5_821_777 * K, 12_658_843 * K, 3_194_774 * K, 1_901_053 * K],
        "ar_open": 35_798_974 * K, "ar_close": 40_450_097 * K,
        "nonrecurring": 2_678_178 * K,
        "q4_profit": 6_062_028 * K,
        "top5": 13.17,
        "selling": 42_891_490 * K,
    },
    "300750": {  # 千元
        "revenue": 423_701_834 * K,
        "cfo": 133_219_982 * K,
        "capex": 42_344_558 * K,                # 合并 (母公司 2,056,300)
        "debt": [12_935_498 * K, 22_237_540 * K, 78_234_935 * K, 3_443_434 * K, 2_805_081 * K],
        "ar_open": 64_135_510 * K, "ar_close": 76_403_264 * K,  # 合并 (母公司 84,277,741 / 69,969,060)
        "nonrecurring": 7_693_417 * K,          # = Σ季度归母净利润 − Σ季度扣非, 已核对
        "q4_profit": 23_167_173 * K,
        "top5": 38.96,
        "selling": 3_735_118 * K,
    },
}


def truth(code: str) -> dict:
    r = RAW[code]
    return {
        "q1_revenue": r["revenue"],
        "q2_fcf": r["cfo"] - r["capex"],
        "q3_interest_debt": sum(r["debt"]),
        "q4_ar_days": 365 * (r["ar_open"] + r["ar_close"]) / 2 / r["revenue"],
        "q5_nonrecurring": r["nonrecurring"],
        "q6_q4_profit": r["q4_profit"],
        "q7_top5_customers": r["top5"],
        "q8_selling_ratio": r["selling"] / r["revenue"] * 100,
    }


def correct(kind: str, got: float, want: float) -> bool:
    if kind == "amount":
        return abs(got - want) <= 0.005 * abs(want)
    if kind == "days":
        return abs(got - want) <= 0.5
    return abs(got - want) <= 0.05


if __name__ == "__main__":
    for code in RAW:
        print(code, {k: round(v, 4) for k, v in truth(code).items()})
