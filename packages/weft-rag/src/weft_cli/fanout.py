"""Finding every registered plugin that has a given capability, without naming any of them.

Task **5.1b** lifted this out of `weft_cli.deletion`, where task 5.1a wrote it against
`SourceDeletable` alone. `weft reconcile` asks the identical question of `Reconcilable` — *who,
across everything installed, can do this?* — and two copies of that walk could come to disagree
about who participates, which is the failure mode a fan-out exists to prevent rather than to
reproduce. One module, one answer, one place to correct.

**Who is a participant, and why `NodeStore` is filtered rather than collected whole.** Every
contract in the registry is walked, and a plugin whose registered *class* satisfies the
capability joins — `issubclass` against the class, never a constructed instance, so nothing is
built to find out whether it should have been (`weft_cli.run_services.class_provides` is the
shared check, public since 5.1a for exactly this reason). The one exception is `NodeStore`,
narrowed at task 5.1a to the single store `[services] store` names and widened again at task
**6.18** (G13's first repair, `docs/02-extension-model.md` §1 → *Extended by G13*): the narrowing
was right that a project with pgvector and Qdrant both installed must not connect to the backend
it does not use, and wrong that only the configured name counts, since the graph store registers
under `NodeStore` too and is written to by a pipeline `[services] store` never mentions. The rule
now filters `NodeStore` down to `store_names` — the configured name plus every `NodeStore` named
by one of the *project's own* documents, by an ancestor those documents derive from, or by a
persisted run record, computed by `weft_cli.participation.stores_in_use` — rather than to one name.
*It read "named by a pipeline in the catalogue" until carried repair `R11.2`, and the catalogue
there meant every document every installed pack contributes, which after G19 gave every project a
participant it had never asked for.* A contract that no `[services]`
key selects has no such choice to respect, so every plugin registered under it participates —
which is what makes a graph pack a participant with nothing declared and no core edit.

**Deduplicated by class, not by name.** One class may be registered under two contracts, and
building it twice would ask one backend to do the same job twice. The first `(contract, name)` in
sorted order wins; the rest are dropped.

**Nothing is constructed here.** A `Participant` holds the registered factory, not an instance, so
asking *who would be involved* — which a confirmation prompt and a `--dry-run` both want — costs no
connection to any backend in the project.

**And whatever *is* constructed from one is closed again — `built`, below. Ledger task 11.5.**
Because a `Participant` is a factory, the three places that actually build one — `weft_cli.deletion.
_ask`, `weft_cli.reconcile._ask` and `._ask_estimate` — are the only frames that ever hold the
instance, so they are the only frames that could release what it opened. That was harmless for
exactly as long as every participant was a store some other path had already opened and would
close; the graph pack is the first first-party participant to open a connection of its own, and
before this those three built one per invocation and dropped it. `deletion.py`, `fanout.py` and
`reconcile.py` contained no `aclose` at all (`grep` → 0 on 2026-09-09). It lives here rather than
in each caller for the reason the paragraph above gives about `participants_for`: three copies of
"build it, use it, close it" are three chances to disagree about the closing.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

from weft_cli.run_services import class_provides
from weft_kernel.registry import Registry, unwrap_factory
from weft_store import NodeStore


@dataclass(frozen=True, slots=True)
class Participant:
    """One plugin a fan-out will ask, and the factory that builds it."""

    contract: str
    name: str
    distribution: str
    build: Callable[[object | None], object]

    @property
    def label(self) -> str:
        """How this participant is named in output — the plugin name and where it came from."""
        return f"{self.name} ({self.distribution})"


def participants_for(
    capability: type[object], *, registry: Registry, store_names: frozenset[str]
) -> tuple[Participant, ...]:
    """Every registered plugin whose class satisfies `capability` — see the module docstring.

    A name in `store_names` that nothing registered is simply absent from the result rather
    than raised over: `weft_cli.registry_bootstrap.require_plugin` is what turns an unresolvable
    `[services] store` into a diagnosable refusal, and repeating that translation here would
    give the same mistake two different messages. The callers make that check first — a lesson
    with a `docs/lessons.md` entry of its own (L5.9).
    """
    found: list[Participant] = []
    seen: set[int] = set()
    for contract in sorted(registry.contracts(), key=lambda c: c.__qualname__):
        names = sorted(registry.names_for(contract))
        if contract is NodeStore:
            names = [name for name in names if name in store_names]
        for name in names:
            entry = registry.entry(contract, name)
            target = unwrap_factory(entry.factory)
            if not isinstance(target, type) or not class_provides(target, capability):
                continue
            if id(target) in seen:
                continue
            seen.add(id(target))
            found.append(
                Participant(
                    contract=contract.__qualname__,
                    name=name,
                    distribution=entry.distribution,
                    build=entry.factory,
                )
            )
    return tuple(found)


def _aclose_of(instance: object) -> Callable[[], Awaitable[None]] | None:
    """`instance.aclose`, if it has one and it is callable — the defensive read `weft_cli.ingest.
    _aclose_of` and `weft_cli.ask._aclose_of` already make, for the reason they give.

    **`aclose` is a fact read off the instance, never a contract method.** No store Protocol
    publishes one and none should start to: a participant that keeps no socket has nothing to
    close, and requiring the method would be a line every third-party pack has to write in order
    to be reaped. `PgVectorStore.aclose` is not part of `NodeStore`; it is a fact about that
    class, and this treats it as one.
    """
    found = getattr(instance, "aclose", None)
    if found is None or not callable(found):
        return None
    return cast("Callable[[], Awaitable[None]]", found)


@asynccontextmanager
async def built(target: Participant) -> AsyncGenerator[object]:
    """`target`, built for the length of the block, and closed again on the way out.

    **The close is inside the block's own `finally`, so a close that fails is the caller's to
    report rather than this helper's to swallow.** Each of the three callers wraps its whole turn
    in `except Exception` and turns a failure into *data* about that participant — so a backend
    that cannot release its connection becomes one named, reported participant failure and the
    fan-out carries on, which is the same answer those callers already give for a backend that
    cannot do the work. Swallowing it here would make a half-closed backend indistinguishable
    from a clean one.

    **`CancelledError` passes through untouched**, and the connection is still released on the
    way: `finally` runs on cancellation, the callers re-raise per G6, and nothing here catches it.
    """
    instance = target.build(None)
    try:
        yield instance
    finally:
        aclose = _aclose_of(instance)
        if aclose is not None:
            await aclose()


__all__ = ["Participant", "built", "participants_for"]
