"""BROKEN. Expected violation: "was invented".

This one gets the hard part right. The money moves as a single journal entry,
so no crash can ever split the debit from the credit, and the two accounts
always add up correctly with respect to the journal.

The mistake is in the deduplication. "Have I handled this transfer already?"
is answered from a separate marker key, written *after* the entry. A crash in
between leaves a journal entry with no marker, so the redelivery cannot tell
the transfer was already applied and appends a second entry for it. The money
moves twice and the pair no longer adds up to what ever existed.

This is the dual-write problem one level up: the data was made atomic and the
record of having written it was not.
"""

from __future__ import annotations

from faultline.api import DurableStore

APPLIED = "applied"
REJECTED = "rejected"


def _entry_key(index: int) -> str:
    return f"j{index}"


def _replay(store: DurableStore) -> tuple[dict[str, int], int]:
    moves: dict[str, int] = {}
    index = 0
    while True:
        raw = store.get(_entry_key(index))
        if raw is None:
            return moves, index
        _, pair, amount = raw.split(":")
        moves[pair[0]] = moves.get(pair[0], 0) - int(amount)
        moves[pair[1]] = moves.get(pair[1], 0) + int(amount)
        index += 1


def _opening(store: DurableStore, account: str) -> int:
    return int(store.get(f"acct:{account}") or "0")


def handle_transfer(
    transfer_id: str,
    source: str,
    target: str,
    amount_cents: int,
    store: DurableStore,
) -> str:
    marker_key = f"tx:{transfer_id}"
    settled = store.get(marker_key)
    if settled is not None:
        return settled

    moves, end = _replay(store)
    if _opening(store, source) + moves.get(source, 0) < amount_cents:
        store.put(marker_key, REJECTED)
        return REJECTED

    store.compare_and_set(
        _entry_key(end), None, f"{transfer_id}:{source}{target}:{amount_cents}"
    )
    store.put(marker_key, APPLIED)
    return APPLIED


def read_balance(account: str, store: DurableStore) -> int:
    moves, _ = _replay(store)
    return _opening(store, account) + moves.get(account, 0)
