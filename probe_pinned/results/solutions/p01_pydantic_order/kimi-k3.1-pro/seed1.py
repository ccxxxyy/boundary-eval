from pydantic import BaseModel, StrictStr, ValidationError, conint, constr


class InvalidOrder(Exception):
    """Raised for any payload that does not satisfy the rules below."""


class Order(BaseModel):
    sku: constr(strict=True, regex=r"^[A-Z]{3}-\d{4}$")
    qty: conint(strict=True, ge=1)
    customer_id: StrictStr

    class Config:
        extra = "forbid"


def parse_order(payload: dict) -> "Order":
    """Validate `payload` and return an Order. Raise InvalidOrder otherwise."""
    try:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict")
        return Order.parse_obj(payload)
    except (ValidationError, TypeError, ValueError) as exc:
        raise InvalidOrder("invalid order payload") from exc


def order_to_dict(order: "Order") -> dict:
    """Return a plain dict with exactly the keys sku, qty, customer_id."""
    return {
        "sku": order.sku,
        "qty": order.qty,
        "customer_id": order.customer_id,
    }
