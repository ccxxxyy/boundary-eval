from typing import Optional, Union

from pydantic import BaseModel, Field, ValidationError


class InvalidShipment(Exception):
    pass


class Shipment(BaseModel):
    ref: Union[int, str]
    qty: int = Field(..., ge=1)
    note: Optional[str]
    carrier: str


def parse_shipment(payload):
    try:
        return Shipment(**payload)
    except ValidationError as exc:
        raise InvalidShipment(str(exc)) from exc


def shipment_to_dict(shipment):
    return {"ref": shipment.ref, "qty": shipment.qty, "note": shipment.note, "carrier": shipment.carrier}
