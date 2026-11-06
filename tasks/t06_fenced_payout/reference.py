"""Reference solution.

Two rules, and the second is the one that matters here.

1. Claim the payout durably *before* touching the legacy system, with a
   conditional write. The claim is what makes the transfer at-most-once
   across restarts.

2. Believe the claim's answer. `compare_and_set` returning `False` means
   somebody else owns this payout - either a previous life of this process or
   a second worker the queue started because this one looked dead. Either way
   the only safe move is to stop and report whatever the owner recorded. A
   worker that took the handover and then transferred anyway pays twice, and
   no amount of retrying undoes that.

After a timeout the outcome is genuinely unknown, and the legacy system cannot
be asked, so the payout is escalated rather than retried.
"""

from __future__ import annotations

from faultline.api import DurableStore, LegacyTransferAPI, TransferTimeout

IN_PROGRESS = "in_progress"
COMPLETED = "completed"
NEEDS_REVIEW = "needs_review"


def send_payout(
    payout_id: str,
    amount_cents: int,
    store: DurableStore,
    legacy: LegacyTransferAPI,
    new_id,
) -> str:
    state_key = f"payout:{payout_id}:state"

    existing = store.get(state_key)
    if existing == COMPLETED:
        return COMPLETED
    if existing == NEEDS_REVIEW:
        return NEEDS_REVIEW
    if existing == IN_PROGRESS:
        # Somebody claimed this and never finished. Whether the money moved is
        # unknown, and the legacy system cannot be asked, so a human has to
        # reconcile it. Retrying here is exactly how a supplier gets paid
        # twice.
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    if not store.compare_and_set(state_key, None, IN_PROGRESS):
        # Lost the race. Another worker owns the payout now; report what it
        # decided and do not go near the legacy system.
        current = store.get(state_key)
        return COMPLETED if current == COMPLETED else NEEDS_REVIEW

    try:
        legacy.transfer(amount_cents)
    except TransferTimeout:
        # The transfer may or may not have happened and there is no way to
        # find out. Record that, and stop.
        store.put(state_key, NEEDS_REVIEW)
        return NEEDS_REVIEW

    store.put(state_key, COMPLETED)
    return COMPLETED
