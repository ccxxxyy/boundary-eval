"""Validation layer for sign-up requests using Marshmallow."""

from marshmallow import Schema, fields, validate


class SignupError(Exception):
    """Raised when the input is invalid. `self.errors` must be a dict
    mapping each offending field name to a list of messages."""

    def __init__(self, errors: dict):
        super().__init__(errors)
        self.errors = errors


class SignupSchema(Schema):
    email = fields.Email(required=True)
    age = fields.Int(required=True, validate=validate.Range(min=13))
    nickname = fields.Str()


_signup_schema = SignupSchema()


def load_signup(data: dict) -> dict:
    """Validate `data` and return the cleaned fields as a plain dict.
    Raise SignupError if anything is invalid."""
    result, errors = _signup_schema.load(data)
    if errors:
        raise SignupError(errors)
    return result
