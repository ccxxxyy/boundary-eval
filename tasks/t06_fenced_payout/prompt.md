# Task: pay out once, even when another worker takes over

You are writing the handler for a payout job. The job arrives from a queue
with at-least-once delivery, and it pays a supplier through an old banking
integration.

## Your function

```python
def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id,
) -> str:
    """Pay out `amount_cents` at most once.

    Return "completed" if the money has moved exactly once and that fact is
    durably recorded. Return "needs_review" if the outcome is unknown or
    cannot be completed safely, so a person can reconcile it.
    """
```

Put it in a single module. You may add helpers. You may import from the
Python standard library. Do not import anything else, and do not try to read
or write real files, sockets or clocks: `store` and `legacy` are the only
outside world you have. `new_id()` returns a fresh unique string each time it
is called, as `uuid4().hex` would.

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
    """The banking integration."""

    def transfer(self, amount_cents: int) -> str:
        """Move the money. Returns the bank's reference for the transfer.

        Two calls move the money twice. There is no idempotency parameter,
        and there is no way to ask afterwards whether a transfer happened.

        May raise `TransferTimeout`, in which case the transfer may or may
        not have taken effect, and you cannot find out which.
        """
```

The listing above is the complete `LegacyTransferAPI`. Do not call methods on
it that are not shown.

## What can go wrong

This is the complete list. Nothing else is simulated.

1. **The process can be killed at any point.** Specifically, it can die
   immediately before any `store.put`, `store.compare_and_set`,
   `store.delete` or `legacy.transfer` takes effect. When the process dies,
   everything in memory is lost: local variables, module-level globals,
   caches, anything. Only data already written through `store` survives.

2. **The job is redelivered until it is acknowledged.** If the process dies,
   a new process is started and `send_payout` is called again with the same
   arguments.

3. **`legacy.transfer` can time out**, raising `TransferTimeout`. The
   transfer may have taken effect before the response was lost, or may not
   have taken effect at all. There is no way to tell, now or later.

4. **Another worker can take over while you are still running.** The queue
   cannot tell a dead worker from a slow one. If your handler takes too long,
   the queue presumes it dead and hands the same job to a second worker,
   which runs `send_payout` from the start, to completion, against the same
   store and the same bank.

   Your process is *not* dead. It continues from exactly where it was, with
   every value it had already read, and its later writes and calls still take
   effect. This can happen at any single point during your run.

## Success criteria

Across everything that runs - your handler, a redelivery after a crash, and a
second worker that took over:

- `legacy.transfer` moves the money **at most once**. Never twice, under any
  combination of the above.
- No handler raises, including never letting `TransferTimeout` escape.
- Every handler returns either `"completed"` or `"needs_review"`.
- A handler returns `"completed"` only if the money moved exactly once.
- When everything finishes, `payout:<payout_id>:state` holds either
  `"completed"` or `"needs_review"`, so the payout can be reconciled. It says
  `"completed"` only if the money moved exactly once.
- If nothing goes wrong at all - no crash, no timeout, no takeover - the
  payout completes and the money moves once. Escalating unconditionally is
  not a solution.

These must hold for *every* point at which the process could have died, every
point at which another worker could have taken over, and every outcome of the
transfer.
