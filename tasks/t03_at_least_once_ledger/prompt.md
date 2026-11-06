# Task: apply each ledger message exactly once

You are writing a consumer for an account ledger. Messages arrive from a queue
with at-least-once delivery, so the same message can arrive more than once and
messages can arrive in any order. Each message adjusts the account balance.
Applying one twice, or losing one, is a real accounting error.

## Your functions

Your module must define both of these.

```python
def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    """Apply this message's `amount_cents` to the balance, exactly once."""


def read_balance(store: DurableStore) -> int:
    """Return the current balance, in cents, from whatever `handle_message`
    has written. Called in a fresh process, so it must work from durable state
    alone."""
```

`amount_cents` may be negative. The balance starts at zero. How you lay out
your storage is up to you, as long as `read_balance` can recover the balance in
a process that has just started.

Put both functions in a single module. You may add helpers. You may import
from the Python standard library, and you may import the names used below:

```python
from faultline.api import DurableStore, StoreValueTooLarge
```

Do not import anything beyond those two, and do not try to read or write real
files, sockets or clocks: `store` is the only outside world you have.

## The API you are given

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
```

### One value is limited to 32 bytes

`put` and `compare_and_set` raise `StoreValueTooLarge` if the value is longer
than 32 bytes when encoded as UTF-8. Keys are not limited, and there is no
limit on how many keys you use.

This is a real constraint, not a formality: it means your durable state cannot
grow with the number of messages you have processed. A value has room for a
balance and one message id, and not for a balance and every message id you
have ever seen.

## How messages are delivered

The consumer is handed a batch of deliveries and calls `handle_message` once
per delivery, in order. A single batch already contains duplicates, because
delivery is at-least-once:

```
m_payroll  +250000
m_rent      -90000
m_payroll  +250000      <- the same message again
m_refund    +12500
m_bonus     +40000
m_rent      -90000      <- and again
m_fees       -1500
m_tax       -33000
m_bonus     +40000      <- and again
m_tax       -33000      <- and again
```

The same `message_id` always carries the same `amount_cents`. Six distinct
messages appear here, so the balance must end at
`250000 - 90000 + 12500 + 40000 - 1500 - 33000`.

## What can go wrong

This is the complete list. Nothing else is simulated.

1. **The process can be killed at any point.** Specifically, it can die
   immediately before any `store.put`, `store.compare_and_set` or
   `store.delete` takes effect, including part way through the batch. When the
   process dies, everything in memory is lost: local variables, module-level
   globals, caches, anything. Only data already written through `store`
   survives.

2. **Nothing is acknowledged until the whole batch is done.** If the process
   dies part way through, a new process is started and the queue redelivers
   **the entire batch from the beginning**. Messages your previous process
   already applied will be delivered again. This repeats until one run gets
   through the batch, and that run can itself die before acknowledging, in
   which case the whole batch arrives once more.

3. Calls never overlap: at most one `handle_message` runs at a time.

## Success criteria

After the final, acknowledged run of the batch:

- `read_balance(store)` returns exactly the sum of the **distinct** messages'
  amounts.
- Neither function raises, including never raising `StoreValueTooLarge`.
- No key in the store holds a value longer than 32 bytes.

These must hold for *every* point at which the process could have died, not
just the common case.
