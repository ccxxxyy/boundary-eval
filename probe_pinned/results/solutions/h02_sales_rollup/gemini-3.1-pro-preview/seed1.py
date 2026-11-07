import pandas as pd


def region_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Total `amount` per `region`."""
    # observed=True ensures we only include regions that actually appear in the data.
    # reset_index(name="total") converts the Series back to a DataFrame and renames the aggregated column.
    totals = df.groupby("region", observed=True)["amount"].sum().reset_index(name="total")
    
    # Sort by region (respecting categorical order) and ensure a default RangeIndex
    return totals.sort_values("region").reset_index(drop=True)


def monthly_totals(df: pd.DataFrame) -> pd.Series:
    """Total `amount` per calendar month."""
    if df.empty:
        # Safely handle empty DataFrames to avoid TypeErrors on missing/uncast columns
        return pd.Series(
            [], 
            index=pd.DatetimeIndex([], name="when"), 
            name="amount", 
            dtype=float
        )
        
    # resample("M") groups by month and sets the index to the last calendar day 
    # of the month at midnight. .sum() automatically fills missing months with 0.
    return df.set_index("when")["amount"].resample("M").sum()
