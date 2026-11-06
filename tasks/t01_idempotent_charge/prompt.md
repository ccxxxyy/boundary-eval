# Task: charge a customer exactly once

You are writing the payment step of an order pipeline. Your function is invoked
by a queue worker. Implement it so that the customer is charged **exactly
once**, no matter how the process and the network misbehave.

## Your function

```python
def handle_order(
    order_id: str,
    amount_cents: int,
    store: DurableStore,
    gateway: PaymentGateway,
    new_id: Callable[[], str],
) -> str:
    """Charge `amount_cents` for `order_id` and return the gateway charge id."""
```

Put it in a single module. You may add helpers. You may import from the Python
standard library, and you may import the names used below:

```python
from faultline.api import DurableStore, GatewayTimeout, PaymentGateway
```

Do not import anything beyond those two, and do not try to read or write real
files, sockets or clocks: `store` and `gateway` are the only outside world you
have.

## The APIs you are given

```python
class DurableStore:
    """A durable key-value store.

    Each operation is atomic, and once it returns, its effect is durable: it
    survives a process crash. The four methods below are the whole API.
    """

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool:
        """Set `key` to `new` only if its current value equals `expected`
        (pass `None` to mean "the key must be absent").
        Returns whether the write happened."""

    def delete(self, key: str) -> None: ...


class PaymentGateway:
    """A third-party payment service, reached over the network."""

    def charge(self, idempotency_key: str, amount_cents: int) -> str:
        """Create a charge and return the gateway's charge id.

        The gateway deduplicates on `idempotency_key`: any number of calls
        sharing one key create at most one charge, and every such call returns
        that same charge id. Different keys create different charges.

        Raises GatewayTimeout.
        """

    def lookup(self, idempotency_key: str) -> str | None:
        """Return the id of the charge created with this idempotency key, or
        `None` if no such charge exists. Never raises GatewayTimeout."""


class GatewayTimeout(Exception):
    """The gateway did not answer."""


def new_id() -> str:
    """Return a fresh unique identifier, like `uuid4().hex`.

    Every call returns a different value, and the values are *not* reproducible
    after a restart: a new process calling `new_id()` gets different output
    than the one before it did.
    """
```

You only need those imports if you refer to the names directly; the objects
themselves are passed in as arguments.

## What can go wrong

This is the complete list. Nothing else is simulated.

1. **The process can be killed at any point.** Specifically, it can die
   immediately before any `store.put`, `store.compare_and_set`, `store.delete`
   or `gateway.charge` takes effect, and it can die after your function returns
   but before the queue records the acknowledgement. When the process dies,
   everything in memory is lost: local variables, module-level globals, caches,
   anything. Only data already written through `store`, and charges already
   created on the gateway, survive.

2. **The queue redelivers.** After a crash, or after a lost acknowledgement, a
   new process calls `handle_order` again with the same `order_id` and the same
   `amount_cents`. This repeats until one call returns and is acknowledged.
   Calls never overlap: at most one `handle_order` runs at a time.

3. **`gateway.charge` can raise `GatewayTimeout`.** When it does, the outcome
   is genuinely unknown: the charge may have been created on the gateway
   before the response was lost, or it may not have been created at all. Your
   code cannot tell which from the exception alone.

## Success criteria

After the final, acknowledged call returns, all of the following must hold:

- The gateway holds **exactly one** charge. Not zero, not two.
- That charge is for exactly `amount_cents`.
- The value your function returned equals that charge's id.
- Your function returned normally. Letting `GatewayTimeout`, or any other
  exception, escape `handle_order` on the acknowledged call is a failure.

These must hold for *every* possible combination of the failures listed above,
not just the common case.
