import pandas as pd


def category_counts(df: pd.DataFrame) -> pd.DataFrame:
    counts = df.groupby("category").size().rename("count").reset_index()
    counts = counts.sort_values(["count", "category"], ascending=[False, True])
    return counts.reset_index(drop=True)


def to_timestamps(values: pd.Series) -> pd.Series:
    return values.map(pd.Timestamp)


def normalise_text(df: pd.DataFrame) -> pd.DataFrame:
    return df.applymap(lambda v: v.strip().lower() if isinstance(v, str) else v)
