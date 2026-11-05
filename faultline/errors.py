"""Exception types.

`GatewayTimeout` is part of the contract shown to the solution author: it is a
normal, expected condition that solution code must cope with.

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


class BrokerTimeout(RemoteTimeout):
    """The message broker did not answer. The message may or may not have been
    accepted for delivery."""


class SimulatedCrash(BaseException):
    """The process died. Derives from BaseException so that a bare
    `except Exception` in solution code does not swallow it."""


class HarnessViolation(Exception):
    """Solution code broke a rule of the harness (e.g. swallowed a crash)."""
