# Task: validate incoming orders

You are adding input validation to an order-intake service. Write a module
that defines:

```python
class InvalidOrder(Exception):
    """Raised for any payload that does not satisfy the rules below."""


def parse_order(payload: dict) -> "Order":
    """Validate `payload` and return an Order. Raise InvalidOrder otherwise."""


def order_to_dict(order: "Order") -> dict:
    """Return a plain dict with exactly the keys sku, qty, customer_id."""
```

`Order` must be a pydantic model with these fields:

- `sku`: a string matching `^[A-Z]{3}-\d{4}$`, for example `"ABC-1234"`.
- `qty`: an integer, at least 1.
- `customer_id`: a string. A number is not a customer id: `{"customer_id": 42}`
  must be rejected, not converted to `"42"`.

Any key other than those three must be rejected. Every rejection, whatever the
reason, must surface as `InvalidOrder`.
