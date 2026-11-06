# Task: pay out through a legacy system, at most once

You are writing the payout step of a settlements pipeline. The transfer goes
through an old partner API that has no idempotency key and no way to look up
whether a request landed. Two calls move the money twice, and there is no
endpoint that will tell you whether your last call succeeded.

Paying a supplier twice is the expensive mistake here. A payout that a human
has to look at is not.

## Your function

```python
def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents`. Return "completed" or "needs_review"."""
```

Put it in a single module. You may add helpers. You may import from the Python
standard library, and you may import the names used below:

```python
from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout
```

Do not import anything beyond those two, and do not try to read or write real
files, sockets or clocks: `store` and `legacy` are the only outside world you
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


class LegacyTransferAPI:
    def transfer(self, amount_cents: int) -> str:
        """Move money. Returns the legacy system's reference for the transfer.

        There is no idempotency key and no way to look a transfer up
        afterwards. Two calls move the money twice.

        Raises TransferTimeout.
        """


class TransferTimeout(Exception):
    """The legacy system did not answer."""


def new_id() -> str:
    """Return a fresh unique identifier, like `uuid4().hex`.

    Every call returns a different value, and the values are *not* reproducible
    after a restart.
    """
```

The listing above is the complete `LegacyTransferAPI`. Do not call methods on
it that are not shown.

## The contract with the rest of the system

Your function reports its outcome two ways, and they must agree:

- It returns either the string `"completed"` or the string `"needs_review"`.
- It records the same word in the store key `payout:<payout_id>:state`.

`"completed"` is a promise that the money moved, exactly once.
`"needs_review"` hands the payout to a human reconciliation queue, saying the
outcome is unknown and must be checked by hand before anything else is tried.

## What can go wrong

This is the complete list. Nothing else is simulated.

1. **The process can be killed at any point.** Specifically, it can die
   immediately before any `store.put`, `store.compare_and_set`,
   `store.delete` or `legacy.transfer` takes effect, and it can die after your
   function returns but before the queue records the acknowledgement. When the
   process dies, everything in memory is lost: local variables, module-level
   globals, caches, anything. Only data already written through `store`, and
   transfers the legacy system has already executed, survive.

   Note what this means for `legacy.transfer`: the process can die at a moment
   when the transfer has already gone through, and also at a moment when it has
   not. A restarted process cannot tell those two situations apart.

2. **The queue redelivers.** After a crash, or after a lost acknowledgement, a
   new process calls `send_payout` again with the same `payout_id` and the same
   `amount_cents`. This repeats until one call returns and is acknowledged.
   Calls never overlap: at most one `send_payout` runs at a time.

3. **`legacy.transfer` can raise `TransferTimeout`.** When it does, the outcome
   is genuinely unknown: the money may have moved before the response was lost,
   or it may not have moved at all.

## Success criteria

After the final, acknowledged call returns, all of the following must hold:

- **At most one transfer** was executed by the legacy system. Two is a failure
  under every circumstance. There is no excuse for it and no fault listed above
  that makes it acceptable.
- If your function returned `"completed"`, then exactly one transfer was
  executed, and `payout:<payout_id>:state` holds `completed`.
- If your function returned `"needs_review"`, then
  `payout:<payout_id>:state` holds `needs_review`, so a human can actually
  find it.
- If **nothing went wrong at all** - no crash, no timeout - the result must be
  `"completed"`. Reporting a payout for manual review when the run was clean is
  a failure: it would make the safe answer "never do any work".
- Your function returned normally. Letting `TransferTimeout`, or any other
  exception, escape `send_payout` on the acknowledged call is a failure.

These must hold for *every* possible combination of the failures listed above,
not just the common case.
