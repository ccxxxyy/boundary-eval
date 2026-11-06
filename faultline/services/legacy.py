"""A legacy transfer API with no idempotency and no way to query it.

Real systems like this are common: an ageing bank integration, an SMS gateway,
a partner endpoint that predates anyone's interest in idempotency keys. Two
calls mean two transfers, and there is no endpoint that answers "did my last
request land?".

Exactly-once is not achievable against such a system - not by clever code, not
by any amount of retrying. The achievable goal is at-most-once plus an honest
report when the outcome is unknown, so a human can reconcile it. That judgement
is the thing the task measures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import TransferTimeout
from ..world import World


@dataclass
class Transfer:
    transfer_id: str
    amount_cents: int


@dataclass
class LegacyState:
    transfers: list[Transfer] = field(default_factory=list)

    def describe(self) -> str:
        if not self.transfers:
            return "transfers executed by the legacy system: none"
        rendered = ", ".join(f"{t.transfer_id}({t.amount_cents})" for t in self.transfers)
        return f"transfers executed by the legacy system: {rendered}"


class LegacyTransferAPI:
    def __init__(self, world: World, state: LegacyState) -> None:
        self._world = world
        self._state = state

    def transfer(self, amount_cents: int) -> str:
        """Move money. Returns the legacy system's reference for the transfer.

        There is no idempotency key and no way to look a transfer up
        afterwards. Two calls move the money twice. May raise
        `TransferTimeout`, in which case the transfer may or may not have
        happened.
        """
        world = self._world
        call_index = world.next_remote_call()
        event = world.begin_op("legacy.transfer", f"amount={amount_cents}", mutating=True)
        timeout = world.fault.timeout_for(call_index)

        if timeout == "lost":
            event.outcome = "TIMEOUT (transfer did not happen)"
            raise TransferTimeout("no response from the legacy system")

        transfer = Transfer(
            transfer_id=f"tr_{len(self._state.transfers) + 1}", amount_cents=amount_cents
        )
        self._state.transfers.append(transfer)

        if timeout == "applied":
            event.outcome = f"TIMEOUT (but transfer {transfer.transfer_id} DID happen)"
            raise TransferTimeout("no response from the legacy system")

        event.outcome = f"ok ({transfer.transfer_id})"
        return transfer.transfer_id
