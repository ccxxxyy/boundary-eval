"""Check candidate silent traps for the harder probe. Run with each env's python."""

import sys


def show(label, fn):
    try:
        print(f"{label}: {fn()!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"{label}: RAISES {type(exc).__name__}: {str(exc)[:100]}")


try:
    import pydantic
    from typing import Optional, Union
    from pydantic import BaseModel

    class M(BaseModel):
        ref: Union[int, str]
        qty: int
        note: Optional[str]
        name: str

    print("pydantic", pydantic.VERSION)
    show("union '007'", lambda: M(ref="007", qty=1, note=None, name="a").ref)
    show("qty 2.5", lambda: M(ref=1, qty=2.5, note=None, name="a").qty)
    show("qty '3'", lambda: M(ref=1, qty="3", note=None, name="a").qty)
    show("qty True", lambda: M(ref=1, qty=True, note=None, name="a").qty)
    show("note missing", lambda: M(ref=1, qty=1, name="a").note)
    show("name 5", lambda: M(ref=1, qty=1, note=None, name=5).name)
    show("extra key", lambda: M(ref=1, qty=1, note=None, name="a", zzz=1).dict())
except ImportError:
    pass

try:
    import pandas as pd

    print("pandas", pd.__version__)
    df = pd.DataFrame({"k": pd.Categorical(["a", "a", "b"], categories=["a", "b", "c"]), "v": [1, 2, 3]})
    show("groupby cat size", lambda: df.groupby("k").size().to_dict())
    show("groupby cat sum", lambda: df.groupby("k")["v"].sum().to_dict())

    def mutate():
        d = pd.DataFrame({"p": [1.0, -2.0]})
        col = d["p"]
        col[col < 0] = 0
        return d["p"].tolist()

    show("CoW col mutate", mutate)
    show("resample ME", lambda: pd.Series([1, 2], index=pd.to_datetime(["2024-01-01", "2024-02-01"])).resample("ME").sum().tolist())
    show("to_datetime mixed", lambda: pd.to_datetime(pd.Series(["12/01/2024", "13/01/2024"])).dt.strftime("%Y-%m-%d").tolist())
    show("str dtype", lambda: str(pd.Series(["a", None]).dtype))
    show("sum empty object", lambda: pd.Series([], dtype=object).sum())
    show("value_counts name", lambda: pd.Series(["x", "y", "x"], name="c").value_counts().reset_index().columns.tolist())
    show("mean numeric_only default", lambda: pd.DataFrame({"g": [1, 1], "s": ["a", "b"], "n": [1, 3]}).groupby("g").mean().columns.tolist())
except ImportError:
    pass

print("python", sys.version.split()[0])
from datetime import datetime  # noqa: E402

show("fromisoformat Z", lambda: datetime.fromisoformat("2024-01-01T00:00:00Z"))
show("fromisoformat frac3", lambda: datetime.fromisoformat("2024-01-01T00:00:00.123+00:00"))
show("zip strict", lambda: list(zip([1], [2], strict=True)))
show("int|None runtime", lambda: eval("int | None"))
