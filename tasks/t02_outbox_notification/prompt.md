# Task: ship an order and notify downstream

You are writing the shipping step of an order pipeline. Your function is
invoked by a queue worker. It has to do two things that live in two different
systems: record that the order shipped, and tell downstream services about it.

## Your function

```python
def mark_shipped(
    order_id: str,
    store: DurableStore,
    bus: EventBus,
    new_id: Callable[[], str],
) -> None:
    """Record that `order_id` shipped, and notify downstream."""
```

Put it in a single module. You may add helpers. You may import from the Python
standard library, and you may import the names used below:

```python
from faultline.api import BrokerTimeout, DurableStore, EventBus
```

Do not import anything beyond those two, and do not try to read or write real
files, sockets or clocks: `store` and `bus` are the only outside world you
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


class EventBus:
    """A message broker, reached over the network."""

    def publish(self, event_id: str, payload: str) -> None:
        """Hand a message to the broker for delivery downstream.

        The broker does **not** deduplicate. Every message it accepts is
        delivered, duplicates included. `event_id` is carried along with the
        message and is what a consumer would deduplicate on.

        Raises BrokerTimeout.
        """


class BrokerTimeout(Exception):
    """The broker did not answer."""


def new_id() -> str:
    """Return a fresh unique identifier, like `uuid4().hex`.

    Every call returns a different value, and the values are *not* reproducible
    after a restart: a new process calling `new_id()` gets different output
    than the one before it did.
    """
```

## The contract with the rest of the system

- An order counts as shipped when the store key `order:<order_id>:status`
  holds exactly the string `shipped`.
- The downstream notification for an order is a message whose payload is
  exactly `order_shipped:<order_id>`.
- Downstream consumers deduplicate on `event_id`. Two messages carrying the
  same `event_id` are understood to be one notification delivered twice. Two
  messages carrying *different* event ids are understood to be two separate
  notifications, and the consumer will act twice.
- A consumer that receives the notification immediately reads the order back
  from the store, and expects to find it shipped.

## What can go wrong

This is the complete list. Nothing else is simulated.

1. **The process can be killed at any point.** Specifically, it can die
   immediately before any `store.put`, `store.compare_and_set`,
   `store.delete` or `bus.publish` takes effect, and it can die after your
   function returns but before the queue records the acknowledgement. When the
   process dies, everything in memory is lost: local variables, module-level
   globals, caches, anything. Only data already written through `store`, and
   messages the broker has already accepted, survive.

2. **The queue redelivers.** After a crash, or after a lost acknowledgement, a
   new process calls `mark_shipped` again with the same `order_id`. This
   repeats until one call returns and is acknowledged. Calls never overlap: at
   most one `mark_shipped` runs at a time.

3. **`bus.publish` can raise `BrokerTimeout`.** When it does, the outcome is
   genuinely unknown: the broker may have accepted the message before the
   response was lost, or it may not have accepted it at all. Your code cannot
   tell which from the exception alone.

## Success criteria

After the final, acknowledged call returns, all of the following must hold:

- `order:<order_id>:status` holds `shipped`.
- **At least one** message with payload `order_shipped:<order_id>` was
  delivered. Zero is a failure: the order shipped and nobody downstream was
  told.
- **All** such messages carry the same `event_id`. More than one distinct
  event id means the consumer acts on the notification more than once.
- **No** such message was published at a moment when
  `order:<order_id>:status` did not already hold `shipped`. Otherwise a
  consumer can read the order back and find it not shipped.
- Your function returned normally. Letting `BrokerTimeout`, or any other
  exception, escape `mark_shipped` on the acknowledged call is a failure.

These must hold for *every* possible combination of the failures listed above,
not just the common case.
