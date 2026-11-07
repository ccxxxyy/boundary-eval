# Task: user repository

You are writing the persistence layer for a small service, using the
SQLAlchemy ORM. Write a module that defines:

```python
class User:  # an ORM-mapped class
    """Table "users": id (integer primary key), email (string, unique,
    not null), display_name (string, nullable)."""


def init_db(engine) -> None:
    """Create the tables for every model in this module."""


def get_or_create_user(session, email: str, display_name: str | None = None) -> "User":
    """Return the User with this email, creating and committing it if it does
    not exist. An existing user is returned unchanged, even if a different
    display_name is passed."""


def emails_by_prefix(session, prefix: str) -> list[str]:
    """Emails starting with `prefix`, sorted ascending."""
```

Callers create the engine and session themselves, for example
`create_engine("sqlite://")` and `Session(engine)`.
