"""BROKEN. Expected violation: "two answers".

Crash-safety is handled properly here: the whole transfer is one journal
entry, exactly like the reference, so no crash can split the debit from the
credit.

What it does not do is settle the decision. The entry records that the
transfer was *seen*, and the accept-or-refuse answer is worked out afresh on
every delivery from whatever the balances are at that moment. A transfer
refused for insufficient funds therefore becomes accepted the moment some
other transfer tops the account up, and the same request has two different
answers.
"""

from __future__ import annotations

from faultline.api import DurableStore

APPLIED = "applied"
REJECTED = "rejected"


def _entry_key(index: int) -> str:
    return f"j{index}"


def _replay(store: DurableStore) -> tuple[dict[str, int], set[str], int]:
    moves: dict[str, int] = {}
    seen: set[str] = set()
    index = 0
    while True:
        raw = store.get(_entry_key(index))
        if raw is None:
            return moves, seen, index
        transfer_id, pair, amount = raw.split(":")
        seen.add(transfer_id)
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
    while True:
        moves, seen, end = _replay(store)
        available = _opening(store, source) + moves.get(source, 0)
        if transfer_id in seen:
            return APPLIED
        if available < amount_cents:
            return REJECTED
        if store.compare_and_set(
            _entry_key(end), None, f"{transfer_id}:{source}{target}:{amount_cents}"
        ):
            return APPLIED


def read_balance(account: str, store: DurableStore) -> int:
    moves, _, _ = _replay(store)
    return _opening(store, account) + moves.get(account, 0)
