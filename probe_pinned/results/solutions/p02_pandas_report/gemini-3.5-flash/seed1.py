import pandas as pd


def category_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Count rows per value of df["category"].

    Return a DataFrame with exactly two columns, in this order:
    "category" and "count". Sort by count descending, then by category
    ascending. The index must be a fresh 0..n-1 RangeIndex.
    """
    counts = df["category"].value_counts(dropna=False)
    result = pd.DataFrame(
        {
            "category": counts.index,
            "count": counts.values,
        }
    )
    result = result.sort_values(
        by=["count", "category"],
        ascending=[False, True],
        ignore_index=True,
    )
    return result


def to_timestamps(values: pd.Series) -> pd.Series:
    """Parse a Series of date strings into datetime64 values.

    The strings come from two upstream systems and the formats are mixed
    within one Series: some look like "2024-03-05" and some look like
    "2024/03/05 14:30". Every element must be parsed.
    """
    return pd.to_datetime(values)


def normalise_text(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df where every string cell is stripped and
    lower-cased. Cells that are not strings are left unchanged.
    """
    return df.applymap(lambda cell: cell.strip().lower() if isinstance(cell, str) else cell)
