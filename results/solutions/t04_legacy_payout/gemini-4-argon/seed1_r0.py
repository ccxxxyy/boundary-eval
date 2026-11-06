from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class DurableStore(Protocol):
    """A durable key-value store.

    Each operation is atomic, and once it returns, its effect is durable: it
    survives a process crash.
    """

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class LegacyTransferAPI(Protocol):
    def transfer(self, amount_cents: int) -> str: ...


class TransferTimeout(Exception):
    """The legacy system did not answer."""


_STATE_COMPLETED = "completed"
_STATE_NEEDS_REVIEW = "needs_review"
_STATE_IN_FLIGHT = "in_flight"


def _is_transfer_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TransferTimeout):
        return True
    return any(cls.__name__ == "TransferTimeout" for cls in type(exc).__mro__)


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents`. Return "completed" or "needs_review"."""
    state_key = f"payout:{payout_id}:state"
    current_state = store.get(state_key)

    if current_state == _STATE_COMPLETED:
        return _STATE_COMPLETED

    if current_state == _STATE_NEEDS_REVIEW:
        return _STATE_NEEDS_REVIEW

    if current_state is not None:
        # A previous execution recorded intent to transfer and then crashed
        # either before or after the transfer took effect. We cannot safely
        # retry without risking a duplicate payout.
        store.put(state_key, _STATE_NEEDS_REVIEW)
        return _STATE_NEEDS_REVIEW

    # Record durable intent before invoking the non-idempotent legacy API.
    if not store.compare_and_set(state_key, None, _STATE_IN_FLIGHT):
        store.put(state_key, _STATE_NEEDS_REVIEW)
        return _STATE_NEEDS_REVIEW

    try:
        legacy.transfer(amount_cents)
    except Exception as exc:
        if _is_transfer_timeout(exc):
            store.put(state_key, _STATE_NEEDS_REVIEW)
            return _STATE_NEEDS_REVIEW
        raise

    store.put(state_key, _STATE_COMPLETED)
    return _STATE_COMPLETED
