import pandas as pd


def region_totals(df):
    out = df.groupby("region")["amount"].sum().rename("total").reset_index()
    out["region"] = out["region"].astype(str)
    return out.sort_values("region").reset_index(drop=True)


def monthly_totals(df):
    return df.set_index("when")["amount"].resample("ME").sum()
