from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id,
) -> str:
    """Pay out `amount_cents` at most once.

    Return "completed" if the money has moved exactly once and that fact is
    durably recorded. Return "needs_review" if the outcome is unknown or
    cannot be completed safely, so a person can reconcile it.
    """
    state_key = f"payout:{payout_id}:state"

    # Fast path for already finished payouts
    state = store.get(state_key)
    if state == "completed":
        return "completed"
    if state == "needs_review":
        return "needs_review"

    # Atomically claim the right to initiate the transfer.
    # Because state_key is never reset to None, this CAS can succeed at most once.
    if store.compare_and_set(state_key, None, "initiated"):
        try:
            legacy.transfer(amount_cents)
        except Exception:
            store.put(state_key, "needs_review")
            return "needs_review"
        else:
            store.put(state_key, "completed")
            return "completed"

    # If CAS failed, another worker claimed or completed the payout.
    state = store.get(state_key)
    if state == "completed":
        return "completed"
    if state == "needs_review":
        return "needs_review"

    # The payout is in an unconfirmed "initiated" state from another (or crashed) worker.
    # Safely transition state to "needs_review" so a terminal state is durably recorded.
    if state is not None:
        store.compare_and_set(state_key, state, "needs_review")

    final_state = store.get(state_key)
    if final_state == "completed":
        return "completed"
    return "needs_review"
