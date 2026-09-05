"""Discovery for tests, with the canary left where it belongs — ledger task **6.33**.

`weft_cli.contract_reference.discover_for_reference()` discovers **open**: no `[packs] allow`, so
every installed pack is imported. That is correct for what it is — a reference generator describes
the contracts the packs on *this machine* publish, and an operator running it wants all of them.

**It is wrong inside a test session, and fitness function 8 is what says so.** `testing/weft-canary`
exists to prove a refused pack is *never imported*, and it proves it with a marker file written at
import plus an in-process `weft_canary not in sys.modules` assertion. Any test that discovers open
imports the canary and makes that assertion unanswerable for every test after it — Python does not
re-execute an already-imported module, so the marker check would pass even if the code under test
loaded the canary when it should not have. FF8's own guard says exactly this: *"Something else in
this test session imported the canary first; find it and stop it from doing so."*

**Found at Phase 6's close, and the gate had never shown it.** `pytest tests/docs
tests/architecture` fails; `pytest tests` passes; the only difference is that `tests/architecture`
sorts first in the second. Four `tests/docs` modules called the open helper. `docs/lessons.md`
L5.21 — a test that passes only because another file ran first is a defect in the test — and the
mirror of it, a test that *fails* only because another file ran first.

**Why the repair is here and not in `weft_cli`.** Two reasons, and the second is the one that
decides it. `discover_for_reference`'s open posture is right for its own job, so narrowing it would
fix a test problem by making a shipped function worse. And `02` §2 settles that a pack is refused
**by an allow-list, never by name** — putting `"weft-canary"` in shipped code would be that rule
broken in the one distribution that must not break it. Here, in the test tree, an allow-list is
exactly what this is: the list of packs a test session means to load.
"""

from __future__ import annotations

from importlib import metadata
from typing import Final

from weft_kernel.discovery import discover
from weft_kernel.registry import Registry

#: The one distribution a test session must never import. Named here, in the tests, because that
#: is where the fact lives — `testing/weft-canary`'s whole purpose is to be refused, and fitness
#: function 8's assertions are the reason.
CANARY: Final[str] = "weft-canary"

ENTRY_POINT_GROUP: Final[str] = "weft.packs"

#: Structurally valid and never dialled — `weft-store`'s `register()` only partial-binds
#: `PgVectorStore(settings)` and `PgVectorStore.__init__` opens no connection, so discovery runs
#: here without a container. Spelled out rather than imported from `weft_cli.contract_reference`'s
#: private constant, the same choice `tests/architecture/test_release_set.py` makes for the same
#: reason: reaching into another distribution's private name would make a rename there a failure
#: here.
_PLACEHOLDER_DSN: Final[str] = "postgresql://tests-discovery/placeholder"


def installed_packs_except_the_canary() -> frozenset[str]:
    """Every installed pack the test session is willing to import.

    Derived from what is actually installed rather than from a list, so a pack added to the
    workspace tomorrow is discovered here without an edit — the allow-list is *"everything except
    the one thing that exists to be refused"*, which is a rule rather than an inventory.
    """
    return frozenset(
        entry_point.dist.name
        for entry_point in metadata.entry_points(group=ENTRY_POINT_GROUP)
        if entry_point.dist is not None and entry_point.dist.name != CANARY
    )


def discover_for_tests() -> Registry:
    """A registry populated exactly as `discover_for_reference()` populates one, minus the canary.

    `weft-store` gets the same structurally-valid, never-dialled DSN, for the reason that
    function's own module docstring gives: `PgVectorStore.__init__` opens no connection, so
    discovery runs here without a container.
    """
    registry = Registry()
    discover(
        registry,
        allow=installed_packs_except_the_canary(),
        pack_settings={"weft-store": {"dsn": _PLACEHOLDER_DSN}},
    )
    return registry
