import pandas as pd


def region_totals(df: pd.DataFrame) -> pd.DataFrame:
    totals = df.groupby("region", observed=True, sort=True)["amount"].sum()
    out = totals.rename("total").reset_index()
    out["region"] = out["region"].astype(str)
    return out.sort_values("region").reset_index(drop=True)


def monthly_totals(df: pd.DataFrame) -> pd.Series:
    return df.set_index("when")["amount"].resample("M").sum()
