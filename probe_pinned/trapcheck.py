"""Confirm, in the installed environment, which version-specific behaviours actually hold."""

import importlib.util
import sys


def has(mod):
    return importlib.util.find_spec(mod) is not None


print(sys.version.split()[0])

if has("pydantic"):
    import pydantic
    from pydantic import BaseModel, Field

    print("pydantic", pydantic.VERSION)
    try:
        class M(BaseModel):
            sku: str = Field(pattern=r"^[A-Z]{3}-\d{4}$")
            qty: int
            model_config = {"extra": "forbid"}

        m = M(sku="bad", qty="3", junk=1)
        print("  pattern= + model_config accepted silently:", m)
    except Exception as e:
        print("  raised:", type(e).__name__, str(e)[:120])
    try:
        class S(BaseModel):
            id: str

        print("  int -> str field:", repr(S(id=123).id))
    except Exception as e:
        print("  int -> str raised:", type(e).__name__)

if has("pandas"):
    import pandas as pd

    print("pandas", pd.__version__)
    df = pd.DataFrame({"category": ["a", "b", "a"]})
    print("  value_counts().reset_index() columns:", list(df["category"].value_counts().reset_index().columns))
    print("  has DataFrame.map:", hasattr(pd.DataFrame, "map"))
    try:
        pd.to_datetime(["2024-01-02", "02/03/2024"], format="mixed")
        print("  format='mixed' ok")
    except Exception as e:
        print("  format='mixed' raised:", type(e).__name__)
    g = pd.DataFrame({"k": ["x", "x"], "n": [1, 3], "s": ["p", "q"]}).groupby("k")
    try:
        print("  groupby.mean with str col:", g.mean().to_dict())
    except Exception as e:
        print("  groupby.mean raised:", type(e).__name__)

if has("marshmallow"):
    import marshmallow
    from marshmallow import Schema, fields

    print("marshmallow", getattr(marshmallow, "__version__", "?"))

    class U(Schema):
        email = fields.Email(required=True)

    try:
        r = U().load({"email": "nope"})
        print("  invalid load returned:", r)
    except Exception as e:
        print("  invalid load raised:", type(e).__name__)

if has("packaging"):
    import packaging
    from packaging.version import parse

    print("packaging", packaging.__version__)
    try:
        v = parse("not-a-version")
        print("  parse('not-a-version') ->", type(v).__name__)
    except Exception as e:
        print("  parse raised:", type(e).__name__)

if has("sqlalchemy"):
    import sqlalchemy

    print("SQLAlchemy", sqlalchemy.__version__)
    try:
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column  # noqa: F401

        print("  2.0-style typed declarative: available")
    except ImportError as e:
        print("  2.0-style typed declarative: ImportError", str(e)[:80])
