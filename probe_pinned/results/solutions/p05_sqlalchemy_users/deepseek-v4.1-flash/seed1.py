"""SQLAlchemy 1.4 persistence layer for users.

Defines the ``users`` table, schema creation, and a couple of small
repository-style helpers. Callers own the engine and session lifecycle.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base

Base = declarative_base()


class User(Base):
    """Table "users": id (integer primary key), email (string, unique,
    not null), display_name (string, nullable)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"User(id={self.id!r}, email={self.email!r}, display_name={self.display_name!r})"


def init_db(engine: Engine) -> None:
    """Create the tables for every model in this module."""
    Base.metadata.create_all(engine)


def get_or_create_user(
    session: Session,
    email: str,
    display_name: str | None = None,
) -> User:
    """Return the User with this email, creating and committing it if it does
    not exist. An existing user is returned unchanged, even if a different
    display_name is passed.
    """
    user = session.query(User).filter(User.email == email).one_or_none()
    if user is not None:
        return user

    user = User(email=email, display_name=display_name)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        # Another writer created the same email between our SELECT and INSERT.
        session.rollback()
        existing = session.query(User).filter(User.email == email).one()
        return existing

    session.refresh(user)
    return user


def emails_by_prefix(session: Session, prefix: str) -> list[str]:
    """Emails starting with `prefix`, sorted ascending."""
    rows = (
        session.query(User.email)
        .filter(User.email.startswith(prefix, autoescape=True))
        .order_by(User.email.asc())
        .all()
    )
    return [email for (email,) in rows]
