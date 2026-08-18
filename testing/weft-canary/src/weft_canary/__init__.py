"""The canary distribution — test-only, never published.

Fitness function 8 (G3) needs to prove two properties about discovery, and both
reduce to the same question: *did any third-party pack code run?*

  (a) A pack refused by an allow-list is never imported.
  (b) No pack code executes for a command that does not need the registry.

The trick that makes both categorical rather than timing-dependent: this module
writes a marker file **at import**, before any ``register`` function could be
called. The assertion is always "marker absent", which needs no threshold and
survives a subprocess boundary — so the same canary works for an in-process
discovery test and for a CLI invocation.

The path comes from the environment because the test owns the temporary
directory, and importing this module must have no effect at all when the
variable is unset — otherwise the canary would write into whatever tree happened
to be current.
"""

import os
from pathlib import Path

from pydantic import BaseModel

from weft_kernel.discovery import PackRegistrar

MARKER_ENV_VAR = "WEFT_CANARY_MARKER"


def _leave_marker() -> None:
    """Record that this module was imported, if a test asked us to."""
    target = os.environ.get(MARKER_ENV_VAR)
    if not target:
        return

    Path(target).write_text("imported\n", encoding="utf-8")


_leave_marker()


class Settings(BaseModel):
    """The canary has nothing to configure — an empty model is still the required shape."""


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """The entry point `weft.packs` resolves to. Must never run — see the module docstring.

    Every test exercising this distribution refuses it by an allow-list, so
    `register` never executes; it exists only so this distribution has the
    same shape — one entry point resolving to `register(registrar, settings)`
    — any other pack does. If this function ever runs, fitness function 8(a)
    has already failed by the time it does.
    """
    del registrar, settings
