"""Exception types.

`GatewayTimeout` is part of the contract shown to the solution author: it is a
normal, expected condition that solution code must cope with.

`SimulatedCrash` is *not* part of that contract. It models the process being
killed, so solution code must never catch it. The injector treats a caught
`SimulatedCrash` as a harness violation rather than as a passing trace.
"""


class GatewayTimeout(Exception):
    """The gateway did not answer in time.

    The outcome of the call is genuinely unknown: the charge may or may not
    have been created on the gateway side.
    """


class SimulatedCrash(BaseException):
    """The process died. Derives from BaseException so that a bare
    `except Exception` in solution code does not swallow it."""


class HarnessViolation(Exception):
    """Solution code broke a rule of the harness (e.g. swallowed a crash)."""
