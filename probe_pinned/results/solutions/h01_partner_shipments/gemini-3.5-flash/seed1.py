from typing import Optional, Union

from pydantic import BaseModel, Field, StrictInt, StrictStr, root_validator


class InvalidShipment(Exception):
    """Raised for any record that does not satisfy the rules below."""


class Shipment(BaseModel):
    ref: Union[StrictInt, StrictStr]
    qty: StrictInt = Field(..., ge=1)
    note: Optional[StrictStr] = Field(...)
    carrier: StrictStr

    @root_validator(pre=True)
    def _validate_keys(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            raise ValueError("Payload must be a dictionary")
        if "note" not in values:
            raise ValueError("Key 'note' is required in payload")
        return values


def parse_shipment(payload: dict) -> Shipment:
    """Validate one decoded JSON record and return a Shipment. Raise InvalidShipment otherwise."""
    if not isinstance(payload, dict):
        raise InvalidShipment("Payload must be a dictionary")
    try:
        return Shipment(**payload)
    except Exception as exc:
        raise InvalidShipment(str(exc)) from exc


def shipment_to_dict(shipment: Shipment) -> dict:
    """Return a plain dict with exactly the keys ref, qty, note, carrier."""
    return {
        "ref": shipment.ref,
        "qty": shipment.qty,
        "note": shipment.note,
        "carrier": shipment.carrier,
    }
