"""Finding every registered plugin that has a given capability, without naming any of them.

Task **5.1b** lifted this out of `weft_cli.deletion`, where task 5.1a wrote it against
`SourceDeletable` alone. `weft reconcile` asks the identical question of `Reconcilable` — *who,
across everything installed, can do this?* — and two copies of that walk could come to disagree
about who participates, which is the failure mode a fan-out exists to prevent rather than to
reproduce. One module, one answer, one place to correct.

**Who is a participant, and why the node store is chosen rather than collected.** Every contract
in the registry is walked, and a plugin whose registered *class* satisfies the capability joins —
`issubclass` against the class, never a constructed instance, so nothing is built to find out
whether it should have been (`weft_cli.run_services.class_provides` is the shared check, public
since 5.1a for exactly this reason). The one exception is `NodeStore`, where `[services] store`
has already chosen which store this project writes to: fanning out across every registered
`NodeStore` would connect to pgvector and Qdrant both, and act on a database the operator does not
use. A contract that no `[services]` key selects has no such choice to respect, so every plugin
registered under it participates — which is what makes a graph pack a participant with nothing
declared and no core edit.

**Deduplicated by class, not by name.** One class may be registered under two contracts, and
building it twice would ask one backend to do the same job twice. The first `(contract, name)` in
sorted order wins; the rest are dropped.

**Nothing is constructed here.** A `Participant` holds the registered factory, not an instance, so
asking *who would be involved* — which a confirmation prompt and a `--dry-run` both want — costs no
connection to any backend in the project.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
    capability: type[object], *, registry: Registry, store_name: str
) -> tuple[Participant, ...]:
    """Every registered plugin whose class satisfies `capability` — see the module docstring.

    A `store_name` nothing registered is simply absent from the result rather than raised over:
    `weft_cli.registry_bootstrap.require_plugin` is what turns an unresolvable `[services]
    store` into a diagnosable refusal, and repeating that translation here would give the same
    mistake two different messages. The callers make that check first — a lesson with a
    `docs/lessons.md` entry of its own (L5.9).
    """
    found: list[Participant] = []
    seen: set[int] = set()
    for contract in sorted(registry.contracts(), key=lambda c: c.__qualname__):
        names = sorted(registry.names_for(contract))
        if contract is NodeStore:
            names = [name for name in names if name == store_name]
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


__all__ = ["Participant", "participants_for"]
