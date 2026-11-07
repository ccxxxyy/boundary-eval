from sqlalchemy import Column, Integer, String, select
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)


def init_db(engine):
    Base.metadata.create_all(engine)


def get_or_create_user(session, email, display_name=None):
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, display_name=display_name)
        session.add(user)
        session.commit()
    return user


def emails_by_prefix(session, prefix):
    rows = session.execute(
        select(User.email).where(User.email.startswith(prefix)).order_by(User.email)
    )
    return [email for (email,) in rows]
