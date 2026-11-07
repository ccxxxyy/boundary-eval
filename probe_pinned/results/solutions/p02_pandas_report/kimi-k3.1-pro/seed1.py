"""Helpers for producing daily category reports."""

from __future__ import annotations

import pandas as pd


def category_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Count rows per value of ``df["category"]``."""
    counts = (
        df["category"]
        .value_counts()
        .rename_axis("category")
        .reset_index(name="count")
    )

    counts = counts.sort_values(
        by=["count", "category"],
        ascending=[False, True],
    )

    return counts.reset_index(drop=True)[["category", "count"]]


def to_timestamps(values: pd.Series) -> pd.Series:
    """Parse mixed date-string formats into a datetime64 Series."""
    # Parse elements individually so pandas does not infer one format from the
    # first value and apply it to the entire mixed-format Series.
    parsed = values.map(lambda value: pd.to_datetime(value, errors="raise"))
    return parsed.astype("datetime64[ns]")


def normalise_text(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with string cells stripped and lower-cased."""
    return df.applymap(
        lambda value: value.strip().lower()
        if isinstance(value, str)
        else value
    )
