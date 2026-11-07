from sqlalchemy import Column, Integer, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    """Table "users": id (integer primary key), email (string, unique,
    not null), display_name (string, nullable)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)


def init_db(engine) -> None:
    """Create the tables for every model in this module."""
    Base.metadata.create_all(engine)


def get_or_create_user(session, email: str, display_name: str | None = None) -> "User":
    """Return the User with this email, creating and committing it if it does
    not exist. An existing user is returned unchanged, even if a different
    display_name is passed."""
    user = session.query(User).filter_by(email=email).first()
    if user is not None:
        return user

    user = User(email=email, display_name=display_name)
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        user = session.query(User).filter_by(email=email).first()
        if user is None:
            raise
            
    return user


def emails_by_prefix(session, prefix: str) -> list[str]:
    """Emails starting with `prefix`, sorted ascending."""
    return [
        email for (email,) in
        session.query(User.email)
        .filter(User.email.startswith(prefix))
        .order_by(User.email.asc())
    ]
