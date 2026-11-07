from typing import Optional, Union

from pydantic import BaseModel, StrictInt, StrictStr, conint


class InvalidShipment(Exception):
    """Raised for any record that does not satisfy the rules below."""
    pass


class Shipment(BaseModel):
    # StrictInt and StrictStr prevent Pydantic from coercing types (e.g., "7" to 7 or 7 to "7")
    # This ensures the reference comes back exactly as it was sent.
    ref: Union[StrictInt, StrictStr]
    
    # strict=True prevents coercion from floats (like 2.5) or booleans.
    # ge=1 ensures the quantity is at least 1.
    qty: conint(strict=True, ge=1)
    
    # Optional[str] allows string or None. 
    # The `= ...` (Ellipsis) makes the field explicitly required in the payload.
    note: Optional[str] = ...
    
    carrier: str


def parse_shipment(payload: dict) -> Shipment:
    """Validate one decoded JSON record and return a Shipment. Raise InvalidShipment otherwise."""
    if not isinstance(payload, dict):
        raise InvalidShipment("Payload must be a dictionary.")
        
    try:
        return Shipment(**payload)
    except Exception as e:
        # Catching Exception covers Pydantic's ValidationError as well as 
        # potential TypeErrors if the payload structure is completely unexpected.
        raise InvalidShipment(str(e)) from e


def shipment_to_dict(shipment: Shipment) -> dict:
    """Return a plain dict with exactly the keys ref, qty, note, carrier."""
    return {
        "ref": shipment.ref,
        "qty": shipment.qty,
        "note": shipment.note,
        "carrier": shipment.carrier,
    }
