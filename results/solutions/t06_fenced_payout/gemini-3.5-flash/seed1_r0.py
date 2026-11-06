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

    while True:
        current = store.get(state_key)

        if current == "completed":
            return "completed"

        if current == "needs_review":
            return "needs_review"

        if current is None:
            token = f"in_progress:{new_id()}"
            if store.compare_and_set(state_key, None, token):
                try:
                    legacy.transfer(amount_cents)
                except Exception:
                    store.put(state_key, "needs_review")
                    return "needs_review"

                store.put(state_key, "completed")
                return "completed"
            continue

        store.compare_and_set(state_key, current, "needs_review")
        final_state = store.get(state_key)
        if final_state == "completed":
            return "completed"
        if final_state != "needs_review":
            store.put(state_key, "needs_review")
        return "needs_review"
