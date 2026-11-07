import pandas as pd

def category_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Count rows per value of df["category"].

    Return a DataFrame with exactly two columns, in this order:
    "category" and "count". Sort by count descending, then by category
    ascending. The index must be a fresh 0..n-1 RangeIndex.
    """
    # groupby.size() is used over value_counts() to ensure consistent 
    # column naming behavior in pandas 1.5.3
    counts = df.groupby("category").size().reset_index(name="count")
    
    # Sort by count (descending) and then category (ascending)
    counts = counts.sort_values(by=["count", "category"], ascending=[False, True])
    
    # Return with a fresh RangeIndex and ensure exact column order
    return counts[["category", "count"]].reset_index(drop=True)


def to_timestamps(values: pd.Series) -> pd.Series:
    """Parse a Series of date strings into datetime64 values.

    The strings come from two upstream systems and the formats are mixed
    within one Series: some look like "2024-03-05" and some look like
    "2024/03/05 14:30". Every element must be parsed.
    """
    # pd.to_datetime natively handles mixed standard formats in pandas 1.5.3
    return pd.to_datetime(values)


def normalise_text(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df where every string cell is stripped and
    lower-cased. Cells that are not strings are left unchanged."""
    # applymap applies the function element-wise across the entire DataFrame
    return df.applymap(lambda x: x.strip().lower() if isinstance(x, str) else x)
