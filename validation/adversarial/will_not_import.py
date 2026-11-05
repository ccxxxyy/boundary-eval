"""Adversarial input: a module that raises at import time, which is what
truncated or hallucinated model output usually looks like. Must be reported as
a load error, not crash the harness."""

from __future__ import annotations

import this_module_does_not_exist  # noqa: F401


def handle_order(*args, **kwargs) -> str:
    return "never reached"
