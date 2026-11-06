from __future__ import annotations

from typing import Callable, Protocol


class TransferTimeout(Exception):
    """The legacy system did not answer."""


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
    """Pay out `amount_cents`. Return "completed" or "needs_review"."""
    state_key = f"payout:{payout_id}:state"
    intent_key = f"payout:{payout_id}:intent"

    state = store.get(state_key)
    if state in ("completed", "needs_review"):
        return state

    if store.get(intent_key) is not None or not store.compare_and_set(
        intent_key, None, new_id()
    ):
        store.put(state_key, "needs_review")
        return "needs_review"

    try:
        legacy.transfer(amount_cents)
    except Exception as exc:
        if isinstance(exc, TransferTimeout) or exc.__class__.__name__ == "TransferTimeout":
            store.put(state_key, "needs_review")
            return "needs_review"
        raise

    store.put(state_key, "completed")
    return "completed"
