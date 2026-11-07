"""Validation for incoming order payloads."""

import re

from pydantic import (
    BaseModel,
    Extra,
    StrictInt,
    StrictStr,
    ValidationError,
    validator,
)

_SKU_RE = re.compile(r"^[A-Z]{3}-\d{4}$")


class InvalidOrder(Exception):
    """Raised for any payload that does not satisfy the order rules."""


class Order(BaseModel):
    sku: StrictStr
    qty: StrictInt
    customer_id: StrictStr

    class Config:
        extra = Extra.forbid

    @validator("sku")
    def _validate_sku(cls, value: str) -> str:
        if _SKU_RE.fullmatch(value) is None:
            raise ValueError("sku must match ^[A-Z]{3}-\\d{4}$")
        return value

    @validator("qty")
    def _validate_qty(cls, value: int) -> int:
        if value < 1:
            raise ValueError("qty must be at least 1")
        return value


def parse_order(payload: dict) -> Order:
    """Validate payload and return an Order, or raise InvalidOrder."""
    if not isinstance(payload, dict):
        raise InvalidOrder("order payload must be a dict")

    try:
        return Order.parse_obj(payload)
    except ValidationError as exc:
        raise InvalidOrder("invalid order payload") from exc
    except (TypeError, ValueError) as exc:
        raise InvalidOrder("invalid order payload") from exc


def order_to_dict(order: Order) -> dict:
    """Return a plain dict with exactly sku, qty, and customer_id."""
    return {
        "sku": order.sku,
        "qty": order.qty,
        "customer_id": order.customer_id,
    }
