"""Validation for partner shipment feed records."""

from typing import Any, Optional, Union

from pydantic import BaseModel, Field, StrictInt, StrictStr, ValidationError, validator


class InvalidShipment(Exception):
    """Raised for any record that does not satisfy the shipment rules."""


class Shipment(BaseModel):
    ref: Union[StrictInt, StrictStr]
    qty: int = Field(..., ge=1)
    note: Optional[str] = Field(...)
    carrier: StrictStr

    class Config:
        smart_union = True
        extra = "ignore"

    @validator("ref", pre=True)
    def _validate_ref(cls, value: Any) -> Union[int, str]:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("ref must be an integer or a string")
        return value

    @validator("qty", pre=True)
    def _validate_qty(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("qty must be a whole number")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise ValueError("qty must be a whole number")

    @validator("note", pre=True)
    def _validate_note(cls, value: Any) -> Optional[str]:
        if value is not None and not isinstance(value, str):
            raise ValueError("note must be a string or null")
        return value

    @validator("carrier", pre=True)
    def _validate_carrier(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("carrier must be a string")
        return value


def parse_shipment(payload: dict) -> Shipment:
    if not isinstance(payload, dict):
        raise InvalidShipment("shipment payload must be a JSON object")

    try:
        return Shipment(**payload)
    except ValidationError as exc:
        raise InvalidShipment(str(exc)) from None
    except (TypeError, ValueError) as exc:
        raise InvalidShipment(str(exc)) from None
    except Exception:
        raise InvalidShipment("invalid shipment") from None


def shipment_to_dict(shipment: Shipment) -> dict:
    return {
        "ref": shipment.ref,
        "qty": shipment.qty,
        "note": shipment.note,
        "carrier": shipment.carrier,
    }
