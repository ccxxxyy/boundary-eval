"""Known-correct, and a completely different storage design.

Each message's contribution is its own key, so the write that records "this
message was applied" *is* the write that records its amount. The balance is
not stored at all - it is derived by summing. Nothing to keep consistent,
because nothing is duplicated.

Included to prove the grader judges the invariant rather than the shape: this
keeps no balance key, no dedup set, and no compare-and-set.
"""

from __future__ import annotations

from faultline.api import DurableStore

PREFIX = "applied:"
INDEX_KEY = "applied:index"


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    key = f"{PREFIX}{message_id}"
    if store.get(key) is not None:
        return
    # The index has to be durable before the amount it points at, or a crash
    # could leave an amount that read_balance never finds. Writing it first can
    # only ever leave an index entry with no amount, which reads as zero and is
    # fixed by the redelivery.
    index = store.get(INDEX_KEY) or ""
    known = [m for m in index.split(",") if m]
    if message_id not in known:
        store.put(INDEX_KEY, ",".join([*known, message_id]))
    store.put(key, str(amount_cents))


def read_balance(store: DurableStore) -> int:
    index = store.get(INDEX_KEY) or ""
    total = 0
    for message_id in (m for m in index.split(",") if m):
        raw = store.get(f"{PREFIX}{message_id}")
        if raw is not None:
            total += int(raw)
    return total
