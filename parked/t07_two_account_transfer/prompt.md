# Task: move money between two accounts

You are writing the consumer for a queue of internal transfers between two
accounts, `"A"` and `"B"`. Delivery is at-least-once, so the same transfer can
arrive more than once.

## Your functions

Your module must define both of these.

```python
def handle_transfer(
    transfer_id: str,
    source: str,
    target: str,
    amount_cents: int,
    store: DurableStore,
) -> str:
    """Move `amount_cents` from `source` to `target`, at most once.

    Return "applied" if the money moved, or "rejected" if it did not because
    `source` could not cover it.
    """


def read_balance(account: str, store: DurableStore) -> int:
    """Return `account`'s balance in cents, from durable state alone.
    Called in a fresh process."""
```

Put both in a single module. You may add helpers. You may import from the
Python standard library, and you may import the names used below:

```python
from faultline.api import DurableStore, StoreValueTooLarge
```

Do not import anything beyond those two, and do not try to read or write real
files, sockets or clocks: `store` is the only outside world you have.

## Opening balances

The store already contains the opening balances when your handler is first
called:

```
acct:A = "100000"
acct:B = "0"
```

How you lay out storage from there is up to you, as long as `read_balance`
can recover each account's balance in a process that has just started.

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
grow with the number of transfers you have processed.

## How transfers are delivered

The consumer is handed a batch and calls `handle_transfer` once per delivery,
in order. A single batch already contains duplicates, because delivery is
at-least-once:

```
t1  A -> B  60000
t2  A -> B  60000
t1  A -> B  60000      <- the same transfer again
t3  B -> A  20000
t2  A -> B  60000      <- and again
t4  A -> B  60000
t3  B -> A  20000      <- and again
t4  A -> B  60000      <- and again
```

The same `transfer_id` always carries the same source, target and amount.

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
   **the entire batch from the beginning**. Transfers your previous process
   already handled will be delivered again. This repeats until one run gets
   through the batch, and that run can itself die before acknowledging, in
   which case the whole batch arrives once more.

3. Calls never overlap: at most one `handle_transfer` runs at a time.

## Success criteria

After the final, acknowledged run of the batch:

- The two accounts hold exactly `100000` between them. No run, and no
  combination of crashes and redeliveries, may create or destroy money.
- Neither account is ever negative.
- Each distinct transfer has moved money **at most once**, and exactly once if
  it was accepted.
- **A transfer's answer never changes.** Whatever `handle_transfer` returns
  for a given `transfer_id` the first time, it must return for every later
  delivery of that same `transfer_id`. A transfer refused because the source
  could not cover it stays refused, even if the source can cover it by the
  time the transfer is delivered again.
- A transfer is rejected only if, at the point it was first decided, `source`
  could not cover `amount_cents`.
- Neither function raises, including never raising `StoreValueTooLarge`.

These must hold for *every* point at which the process could have died, not
just the common case.
