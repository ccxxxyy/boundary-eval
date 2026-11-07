import pandas as pd


def region_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Total `amount` per `region`, excluding unused categorical categories."""
    # Work with region as object so sorting uses the actual region labels,
    # not the categorical category order, and so unused categories disappear.
    frame = df.assign(region=df["region"].astype(object))

    result = (
        frame.groupby("region", as_index=False, observed=True, sort=False)["amount"]
        .sum()
        .sort_values("region", kind="mergesort")
        .reset_index(drop=True)
        .rename(columns={"amount": "total"})
    )

    return result[["region", "total"]]


def monthly_totals(df: pd.DataFrame) -> pd.Series:
    """Total `amount` per calendar month, indexed by month-end at midnight."""
    if df.empty:
        return pd.Series(
            dtype=df["amount"].dtype,
            index=pd.DatetimeIndex([], name=None),
            name="amount",
        )

    months = df["when"].dt.to_period("M")
    totals = df.groupby(months)["amount"].sum()

    full_months = pd.period_range(start=months.min(), end=months.max(), freq="M")
    totals = totals.reindex(full_months, fill_value=0)

    totals.index = totals.index.to_timestamp(how="end").normalize()
    totals.index.name = None
    totals.name = "amount"

    return totals
