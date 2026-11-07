import pandas as pd

from probe_support import solution

mod = solution()


def sales():
    return pd.DataFrame({
        "region": pd.Categorical(["north", "south", "north", "east"],
                                 categories=["east", "north", "south", "west", "zz_closed"]),
        "amount": [10.0, 5.0, 2.5, 1.0],
    })


def test_region_totals_only_present_regions():
    out = mod.region_totals(sales())
    assert list(out.columns) == ["region", "total"]
    assert [str(r) for r in out["region"]] == ["east", "north", "south"]
    assert out["total"].tolist() == [1.0, 12.5, 5.0]
    assert out.index.tolist() == [0, 1, 2]


def test_monthly_totals_month_end_with_gaps():
    df = pd.DataFrame({
        "when": pd.Series([pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-20 13:00"),
                           pd.Timestamp("2024-03-31 23:59"), pd.Timestamp("2024-03-01")]),
        "amount": [1.0, 2.0, 4.0, 8.0],
    })
    out = mod.monthly_totals(df)
    assert [ts.strftime("%Y-%m-%d %H:%M") for ts in out.index] == [
        "2024-01-31 00:00", "2024-02-29 00:00", "2024-03-31 00:00"]
    assert out.tolist() == [3.0, 0.0, 12.0]
