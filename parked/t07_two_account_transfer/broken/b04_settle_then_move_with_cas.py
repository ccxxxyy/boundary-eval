"""BROKEN. Expected violation: "was lost".

A more sophisticated attempt than the plain dual write. It claims the
transfer with a conditional write, so two deliveries cannot both decide it,
and then applies the debit and the credit with compare-and-set so neither can
be applied on top of a stale read.

Every individual write is safe. What is missing is a way for a later delivery
to finish an interrupted one: once `tx:<id>` says `applied`, every delivery
returns early, including the delivery that could have completed the credit
that never happened.
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
        store.compare_and_set(decision_key, None, REJECTED)
        return REJECTED

    if not store.compare_and_set(decision_key, None, APPLIED):
        return store.get(decision_key) or APPLIED

    while True:
        current = store.get(f"acct:{source}")
        if store.compare_and_set(
            f"acct:{source}", current, str(int(current or "0") - amount_cents)
        ):
            break
    while True:
        current = store.get(f"acct:{target}")
        if store.compare_and_set(
            f"acct:{target}", current, str(int(current or "0") + amount_cents)
        ):
            break
    return APPLIED


def read_balance(account: str, store: DurableStore) -> int:
    return _balance(store, account)
