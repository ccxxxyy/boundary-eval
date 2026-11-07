"""Task 7: one invariant held across two accounts.

Every earlier task guards a single fact. This one guards a relationship: money
moves between two accounts, the pair must always add up to the opening total,
and no account may go negative. The store still has no multi-key transaction,
so debiting one account and crediting the other cannot be made durable
together, and a value is still capped, so the whole world cannot be hidden in
one key.

Two things make this harder than a single-key ledger.

First, a decision has to be *remembered*, not recomputed. A transfer that was
refused for insufficient funds must stay refused, even when it is redelivered
later and the source account has meanwhile been topped up by another transfer.
The batch below is arranged so that recomputing the answer on redelivery gives
a different one, which is the ordinary way this is got wrong.

Second, the two halves of a transfer are two durable facts about two different
keys. Either the design makes them one write, or it needs a recovery path that
any later delivery can complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from faultline.services import DurableStore, StoreState
from faultline.injector import TraceFacts
from faultline.world import World

TASK_ID = "t07_two_account_transfer"
TITLE = "Move money between two accounts without ever losing or inventing any"
ENTRYPOINT = "handle_transfer"

MAX_VALUE_BYTES = 32

OPENING: dict[str, int] = {"A": 100_000, "B": 0}
TOTAL = sum(OPENING.values())

APPLIED = "applied"
REJECTED = "rejected"

# (transfer_id, source, target, amount, the decision this transfer must get)
#
# t2 is refused when it first arrives, because A is down to 40000. By the time
# it is redelivered, t3 has put A back up to 60000 and the same request would
# now be affordable - but the answer to a request does not change because it
# was asked twice.
BATCH: tuple[tuple[str, str, str, int, str], ...] = (
    ("t1", "A", "B", 60_000, APPLIED),
    ("t2", "A", "B", 60_000, REJECTED),
    ("t1", "A", "B", 60_000, APPLIED),
    ("t3", "B", "A", 20_000, APPLIED),
    ("t2", "A", "B", 60_000, REJECTED),
    ("t4", "A", "B", 60_000, APPLIED),
    ("t3", "B", "A", 20_000, APPLIED),
    ("t4", "A", "B", 60_000, APPLIED),
)

EXPECTED_DECISIONS: dict[str, str] = {t[0]: t[4] for t in BATCH}


def _expected_balances() -> dict[str, int]:
    """Opening balances plus each *distinct* accepted transfer, applied once."""
    balances = dict(OPENING)
    for transfer_id in dict.fromkeys(entry[0] for entry in BATCH):
        _, source, target, amount, decision = next(
            entry for entry in BATCH if entry[0] == transfer_id
        )
        if decision == APPLIED:
            balances[source] -= amount
            balances[target] += amount
    return balances


EXPECTED_BALANCES = _expected_balances()

# No remote systems here, so there is nothing for a timeout to hit.
FAULT_VARIANTS: tuple[tuple[tuple[int, str], ...], ...] = ((),)

MAX_CRASHES = 2
OP_BUDGET = 400


@dataclass
class Durable:
    store: StoreState = field(
        default_factory=lambda: StoreState(
            data={f"acct:{name}": str(balance) for name, balance in OPENING.items()},
            max_value_bytes=MAX_VALUE_BYTES,
        )
    )


def new_durable_state() -> Durable:
    return Durable()


def invoke(world: World, solution: Any) -> Any:
    handler = getattr(solution, ENTRYPOINT, None)
    if handler is None:
        raise AttributeError(f"solution does not define {ENTRYPOINT}()")
    reader = getattr(solution, "read_balance", None)
    if reader is None:
        raise AttributeError("solution does not define read_balance()")

    durable: Durable = world.durable
    store = DurableStore(world, durable.store)

    decisions: list[tuple[str, Any]] = []
    for transfer_id, source, target, amount, _ in BATCH:
        decisions.append(
            (
                transfer_id,
                handler(
                    transfer_id=transfer_id,
                    source=source,
                    target=target,
                    amount_cents=amount,
                    store=store,
                ),
            )
        )

    balances = {name: reader(account=name, store=store) for name in OPENING}
    return {"decisions": decisions, "balances": balances}


def check(durable: Durable, returned: Any, facts: TraceFacts) -> list[str]:
    if not isinstance(returned, dict):
        return [f"invoke returned {returned!r}, which is a harness error"]

    violations: list[str] = []
    balances = returned["balances"]

    for name, value in balances.items():
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"read_balance({name!r}) returned {value!r}, expected an int"]

    oversized = [
        (key, value)
        for key, value in durable.store.data.items()
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES
    ]
    if oversized:
        key, value = oversized[0]
        violations.append(
            f"key {key!r} holds {len(value.encode('utf-8'))} bytes, over the "
            f"{MAX_VALUE_BYTES}-byte limit"
        )

    # The relationship, not the individual numbers: money is never created or
    # destroyed, only moved.
    total = sum(balances.values())
    if total != TOTAL:
        violations.append(
            f"the two accounts hold {total} between them, but only {TOTAL} ever existed, "
            f"so {abs(total - TOTAL)} was {'invented' if total > TOTAL else 'lost'} "
            f"(A={balances.get('A')}, B={balances.get('B')})"
        )

    for name, value in balances.items():
        if value < 0:
            violations.append(f"account {name} is overdrawn at {value}")

    # A decision, once given, is the answer to that request forever.
    by_id: dict[str, set[Any]] = {}
    for transfer_id, decision in returned["decisions"]:
        by_id.setdefault(transfer_id, set()).add(decision)
    for transfer_id, answers in by_id.items():
        if len(answers) > 1:
            violations.append(
                f"transfer {transfer_id} was answered {sorted(map(repr, answers))} on "
                "different deliveries; the same request cannot have two answers"
            )
            continue
        answer = next(iter(answers))
        expected = EXPECTED_DECISIONS[transfer_id]
        if answer not in (APPLIED, REJECTED):
            violations.append(
                f"transfer {transfer_id} was answered {answer!r}, expected {APPLIED!r} "
                f"or {REJECTED!r}"
            )
        elif answer != expected:
            violations.append(
                f"transfer {transfer_id} was answered {answer!r} but should have been "
                f"{expected!r}"
            )

    if not violations and balances != EXPECTED_BALANCES:
        violations.append(
            f"final balances are {balances}, expected {EXPECTED_BALANCES}"
        )

    return violations


def describe_state(durable: Durable) -> list[str]:
    return [
        durable.store.describe(),
        f"expected balances: {EXPECTED_BALANCES}",
        f"expected decisions: {EXPECTED_DECISIONS}",
    ]
