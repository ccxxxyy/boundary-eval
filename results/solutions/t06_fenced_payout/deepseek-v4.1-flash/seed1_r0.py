from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id,
) -> str:
    """Pay out `amount_cents` at most once.

    The store value for this payout is a small state machine:

        claimed:<token>   a worker has claimed the right to prepare
        prepared:<token>  that worker has the unique right to call transfer
        completed         the bank transfer succeeded and is recorded
        needs_review      the outcome is unknown or cannot be completed safely

    The CAS from claimed -> prepared is the fence.  Only the worker that
    wins that CAS may call `legacy.transfer`.  A worker seeing `prepared`
    never calls transfer: it may be looking at a live worker that is still
    about to call the bank, so trying to take over would risk a double pay.
    """
    key = f"payout:{payout_id}:state"

    while True:
        token = new_id()
        claimed = f"claimed:{token}"
        prepared = f"prepared:{token}"

        # Acquire a claim, or safely take over a claim that has not yet
        # become prepared.  The prepared state is never taken over.
        while True:
            current = store.get(key)

            if current == "completed":
                return "completed"
            if current == "needs_review":
                return "needs_review"

            if current is None:
                if store.compare_and_set(key, None, claimed):
                    break
                continue

            if current.startswith("claimed:"):
                # Taking over a claimed-but-not-prepared state is safe:
                # the previous claimant's later claimed -> prepared CAS will
                # fail, so it will not be authorized to transfer.
                if store.compare_and_set(key, current, claimed):
                    break
                continue

            if current.startswith("prepared:"):
                # Some worker already has the one authorization to transfer.
                # We must not call transfer.  Record that this payout needs
                # human reconciliation if it is not already completed.
                store.compare_and_set(key, current, "needs_review")
                final = store.get(key)
                if final == "completed":
                    return "completed"
                return "needs_review"

            # Unknown/corrupt state: never move money from here.
            store.compare_and_set(key, current, "needs_review")
            final = store.get(key)
            if final == "completed":
                return "completed"
            return "needs_review"

        # This CAS is the commitment point.  If it succeeds, we are the only
        # worker allowed to call the legacy transfer.
        if not store.compare_and_set(key, claimed, prepared):
            # Lost the claim before becoming authorized.  No bank call was
            # made by us; re-enter and inspect the new state.
            continue

        try:
            legacy.transfer(amount_cents)
        except TransferTimeout:
            # The transfer may or may not have happened.  Never retry.
            store.compare_and_set(key, prepared, "needs_review")
            return "needs_review"
        except Exception:
            # Defensive: any non-normal outcome from the bank call leaves the
            # result unknown, so escalate rather than retry.
            store.compare_and_set(key, prepared, "needs_review")
            return "needs_review"

        # The transfer returned normally, so it moved the money exactly once.
        if store.compare_and_set(key, prepared, "completed"):
            return "completed"

        # A takeover may have observed `prepared` and changed it to
        # `needs_review` while our transfer was in flight.  We now know the
        # transfer succeeded, and only our prepared token was ever authorized
        # to call the bank, so promoting to completed is safe.
        if store.compare_and_set(key, "needs_review", "completed"):
            return "completed"

        final = store.get(key)
        if final == "completed":
            return "completed"

        return "needs_review"
