from pydantic import BaseModel, Field, StrictStr, Extra, ValidationError

class InvalidOrder(Exception):
    """Raised for any payload that does not satisfy the rules below."""


class Order(BaseModel):
    sku: str = Field(..., regex=r"^[A-Z]{3}-\d{4}$")
    qty: int = Field(..., ge=1)
    customer_id: StrictStr

    class Config:
        extra = Extra.forbid


def parse_order(payload: dict) -> "Order":
    """Validate `payload` and return an Order. Raise InvalidOrder otherwise."""
    try:
        return Order(**payload)
    except (ValidationError, TypeError, ValueError) as e:
        raise InvalidOrder(str(e)) from e


def order_to_dict(order: "Order") -> dict:
    """Return a plain dict with exactly the keys sku, qty, customer_id."""
    return order.dict()
