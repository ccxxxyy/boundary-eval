"""At-most-once payout coordination for a non-idempotent legacy API."""

from typing import Callable

from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout


_COMPLETED = "completed"
_NEEDS_REVIEW = "needs_review"
_PENDING_PREFIX = "pending:"


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out ``amount_cents`` at most once.

    A durable pending record is installed before calling the legacy API. If a
    crash or timeout leaves that record behind, its transfer outcome is
    unknowable, so the payout is sent to review rather than attempted again.
    """
    state_key = f"payout:{payout_id}:state"
    state = store.get(state_key)

    if state == _COMPLETED:
        return _COMPLETED
    if state == _NEEDS_REVIEW:
        return _NEEDS_REVIEW

    # Any other existing value is an interrupted attempt (or otherwise
    # unrecognized). It must never be used as justification for another call.
    if state is not None:
        store.put(state_key, _NEEDS_REVIEW)
        return _NEEDS_REVIEW

    pending = _PENDING_PREFIX + new_id()
    if not store.compare_and_set(state_key, None, pending):
        # Calls do not overlap, but handle a lost claim conservatively.
        state = store.get(state_key)
        if state == _COMPLETED:
            return _COMPLETED
        if state != _NEEDS_REVIEW:
            store.put(state_key, _NEEDS_REVIEW)
        return _NEEDS_REVIEW

    try:
        legacy.transfer(amount_cents)
    except TransferTimeout:
        # The request may or may not have been applied. Never retry it.
        store.put(state_key, _NEEDS_REVIEW)
        return _NEEDS_REVIEW

    # A normal return from transfer is the only point at which completion can
    # be promised. If a crash precedes this write, recovery chooses review.
    store.put(state_key, _COMPLETED)
    return _COMPLETED
