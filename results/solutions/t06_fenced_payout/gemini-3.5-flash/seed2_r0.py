from __future__ import annotations


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

    try:
        # Check current recorded state.
        state = store.get(state_key)

        if state == "completed":
            return "completed"
        if state == "needs_review":
            return "needs_review"

        if state is None:
            my_token = f"token:{new_id()}"
            if store.compare_and_set(state_key, None, my_token):
                # We exclusively claimed the attempt to transfer money.
                # Double-check we still hold the token right before calling legacy.transfer.
                if store.get(state_key) != my_token:
                    final_state = store.get(state_key)
                    if final_state == "completed":
                        return "completed"
                    return "needs_review"

                try:
                    legacy.transfer(amount_cents)
                except Exception:
                    # Transfer timed out or failed. Outcome is unknown or unverified.
                    store.compare_and_set(state_key, my_token, "needs_review")
                    if store.get(state_key) == "completed":
                        return "completed"
                    return "needs_review"

                # Money transferred successfully. Record completed state.
                if store.compare_and_set(state_key, my_token, "completed"):
                    return "completed"

                final_state = store.get(state_key)
                if final_state == "completed":
                    return "completed"
                return "needs_review"

        # If state was not None (or CAS failed because another worker claimed it first):
        state = store.get(state_key)
        if state == "completed":
            return "completed"
        if state == "needs_review":
            return "needs_review"

        # State is a token from another worker attempt (crashed or concurrent).
        # Mark as needs_review if it has not been finalized.
        if state is not None:
            store.compare_and_set(state_key, state, "needs_review")

        final_state = store.get(state_key)
        if final_state == "completed":
            return "completed"
        return "needs_review"

    except Exception:
        # Fallback guard so no exception escapes the handler.
        try:
            curr = store.get(state_key)
            if curr == "completed":
                return "completed"
            if curr is None:
                store.put(state_key, "needs_review")
            elif curr != "completed":
                store.compare_and_set(state_key, curr, "needs_review")
        except Exception:
            pass
        return "needs_review"
