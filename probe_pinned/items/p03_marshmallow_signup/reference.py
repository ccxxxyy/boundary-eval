from marshmallow import Schema, fields, validate


class SignupError(Exception):
    def __init__(self, errors: dict):
        super().__init__(errors)
        self.errors = errors


class SignupSchema(Schema):
    email = fields.Email(required=True)
    age = fields.Integer(required=True, validate=validate.Range(min=13))
    nickname = fields.String()


def load_signup(data: dict) -> dict:
    result = SignupSchema().load(data)
    if result.errors:
        raise SignupError(dict(result.errors))
    return dict(result.data)
