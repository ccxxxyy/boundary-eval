"""Sales roll-up helpers for the finance dashboard."""

import pandas as pd


__all__ = ["region_totals", "monthly_totals"]


def region_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Return the total ``amount`` for each region present in ``df``."""
    totals = (
        df.groupby("region", observed=True, sort=True, dropna=True)["amount"]
        .sum()
        .rename("total")
        .reset_index()
    )
    return totals.loc[:, ["region", "total"]].reset_index(drop=True)


def monthly_totals(df: pd.DataFrame) -> pd.Series:
    """Return monthly totals, including zero-total months within the date range."""
    amounts = df.set_index("when")["amount"]

    if amounts.empty:
        return pd.Series(
            index=pd.DatetimeIndex([], name="when"),
            name="amount",
            dtype=amounts.dtype,
        )

    # Month-end resampling labels each bucket with the last calendar day at
    # midnight and creates zero-valued buckets for months without rows.
    return amounts.sort_index().resample("M").sum()
