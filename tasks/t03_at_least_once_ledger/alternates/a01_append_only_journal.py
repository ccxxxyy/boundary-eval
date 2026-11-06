"""Known-correct, and a completely different design: an append-only journal.

There is no balance key and no dedup marker. Each distinct message becomes one
numbered entry holding its own amount, and the balance is derived by replaying
the journal. Finding the end of the journal also finds out whether this message
is already in it, so one single atomic write per message is all it takes -
there is never a second fact to keep in step with the first.

Included to prove the grader judges the invariant and not the shape: this
stores no balance, keeps no set of applied ids, and uses a different key
layout from the reference. Durable state stays bounded because each entry
holds exactly one message.
"""

from __future__ import annotations

from faultline.api import DurableStore


def _entry_key(index: int) -> str:
    return f"e{index}"


def handle_message(message_id: str, amount_cents: int, store: DurableStore) -> None:
    index = 0
    while True:
        entry = store.get(_entry_key(index))
        if entry is None:
            break
        if entry.split(":", 1)[0] == message_id:
            return
        index += 1
    # compare_and_set rather than put so that a redelivery which raced ahead
    # cannot be overwritten; a crash before this leaves no trace at all.
    store.compare_and_set(_entry_key(index), None, f"{message_id}:{amount_cents}")


def read_balance(store: DurableStore) -> int:
    total = 0
    index = 0
    while True:
        entry = store.get(_entry_key(index))
        if entry is None:
            return total
        total += int(entry.split(":", 1)[1])
        index += 1
