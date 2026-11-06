from __future__ import annotations

from typing import Callable, Protocol

COMPLETED = "completed"
NEEDS_REVIEW = "needs_review"


class DurableStore(Protocol):
    """A durable key-value store with atomic operations."""

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class LegacyTransferAPI(Protocol):
    def transfer(self, amount_cents: int) -> str: ...


class TransferTimeout(Exception):
    """The legacy system did not answer."""


def _is_transfer_timeout(exc: BaseException) -> bool:
    return isinstance(exc, TransferTimeout) or type(exc).__name__ == "TransferTimeout"


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents`. Return "completed" or "needs_review"."""
    state_key = f"payout:{payout_id}:state"

    state = store.get(state_key)
    if state in (COMPLETED, NEEDS_REVIEW):
        return state

    if state is not None:
        # A previous attempt recorded its intent to transfer and crashed before
        # recording a terminal state; we cannot know if the transfer landed.
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    claim = f"pending:{new_id()}"
    if not store.compare_and_set(state_key, None, claim):
        state = store.get(state_key)
        if state in (COMPLETED, NEEDS_REVIEW):
            return state
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    try:
        legacy.transfer(amount_cents)
    except BaseException as exc:
        if _is_transfer_timeout(exc):
            store.put(state_key, NEEDS_REVIEW)
            return NEEDS_REVIEW
        raise

    store.put(state_key, COMPLETED)
    return COMPLETED
