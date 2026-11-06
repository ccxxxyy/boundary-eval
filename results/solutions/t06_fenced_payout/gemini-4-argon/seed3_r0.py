from __future__ import annotations

from typing import Callable, Protocol


class DurableStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...
    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class LegacyTransferAPI(Protocol):
    def transfer(self, amount_cents: int) -> str: ...


def _is_transfer_timeout(exc: BaseException) -> bool:
    return any("Timeout" in cls.__name__ for cls in type(exc).__mro__)


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
    claim = f"in_progress:{new_id()}"

    # Atomically claim the payout if no worker has started it yet.
    # Because `state_key` is never deleted or reset to None, this CAS can
    # succeed at most once across all retries, crashes, and takeovers.
    if store.compare_and_set(state_key, None, claim):
        try:
            legacy.transfer(amount_cents)
        except Exception as exc:
            if not _is_transfer_timeout(exc):
                raise
            store.compare_and_set(state_key, claim, "needs_review")
            return "needs_review"

        if store.compare_and_set(state_key, claim, "completed"):
            return "completed"
        return "needs_review"

    current = store.get(state_key)
    if current == "completed":
        return "completed"
    if current == "needs_review":
        return "needs_review"

    # Another worker claimed the payout and either crashed or is still running.
    # Fence off its claim so the final state is durably marked for review.
    if current is not None and store.compare_and_set(state_key, current, "needs_review"):
        return "needs_review"

    final = store.get(state_key)
    if final == "completed":
        return "completed"
    return "needs_review"
