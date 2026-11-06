"""Exception types.

The `RemoteTimeout` family is part of the contract shown to the solution
author: these are normal, expected conditions that solution code must cope
with, and each task prompt says so.

`SimulatedCrash` is *not* part of that contract. It models the process being
killed, so solution code must never catch it. The injector treats a caught
`SimulatedCrash` as a harness violation rather than as a passing trace.
"""


class RemoteTimeout(Exception):
    """A remote call did not answer. Its outcome is genuinely unknown: the
    request may have been applied before the response was lost, or not at
    all."""


class GatewayTimeout(RemoteTimeout):
    """The payment gateway did not answer. The charge may or may not exist."""


class TransferTimeout(RemoteTimeout):
    """The legacy transfer system did not answer. The money may or may not have
    moved, and there is no way to find out."""


class InventoryTimeout(RemoteTimeout):
    """The inventory service did not answer. The hold or release may or may not
    have taken effect."""


class BrokerTimeout(RemoteTimeout):
    """The message broker did not answer. The message may or may not have been
    accepted for delivery."""


class StoreValueTooLarge(Exception):
    """A value exceeded the store's per-value size limit.

    Part of the contract, and declared in the prompt of any task that sets a
    limit. It exists to rule out the degenerate design where every fact a
    handler has ever learned is serialised into one key: that makes any
    single-key store trivially transactional, and it is a real bug, because
    the row grows without bound as traffic arrives.
    """


class ChargeDeclined(Exception):
    """The gateway refused the charge. Unlike a timeout this is a definite
    answer: no money moved, and retrying the same charge will not help."""


class SimulatedCrash(BaseException):
    """The process died. Derives from BaseException so that a bare
    `except Exception` in solution code does not swallow it."""


class HarnessViolation(Exception):
    """Solution code broke a rule of the harness (e.g. swallowed a crash)."""
