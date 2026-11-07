"""Reference solution: an append-only journal, one atomic write per transfer.

The two halves of a transfer are only two facts if the design makes them two.
Writing the decision as a single journal entry makes them one: the entry says
what was accepted, and both balances are derived from it. There is no window
in which the debit is durable and the credit is not, because there is no
separate debit.

The decision is settled at the moment the entry is written and is never
recomputed. That is what keeps a refused transfer refused when it comes round
again and the source account has since been topped up - the journal is
replayed to find the answer that was already given, not to work out a fresh
one.

Finding the end of the journal also establishes whether this transfer is
already in it, so one compare-and-set is the whole write path. A crash before
it leaves no trace and the redelivery does the same work again; a crash after
it is indistinguishable from success.

Durable state stays bounded: one entry per distinct transfer, each holding
only that transfer.
"""

from __future__ import annotations

from faultline.api import DurableStore

APPLIED = "applied"
REJECTED = "rejected"


def _entry_key(index: int) -> str:
    return f"j{index}"


def _encode(transfer_id: str, source: str, target: str, amount: int, decision: str) -> str:
    return f"{transfer_id}:{source}{target}:{amount}:{decision[0]}"


def _decode(raw: str) -> tuple[str, str, str, int, str]:
    transfer_id, pair, amount, flag = raw.split(":")
    decision = APPLIED if flag == "a" else REJECTED
    return transfer_id, pair[0], pair[1], int(amount), decision


def _replay(store: DurableStore) -> tuple[dict[str, int], dict[str, str], int]:
    """Balances, settled decisions, and where the journal ends."""
    balances: dict[str, int] = {}
    decisions: dict[str, str] = {}
    index = 0
    while True:
        raw = store.get(_entry_key(index))
        if raw is None:
            return balances, decisions, index
        transfer_id, source, target, amount, decision = _decode(raw)
        decisions[transfer_id] = decision
        if decision == APPLIED:
            balances[source] = balances.get(source, 0) - amount
            balances[target] = balances.get(target, 0) + amount
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
        moves, decisions, end = _replay(store)
        if transfer_id in decisions:
            return decisions[transfer_id]

        available = _opening(store, source) + moves.get(source, 0)
        decision = APPLIED if available >= amount_cents else REJECTED

        if store.compare_and_set(
            _entry_key(end),
            None,
            _encode(transfer_id, source, target, amount_cents, decision),
        ):
            return decision
        # Another delivery claimed that slot. Replay and try again; if it was
        # this very transfer, the replay above will now find the decision.


def read_balance(account: str, store: DurableStore) -> int:
    moves, _, _ = _replay(store)
    return _opening(store, account) + moves.get(account, 0)
