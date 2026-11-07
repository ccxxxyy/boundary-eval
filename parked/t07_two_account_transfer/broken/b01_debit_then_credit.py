"""BROKEN. Expected violation: "was lost".

The obvious implementation: mark the transfer settled, debit the source,
credit the target. Three writes, in the order a person would say them out
loud, and every one of them individually atomic and durable.

A crash between the debit and the credit leaves the money nowhere. The
transfer is already marked settled, so the redelivery returns early and never
finishes the job. The two accounts no longer add up to what ever existed.
"""

from __future__ import annotations

from faultline.api import DurableStore

APPLIED = "applied"
REJECTED = "rejected"


def _balance(store: DurableStore, account: str) -> int:
    return int(store.get(f"acct:{account}") or "0")


def handle_transfer(
    transfer_id: str,
    source: str,
    target: str,
    amount_cents: int,
    store: DurableStore,
) -> str:
    decision_key = f"tx:{transfer_id}"
    settled = store.get(decision_key)
    if settled is not None:
        return settled

    if _balance(store, source) < amount_cents:
        store.put(decision_key, REJECTED)
        return REJECTED

    store.put(decision_key, APPLIED)
    store.put(f"acct:{source}", str(_balance(store, source) - amount_cents))
    store.put(f"acct:{target}", str(_balance(store, target) + amount_cents))
    return APPLIED


def read_balance(account: str, store: DurableStore) -> int:
    return _balance(store, account)
