"""Validation for sign-up requests."""

from __future__ import annotations

from marshmallow import Schema, ValidationError, fields, validate


class SignupError(Exception):
    """Raised when sign-up input is invalid.

    ``self.errors`` maps field names to lists of validation messages.
    """

    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__("Invalid sign-up data")


class _SignupSchema(Schema):
    email = fields.Email(required=True)
    age = fields.Integer(required=True, validate=validate.Range(min=13))
    nickname = fields.String(required=False)


def load_signup(data: dict) -> dict:
    """Validate ``data`` and return only the cleaned sign-up fields."""
    if not isinstance(data, dict):
        raise SignupError({"_schema": ["Invalid input type."]})

    schema = _SignupSchema()

    try:
        cleaned, errors = schema.load(data)
    except ValidationError as exc:
        errors = exc.messages
        if isinstance(errors, list):
            errors = {"_schema": errors}
        elif isinstance(errors, str):
            errors = {"_schema": [errors]}
        raise SignupError(errors) from None

    if errors:
        raise SignupError(errors)

    return {
        key: cleaned[key]
        for key in ("email", "age", "nickname")
        if key in cleaned
    }
