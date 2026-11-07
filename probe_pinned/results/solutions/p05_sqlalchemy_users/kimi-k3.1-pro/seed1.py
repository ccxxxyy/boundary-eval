"""User persistence models and repository helpers."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base


Base = declarative_base()


class User(Base):
    """A row in the ``users`` table."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)


def init_db(engine: Engine) -> None:
    """Create all tables registered with this module's metadata."""
    Base.metadata.create_all(bind=engine)


def get_or_create_user(
    session: Session,
    email: str,
    display_name: str | None = None,
) -> User:
    """Return an existing user, or create and commit a new one."""
    user = session.query(User).filter(User.email == email).one_or_none()
    if user is not None:
        return user

    user = User(email=email, display_name=display_name)
    session.add(user)

    try:
        session.commit()
    except IntegrityError:
        # Another transaction may have inserted the same email after the
        # initial lookup. The unique constraint makes that insert fail; the
        # concurrently created user is the one that should be returned.
        session.rollback()
        existing = (
            session.query(User).filter(User.email == email).one_or_none()
        )
        if existing is None:
            raise
        return existing

    session.refresh(user)
    return user


def emails_by_prefix(session: Session, prefix: str) -> list[str]:
    """Return emails beginning with the literal prefix, sorted ascending."""
    # Escape LIKE metacharacters so that '%', '_', and '\' in the prefix are
    # matched literally rather than treated as pattern syntax.
    escaped_prefix = (
        prefix.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )

    rows = (
        session.query(User.email)
        .filter(User.email.like(escaped_prefix + "%", escape="\\"))
        .order_by(User.email.asc())
        .all()
    )
    return [email for (email,) in rows]
