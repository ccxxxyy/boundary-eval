"""BROKEN. Expected violation: "nobody will ever find this payout".

The reasoning is entirely right - claim first, escalate rather than retry - and
the escalation is only ever returned to the caller, never written down. The
state key is left on "attempting", so the payout sits in limbo instead of in
somebody's reconciliation queue.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    state_key = f"payout:{payout_id}:state"
    state = store.get(state_key)
    if state == "completed":
        return "completed"
    if state == "attempting":
        return "needs_review"

    store.put(state_key, "attempting")
    try:
        legacy.transfer(amount_cents=amount_cents)
    except TransferTimeout:
        return "needs_review"

    store.put(state_key, "completed")
    return "completed"
