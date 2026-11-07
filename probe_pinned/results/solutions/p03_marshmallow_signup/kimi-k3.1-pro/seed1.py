"""Validation for sign-up requests using marshmallow 2.x."""

from marshmallow import Schema, fields, validate


class SignupError(Exception):
    """Raised when sign-up input is invalid."""

    def __init__(self, errors: dict) -> None:
        self.errors = dict(errors)
        super().__init__(self.errors)


class _SignupSchema(Schema):
    email = fields.Email(required=True)
    age = fields.Integer(required=True, validate=validate.Range(min=13))
    nickname = fields.String(required=False)


_SIGNUP_SCHEMA = _SignupSchema()


def load_signup(data: dict) -> dict:
    """Validate and deserialize sign-up input, or raise SignupError."""
    # In marshmallow 2.x, non-strict load() returns an object with data/errors.
    result = _SIGNUP_SCHEMA.load(data)
    if result.errors:
        raise SignupError(result.errors)
    return dict(result.data)
