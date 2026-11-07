import pandas as pd


def region_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Total `amount` per `region`."""
    if df.empty:
        return pd.DataFrame(columns=["region", "total"])

    res = (
        df.groupby("region", observed=True)["amount"]
        .sum()
        .reset_index(name="total")
    )
    return res.sort_values("region").reset_index(drop=True)


def monthly_totals(df: pd.DataFrame) -> pd.Series:
    """Total `amount` per calendar month."""
    if df.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], name="when"))

    return df.set_index("when")["amount"].resample("M").sum()
