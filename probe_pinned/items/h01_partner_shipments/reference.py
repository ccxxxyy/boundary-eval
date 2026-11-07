from typing import Optional, Union

from pydantic import BaseModel, StrictInt, StrictStr, ValidationError, conint


class InvalidShipment(Exception):
    pass


class Shipment(BaseModel):
    ref: Union[StrictInt, StrictStr]
    qty: conint(strict=True, ge=1)
    note: Optional[StrictStr] = ...
    carrier: StrictStr


def parse_shipment(payload: dict) -> Shipment:
    if not isinstance(payload, dict):
        raise InvalidShipment("not an object")
    try:
        return Shipment(**payload)
    except (ValidationError, TypeError) as exc:
        raise InvalidShipment(str(exc)) from exc


def shipment_to_dict(shipment: Shipment) -> dict:
    return {"ref": shipment.ref, "qty": shipment.qty, "note": shipment.note, "carrier": shipment.carrier}
