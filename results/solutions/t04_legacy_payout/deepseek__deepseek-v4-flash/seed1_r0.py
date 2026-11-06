def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id: Callable[[], str],
) -> str:
    """Pay out `amount_cents`. Return "completed" or "needs_review"."""
    state_key = f"payout:{payout_id}:state"

    # 1. Read current state
    state = store.get(state_key)

    # Already in a final state – just return it
    if state == "completed" or state == "needs_review":
        return state

    # A previous attempt started but never finished – we cannot know
    # whether the transfer went through, so we must not try again.
    if state == "in_progress":
        store.put(state_key, "needs_review")
        return "needs_review"

    # No state yet – we are the first to handle this payout.
    # Atomically claim the right to call transfer.
    claimed = store.compare_and_set(state_key, None, "in_progress")
    if not claimed:
        # Another call claimed it (should not happen with non‑overlapping
        # calls, but be safe).  Re‑read and act on the new state.
        state = store.get(state_key)
        if state == "in_progress":
            store.put(state_key, "needs_review")
            return "needs_review"
        # Must be "completed" or "needs_review" now
        return state  # type: ignore[return-value]  # guaranteed by logic

    # We are now responsible for the transfer.
    try:
        legacy.transfer(amount_cents)
    except TransferTimeout:
        # The outcome is unknown – record and report.
        store.put(state_key, "needs_review")
        return "needs_review"

    # Transfer succeeded.
    store.put(state_key, "completed")
    return "completed"
