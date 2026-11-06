"""BROKEN. Expected violation: "at most one".

Claims properly, then retries the claim it finds on recovery. This is the
instinct the task is about: a failed remote call gets retried. Against a system
that cannot be queried and does not deduplicate, the retry is the bug, and the
supplier is paid twice.
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

    store.put(state_key, "attempting")
    for _ in range(4):
        try:
            legacy.transfer(amount_cents=amount_cents)
            store.put(state_key, "completed")
            return "completed"
        except TransferTimeout:
            continue

    store.put(state_key, "needs_review")
    return "needs_review"
