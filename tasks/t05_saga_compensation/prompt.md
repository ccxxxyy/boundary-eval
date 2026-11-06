# Task: book a seat, or give it back

You are writing the booking step of a ticketing pipeline. It touches two
systems: a seat inventory and a payment gateway. Both have to end up agreeing,
and there is no transaction spanning them.

A customer who is charged for a seat they do not hold is the worst outcome. A
seat held for a booking that was never paid for is the second worst: that seat
can never be sold again.

## Your function

```python
def book_seat(
    booking_id: str,
    seat: str,
    amount_cents: int,
    store: DurableStore,
    inventory: SeatInventory,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Book `seat` for `booking_id`. Return "confirmed" or "declined"."""
```

Put it in a single module. You may add helpers. You may import from the Python
standard library, and you may import the names used below:

```python
from faultline.api import (
    ChargeDeclined,
    DurableStore,
    GatewayTimeout,
    InventoryTimeout,
    PaymentGateway,
    SeatInventory,
)
```

Do not import anything beyond those two, and do not try to read or write real
files, sockets or clocks: `store`, `inventory` and `gateway` are the only
outside world you have.

## The APIs you are given

```python
class DurableStore:
    """A durable key-value store.

    Each operation is atomic, and once it returns, its effect is durable: it
    survives a process crash. The four methods below are the whole API.
    """

    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...
    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class SeatInventory:
    def hold(self, booking_id: str, seat: str) -> None:
        """Reserve `seat` for `booking_id`.

        Idempotent: holding the same seat for the same booking twice is one
        hold.

        Raises InventoryTimeout.
        """

    def release(self, booking_id: str) -> None:
        """Give the seat back.

        Idempotent: releasing an unknown or already-released booking does
        nothing.

        Raises InventoryTimeout.
        """

    def held_seat(self, booking_id: str) -> str | None:
        """Which seat this booking currently holds, or None.
        Never raises InventoryTimeout."""


class PaymentGateway:
    def charge(self, idempotency_key: str, amount_cents: int) -> str:
        """Create a charge and return the gateway's charge id.

        The gateway deduplicates on `idempotency_key`: any number of calls
        sharing one key create at most one charge, and every such call returns
        that same charge id.

        Raises GatewayTimeout, and raises ChargeDeclined.
        """

    def lookup(self, idempotency_key: str) -> str | None:
        """Return the id of the charge created with this idempotency key, or
        None if no such charge exists. Never raises."""


class GatewayTimeout(Exception):
    """The gateway did not answer."""


class InventoryTimeout(Exception):
    """The inventory service did not answer."""


class ChargeDeclined(Exception):
    """The gateway refused the charge. No money moved, and presenting the same
    idempotency key again gets the same refusal."""


def new_id() -> str:
    """Return a fresh unique identifier, like `uuid4().hex`.

    Every call returns a different value, and the values are *not* reproducible
    after a restart.
    """
```

## The contract with the rest of the system

- Your function returns either `"confirmed"` or `"declined"`.
- `"confirmed"` means the customer was charged once and holds the seat.
- `"declined"` means no money was taken and the seat is available to others.

## What can go wrong

This is the complete list. Nothing else is simulated.

1. **The process can be killed at any point.** Specifically, it can die
   immediately before any `store.put`, `store.compare_and_set`,
   `store.delete`, `inventory.hold`, `inventory.release` or `gateway.charge`
   takes effect, and it can die after your function returns but before the
   queue records the acknowledgement. When the process dies, everything in
   memory is lost: local variables, module-level globals, caches, anything.
   Only data written through `store`, holds the inventory has taken, and
   charges the gateway has created, survive.

2. **The queue redelivers.** After a crash, or after a lost acknowledgement, a
   new process calls `book_seat` again with the same arguments. This repeats
   until one call returns and is acknowledged. Calls never overlap.

3. **`inventory.hold`, `inventory.release` and `gateway.charge` can time out.**
   When they do, the outcome is genuinely unknown: the request may have been
   applied before the response was lost, or not applied at all. Your code
   cannot tell which from the exception alone.

4. **`gateway.charge` can raise `ChargeDeclined`.** This one is *not*
   ambiguous: no money moved, and the same idempotency key will be refused
   again. Retrying it is pointless.

## Success criteria

After the final, acknowledged call returns, all of the following must hold:

- If your function returned `"confirmed"`: exactly one charge exists, for
  exactly `amount_cents`, and `booking_id` holds `seat`.
- If your function returned `"declined"`: no charge exists, and `booking_id`
  holds no seat.
- Under no circumstances does a charge exist while the booking holds no seat.
  That is a customer who paid for nothing.
- Under no circumstances does the booking still hold a seat after a
  `"declined"` result. That seat is lost inventory.
- If **nothing went wrong at all** - no crash, no timeout, no decline - the
  result must be `"confirmed"`.
- If the **only** thing that went wrong was a decline - no crash, no timeout -
  the result must be `"declined"`.
- Your function returned normally. Letting any exception escape `book_seat` on
  the acknowledged call is a failure.

These must hold for *every* possible combination of the failures listed above,
not just the common case.
