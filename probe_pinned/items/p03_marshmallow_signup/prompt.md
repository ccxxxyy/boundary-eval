# Task: validate sign-up requests

You are writing the validation layer for a sign-up endpoint, using
marshmallow. Write a module that defines:

```python
class SignupError(Exception):
    """Raised when the input is invalid. `self.errors` must be a dict
    mapping each offending field name to a list of messages."""

    def __init__(self, errors: dict): ...


def load_signup(data: dict) -> dict:
    """Validate `data` and return the cleaned fields as a plain dict.
    Raise SignupError if anything is invalid."""
```

Rules, expressed as a marshmallow schema:

- `email`: required, must be a valid email address.
- `age`: required integer, at least 13.
- `nickname`: optional string; if absent, it is absent from the result too.

Unknown keys may be ignored.
