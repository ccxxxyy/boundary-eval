import pandas as pd

from probe_support import solution

sol = solution()


def test_category_counts_shape_and_order():
    df = pd.DataFrame({"category": ["b", "a", "b", "c", "a", "b"], "x": range(6)})
    out = sol.category_counts(df)
    assert list(out.columns) == ["category", "count"]
    assert out["category"].tolist() == ["b", "a", "c"]
    assert out["count"].tolist() == [3, 2, 1]
    assert list(out.index) == [0, 1, 2]


def test_to_timestamps_mixed_formats():
    s = pd.Series(["2024-03-05", "2024/03/06 14:30", "2024-03-07"])
    out = sol.to_timestamps(s)
    assert pd.api.types.is_datetime64_any_dtype(out)
    assert out.tolist() == [
        pd.Timestamp("2024-03-05"),
        pd.Timestamp("2024-03-06 14:30"),
        pd.Timestamp("2024-03-07"),
    ]


def test_normalise_text():
    df = pd.DataFrame({"name": ["  Ann ", "BOB"], "n": [1, 2]})
    out = sol.normalise_text(df)
    assert out["name"].tolist() == ["ann", "bob"]
    assert out["n"].tolist() == [1, 2]
    assert df["name"].tolist() == ["  Ann ", "BOB"]
