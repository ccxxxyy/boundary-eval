"""The simulated world that solution code runs against.

Everything here is deterministic. There is no wall clock, no real network and
no real filesystem, so a trace that fails once fails identically forever and
the failing trace can be replayed and printed as a counterexample.

State is split into what survives a crash and what does not:

  * `StoreState`   - durable storage, survives (it is "on disk")
  * `GatewayState` - the remote payment service, survives (it is someone
                     else's server)
  * `World`        - per-attempt scratch state, does *not* survive; a new
                     `World` is built for every attempt, which is what makes
                     in-memory bookkeeping in solution code unsafe
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import GatewayTimeout, SimulatedCrash

MUTATING_OPS = frozenset({"store.put", "store.compare_and_set", "store.delete", "gateway.charge"})


@dataclass
class Charge:
    charge_id: str
    idempotency_key: str
    amount_cents: int


@dataclass
class StoreState:
    data: dict[str, str] = field(default_factory=dict)


@dataclass
class GatewayState:
    charges: dict[str, Charge] = field(default_factory=dict)  # keyed by idempotency key
    issued: int = 0

    def charge_list(self) -> list[Charge]:
        return sorted(self.charges.values(), key=lambda c: c.charge_id)


@dataclass
class Event:
    op_index: int
    kind: str
    detail: str
    outcome: str = "ok"

    def render(self) -> str:
        suffix = "" if self.outcome == "ok" else f"  -> {self.outcome}"
        return f"    #{self.op_index:<2} {self.kind:<24} {self.detail}{suffix}"


class _OpBudgetExceeded(SimulatedCrash):
    """Raised when solution code performs absurdly many operations (likely a
    runaway loop). Reported separately from a real invariant violation."""


class World:
    """One attempt's view of the world.

    `fault` controls what goes wrong during this attempt and is supplied by the
    injector, never by solution code.
    """

    def __init__(
        self,
        store_state: StoreState,
        gateway_state: GatewayState,
        fault: "AttemptFault",
        attempt_index: int,
        op_budget: int = 64,
    ) -> None:
        self._store_state = store_state
        self._gateway_state = gateway_state
        self._fault = fault
        self._attempt_index = attempt_index
        self._op_budget = op_budget

        self.op_index = 0
        self.charge_calls = 0
        self.id_calls = 0
        self.events: list[Event] = []
        self.ack_lost = False
        self.crash_raised = False

        self.store = DurableStore(self)
        self.gateway = PaymentGateway(self)

    # -- internals used by the API objects -------------------------------

    def _begin_op(self, kind: str, detail: str) -> Event:
        if self.op_index >= self._op_budget:
            raise _OpBudgetExceeded(f"op budget of {self._op_budget} exhausted")
        event = Event(op_index=self.op_index, kind=kind, detail=detail)
        self.events.append(event)
        if self._fault.crash_before_op == self.op_index and kind in MUTATING_OPS:
            event.outcome = "CRASH (operation never applied)"
            self.op_index += 1
            self.crash_raised = True
            raise SimulatedCrash(f"crash before op #{event.op_index} ({kind})")
        self.op_index += 1
        return event

    def new_id(self) -> str:
        """A fresh identifier, as `uuid4()` would be: never repeated, and not
        reproducible after a restart."""
        self.id_calls += 1
        return f"id-a{self._attempt_index}-{self.id_calls}"


class DurableStore:
    """A durable key-value store.

    Each operation is atomic and, once it returns, durable: it survives a
    process crash. There are no multi-key transactions.
    """

    def __init__(self, world: World) -> None:
        self._world = world

    def get(self, key: str) -> str | None:
        data = self._world._store_state.data
        event = self._world._begin_op("store.get", f"key={key!r}")
        value = data.get(key)
        event.outcome = f"ok ({value!r})"
        return value

    def put(self, key: str, value: str) -> None:
        self._world._begin_op("store.put", f"key={key!r} value={value!r}")
        self._world._store_state.data[key] = value

    def compare_and_set(self, key: str, expected: str | None, new: str) -> bool:
        """Set `key` to `new` only if its current value equals `expected`
        (use `None` for "key must be absent"). Returns whether it was set."""
        event = self._world._begin_op(
            "store.compare_and_set", f"key={key!r} expected={expected!r} new={new!r}"
        )
        data = self._world._store_state.data
        if data.get(key) != expected:
            event.outcome = "ok (False)"
            return False
        data[key] = new
        event.outcome = "ok (True)"
        return True

    def delete(self, key: str) -> None:
        self._world._begin_op("store.delete", f"key={key!r}")
        self._world._store_state.data.pop(key, None)


class PaymentGateway:
    """A third-party payment service reached over the network.

    It deduplicates on `idempotency_key`: two `charge` calls with the same key
    create at most one charge. Calls may raise `GatewayTimeout`, in which case
    the outcome is unknown - the charge may or may not have been created.
    """

    def __init__(self, world: World) -> None:
        self._world = world

    def charge(self, idempotency_key: str, amount_cents: int) -> str:
        """Charge the customer and return the gateway's charge id."""
        world = self._world
        call_index = world.charge_calls
        world.charge_calls += 1
        event = world._begin_op(
            "gateway.charge", f"key={idempotency_key!r} amount={amount_cents}"
        )
        timeout = world._fault.timeout_for(call_index)

        if timeout == "lost":
            event.outcome = "TIMEOUT (charge not created)"
            raise GatewayTimeout("no response from gateway")

        state = world._gateway_state
        existing = state.charges.get(idempotency_key)
        if existing is None:
            state.issued += 1
            existing = Charge(
                charge_id=f"ch_{state.issued}",
                idempotency_key=idempotency_key,
                amount_cents=amount_cents,
            )
            state.charges[idempotency_key] = existing

        if timeout == "applied":
            event.outcome = f"TIMEOUT (but charge {existing.charge_id} WAS created)"
            raise GatewayTimeout("no response from gateway")

        event.outcome = f"ok ({existing.charge_id})"
        return existing.charge_id

    def lookup(self, idempotency_key: str) -> str | None:
        """Return the charge id previously created with this idempotency key,
        or `None` if there is no such charge."""
        world = self._world
        event = world._begin_op("gateway.lookup", f"key={idempotency_key!r}")
        charge = world._gateway_state.charges.get(idempotency_key)
        event.outcome = f"ok ({charge.charge_id if charge else None!r})"
        return charge.charge_id if charge else None
