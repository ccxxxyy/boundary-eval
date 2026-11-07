"""Helpers for the daily category report."""

from __future__ import annotations

from dateutil import parser
import pandas as pd


def category_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Count rows per value of df["category"].

    Return a DataFrame with exactly two columns, in this order:
    "category" and "count". Sort by count descending, then by category
    ascending. The index must be a fresh 0..n-1 RangeIndex.
    """
    counts = (
        df.groupby("category", dropna=False, observed=True)["category"]
        .size()
        .reset_index(name="count")
    )
    counts = (
        counts.sort_values(
            ["count", "category"],
            ascending=[False, True],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )
    return counts.loc[:, ["category", "count"]]


def to_timestamps(values: pd.Series) -> pd.Series:
    """Parse a Series of date strings into datetime64 values.

    The strings come from two upstream systems and the formats are mixed
    within one Series: some look like "2024-03-05" and some look like
    "2024/03/05 14:30". Every element must be parsed.
    """
    def _parse(value):
        if pd.isna(value):
            return pd.NaT
        return parser.parse(str(value))

    return pd.to_datetime(values.map(_parse))


def normalise_text(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df where every string cell is stripped and
    lower-cased. Cells that are not strings are left unchanged."""
    return df.applymap(
        lambda value: value.strip().lower()
        if isinstance(value, str)
        else value
    )
