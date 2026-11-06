"""BROKEN. Expected violation: "although nothing went wrong".

The degenerate "safe" solution: never transfer, always escalate. It satisfies
at-most-once perfectly. It is here to pin down the liveness half of the
contract - without that clause, this would pass, and the task would be
measuring nothing.
"""

from __future__ import annotations

from typing import Callable

from faultline.api import DurableStore, LegacyTransferAPI


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    store.put(f"payout:{payout_id}:state", "needs_review")
    return "needs_review"
