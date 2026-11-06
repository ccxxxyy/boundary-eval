from __future__ import annotations

from typing import Callable, Protocol


class DurableStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...
    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class LegacyTransferAPI(Protocol):
    def transfer(self, amount_cents: int) -> str: ...


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents` at most once.

    Return "completed" if the money has moved exactly once and that fact is
    durably recorded. Return "needs_review" if the outcome is unknown or
    cannot be completed safely, so a person can reconcile it.
    """
    state_key = f"payout:{payout_id}:state"

    # Atomically claim the payout by transitioning the state from absent (None)
    # directly to "needs_review". Because the state key is never deleted or
    # reset to None, this compare_and_set can succeed at most once across all
    # deliveries, crashes, and concurrent worker takeovers.
    if store.compare_and_set(state_key, None, "needs_review"):
        try:
            legacy.transfer(amount_cents)
        except Exception:
            return "needs_review"

        store.compare_and_set(state_key, "needs_review", "completed")
        return "completed"

    if store.get(state_key) == "completed":
        return "completed"
    return "needs_review"
