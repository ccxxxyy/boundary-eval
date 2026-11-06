from __future__ import annotations
from typing import Callable, Protocol


class TransferTimeout(Exception):
    """The legacy system did not answer."""


class DurableStore(Protocol):
    """A durable key-value store interface."""

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class LegacyTransferAPI(Protocol):
    """The legacy system's transfer API interface."""

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
    lock_key = f"payout:{payout_id}:lock"

    try:
        # 1. Check if a terminal state has already been reached and recorded.
        # This handles redeliveries after a successful or failed-but-handled attempt.
        existing_state = store.get(state_key)
        if existing_state in ("completed", "needs_review"):
            return existing_state

        # 2. Check if an attempt was already initiated in a previous run.
        # Because the legacy API is not idempotent and has no lookup, if a lock exists
        # but no terminal state is recorded, we are in an ambiguous state (e.g., the
        # process crashed during or immediately after the legacy transfer call).
        # To prevent double-paying, we must escalate to manual review.
        if store.get(lock_key) is not None:
            store.put(state_key, "needs_review")
            return "needs_review"

        # 3. Acquire the lock to indicate we are about to attempt the transfer.
        # The lock acts as our idempotency guard. Once set, no further attempts
        # will be made by this function for this payout_id.
        if not store.compare_and_set(lock_key, None, new_id()):
            # Safety fallback: if CAS fails, another process (or a previous run)
            # set the lock. Re-check state, otherwise treat as ambiguous.
            existing_state = store.get(state_key)
            if existing_state in ("completed", "needs_review"):
                return existing_state
            store.put(state_key, "needs_review")
            return "needs_review"

        # 4. Execute the transfer.
        try:
            legacy.transfer(amount_cents)
        except Exception:
            # This includes TransferTimeout. Since the outcome is unknown,
            # we must transition to needs_review.
            store.put(state_key, "needs_review")
            return "needs_review"

        # 5. Success! Record the completion.
        store.put(state_key, "completed")
        return "completed"

    except Exception:
        # Final safety net to ensure no exceptions escape the function.
        # We attempt to record the state as "needs_review" before returning.
        try:
            store.put(state_key, "needs_review")
        except Exception:
            # If the store is also failing, we cannot record state, but we
            # still return the correct status to the caller.
            pass
        return "needs_review"
