from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout


_COMPLETED = "completed"
_NEEDS_REVIEW = "needs_review"
_CLAIM_PREFIX = "in_progress:"


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id,
) -> str:
    """Pay out ``amount_cents`` at most once.

    The first worker to install the durable claim is the only worker ever
    permitted to call the bank. A claim whose outcome is not already durable
    is escalated rather than retried: its owner might merely be slow, or might
    have crashed after the bank applied the transfer.
    """
    state_key = f"payout:{payout_id}:state"

    while True:
        state = store.get(state_key)

        if state == _COMPLETED:
            return _COMPLETED
        if state == _NEEDS_REVIEW:
            return _NEEDS_REVIEW

        if state is not None:
            # Another worker owns the sole possible transfer attempt. Never
            # retry it. CAS avoids overwriting a completion recorded after our
            # read; if that race occurs, re-read and return the final state.
            if store.compare_and_set(state_key, state, _NEEDS_REVIEW):
                return _NEEDS_REVIEW
            continue

        claim = _CLAIM_PREFIX + new_id()
        if store.compare_and_set(state_key, None, claim):
            break
        # A concurrent worker installed a claim or final state first.

    try:
        legacy.transfer(amount_cents)
    except TransferTimeout:
        # The transfer may have been applied, so no worker may try again.
        # A takeover worker may already have changed the claim to needs_review.
        store.compare_and_set(state_key, claim, _NEEDS_REVIEW)
        return _NEEDS_REVIEW

    # Only this claim owner can have received a successful response. It may
    # therefore record completion even if a takeover worker escalated the
    # claim meanwhile. Other workers only replace claims via CAS, so none can
    # subsequently overwrite this completion with needs_review.
    store.put(state_key, _COMPLETED)
    return _COMPLETED
