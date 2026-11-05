"""A third-party payment provider reached over the network.

Deduplicates on a caller-supplied idempotency key, and can time out after
having already accepted the charge - the ambiguous outcome that makes naive
retry logic expensive.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import GatewayTimeout
from ..world import World


@dataclass
class Charge:
    charge_id: str
    idempotency_key: str
    amount_cents: int


@dataclass
class GatewayState:
    charges: dict[str, Charge] = field(default_factory=dict)  # by idempotency key
    issued: int = 0

    def charge_list(self) -> list[Charge]:
        return sorted(self.charges.values(), key=lambda c: c.charge_id)

    def describe(self) -> str:
        charges = self.charge_list()
        if not charges:
            return "charges on the gateway: none"
        rendered = ", ".join(
            f"{c.charge_id}({c.amount_cents}, key={c.idempotency_key})" for c in charges
        )
        return f"charges on the gateway: {rendered}"


class PaymentGateway:
    def __init__(self, world: World, state: GatewayState) -> None:
        self._world = world
        self._state = state

    def charge(self, idempotency_key: str, amount_cents: int) -> str:
        world = self._world
        call_index = world.next_remote_call()
        event = world.begin_op(
            "gateway.charge", f"key={idempotency_key!r} amount={amount_cents}", mutating=True
        )
        timeout = world.fault.timeout_for(call_index)

        if timeout == "lost":
            event.outcome = "TIMEOUT (charge not created)"
            raise GatewayTimeout("no response from gateway")

        charge = self._state.charges.get(idempotency_key)
        if charge is None:
            self._state.issued += 1
            charge = Charge(
                charge_id=f"ch_{self._state.issued}",
                idempotency_key=idempotency_key,
                amount_cents=amount_cents,
            )
            self._state.charges[idempotency_key] = charge

        if timeout == "applied":
            event.outcome = f"TIMEOUT (but charge {charge.charge_id} WAS created)"
            raise GatewayTimeout("no response from gateway")

        event.outcome = f"ok ({charge.charge_id})"
        return charge.charge_id

    def lookup(self, idempotency_key: str) -> str | None:
        world = self._world
        event = world.begin_op("gateway.lookup", f"key={idempotency_key!r}", mutating=False)
        charge = self._state.charges.get(idempotency_key)
        found = charge.charge_id if charge else None
        event.outcome = f"ok ({found!r})"
        return found
