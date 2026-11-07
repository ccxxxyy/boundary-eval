# Task: sales roll-ups for the finance dashboard

Write a module with two pandas helpers used by the finance dashboard.

```python
import pandas as pd


def region_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Total `amount` per `region`."""


def monthly_totals(df: pd.DataFrame) -> pd.Series:
    """Total `amount` per calendar month."""
```

`region_totals`:

- `df` has columns `region` and `amount`. Upstream, `region` is loaded as a
  pandas categorical whose categories are every region the company has ever
  had, so many categories have no rows in a given frame.
- Return a DataFrame with exactly the columns `region` and `total`, one row per
  region that actually occurs in `df` (a region with no rows must not appear),
  sorted by region, with a default RangeIndex.

`monthly_totals`:

- `df` has a `when` column of naive datetime64 timestamps and an `amount` column.
- Return a Series of summed `amount`, indexed by the last calendar day of each
  month (at midnight), covering every month from the first to the last
  timestamp in `df`. Months in between with no rows have total 0.
