from marshmallow import Schema, fields, validate

class SignupError(Exception):
    """Raised when the input is invalid. `self.errors` must be a dict
    mapping each offending field name to a list of messages."""

    def __init__(self, errors: dict):
        super().__init__("Invalid signup data")
        self.errors = errors


class SignupSchema(Schema):
    email = fields.Email(required=True)
    age = fields.Integer(required=True, validate=validate.Range(min=13))
    nickname = fields.String(required=False)


# Instantiate the schema once to reuse it
_signup_schema = SignupSchema()


def load_signup(data: dict) -> dict:
    """Validate `data` and return the cleaned fields as a plain dict.
    Raise SignupError if anything is invalid."""
    
    # In marshmallow 2.x, `load` returns a namedtuple: UnmarshalResult(data, errors)
    # Unknown keys are ignored and excluded from `result.data` by default.
    result = _signup_schema.load(data)
    
    if result.errors:
        raise SignupError(result.errors)
        
    return result.data
