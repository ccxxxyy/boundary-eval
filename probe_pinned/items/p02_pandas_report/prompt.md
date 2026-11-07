# Task: daily category report

You are writing a small reporting helper for an analytics job. Write a module
that defines:

```python
def category_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Count rows per value of df["category"].

    Return a DataFrame with exactly two columns, in this order:
    "category" and "count". Sort by count descending, then by category
    ascending. The index must be a fresh 0..n-1 RangeIndex.
    """


def to_timestamps(values: pd.Series) -> pd.Series:
    """Parse a Series of date strings into datetime64 values.

    The strings come from two upstream systems and the formats are mixed
    within one Series: some look like "2024-03-05" and some look like
    "2024/03/05 14:30". Every element must be parsed.
    """


def normalise_text(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df where every string cell is stripped and
    lower-cased. Cells that are not strings are left unchanged."""
```
