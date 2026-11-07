"""Validation and serialization for partner shipment records."""

from typing import Optional, Union

from pydantic import BaseModel, Field, StrictInt, StrictStr, conint


class InvalidShipment(Exception):
    """Raised for any record that does not satisfy the shipment rules."""


ParcelQuantity = conint(strict=True, ge=1)


class Shipment(BaseModel):
    # Strict types prevent pydantic v1 from coercing "007" to 7 or 7 to "7".
    ref: Union[StrictInt, StrictStr]
    qty: ParcelQuantity
    # Optional alone is not sufficient in pydantic v1: Field(...) keeps the key required.
    note: Optional[StrictStr] = Field(...)
    carrier: StrictStr

    class Config:
        extra = "ignore"


def parse_shipment(payload: dict) -> "Shipment":
    """Validate one decoded JSON record and return a Shipment."""
    try:
        if not isinstance(payload, dict):
            raise TypeError("shipment payload must be a JSON object")
        return Shipment.parse_obj(payload)
    except Exception as exc:
        raise InvalidShipment(str(exc)) from exc


def shipment_to_dict(shipment: "Shipment") -> dict:
    """Return a plain dict with exactly the keys ref, qty, note, carrier."""
    return {
        "ref": shipment.ref,
        "qty": shipment.qty,
        "note": shipment.note,
        "carrier": shipment.carrier,
    }
