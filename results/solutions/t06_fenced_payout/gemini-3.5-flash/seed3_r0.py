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
    my_token = new_id()

    while True:
        current = store.get(state_key)

        if current == "completed":
            return "completed"
        if current == "needs_review":
            return "needs_review"

        if current is None or current.startswith("claimed:"):
            # Attempt to claim or take over the claim for this payout
            if store.compare_and_set(
                state_key, current, f"claimed:{my_token}"
            ):
                # Transition from claimed to transferring. Only the worker that
                # succeeds in this step is authorized to call legacy.transfer.
                if store.compare_and_set(
                    state_key,
                    f"claimed:{my_token}",
                    f"transferring:{my_token}",
                ):
                    try:
                        legacy.transfer(amount_cents)
                    except Exception:
                        store.put(state_key, "needs_review")
                        return "needs_review"

                    store.put(state_key, "completed")
                    return "completed"
                else:
                    # Another worker took over our claimed state before we reached transferring
                    continue
            else:
                # CAS failed because state changed concurrently
                continue

        if current.startswith("transferring:"):
            # Another worker reached the transfer stage. It may have already initiated
            # or completed the transfer, so we must not attempt transfer. Mark as needs_review.
            store.compare_and_set(state_key, current, "needs_review")
            continue

        store.put(state_key, "needs_review")
        return "needs_review"
