from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from probe_support import solution

sol = solution()


def _session():
    engine = create_engine("sqlite://")
    sol.init_db(engine)
    return Session(engine)


def test_create_then_get_returns_same_user():
    with _session() as session:
        first = sol.get_or_create_user(session, "a@x.io", "Ann")
        again = sol.get_or_create_user(session, "a@x.io", "Other")
        assert first.id == again.id
        assert again.display_name == "Ann"


def test_emails_by_prefix_sorted():
    with _session() as session:
        for email in ["bob@x.io", "al@x.io", "ann@x.io"]:
            sol.get_or_create_user(session, email)
        assert sol.emails_by_prefix(session, "a") == ["al@x.io", "ann@x.io"]
