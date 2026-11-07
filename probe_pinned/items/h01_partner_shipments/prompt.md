# Task: validate a partner's shipment feed

A logistics partner posts shipment records to us as JSON. Write a module that
defines:

```python
class InvalidShipment(Exception):
    """Raised for any record that does not satisfy the rules below."""


def parse_shipment(payload: dict) -> "Shipment":
    """Validate one decoded JSON record and return a Shipment. Raise InvalidShipment otherwise."""


def shipment_to_dict(shipment: "Shipment") -> dict:
    """Return a plain dict with exactly the keys ref, qty, note, carrier."""
```

`Shipment` must be a pydantic model with these fields:

- `ref`: the partner's own reference. Partners send it either as a JSON integer
  or as a JSON string. It is opaque to us and must come back exactly as it was
  sent, same type and same value: `7` stays `7`, `"007"` stays `"007"`.
- `qty`: a whole number of parcels, at least 1. `2.5` parcels is invalid.
- `note`: the key is required in every record; its value is either a string or
  `null`.
- `carrier`: a string.

Every rejection, whatever the reason, must surface as `InvalidShipment`.
