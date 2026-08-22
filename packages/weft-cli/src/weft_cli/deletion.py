"""Fanning a source's deletion out across everything that holds data derived from it.

Task **5.1a**. `docs/03-cli.md` → *Command surface*: "`weft delete <source-id>` fans out
synchronously across every registered plugin satisfying `SourceDeletable` — the node store,
and any pack holding data derived from it, such as the graph store. Every participant is
tried, and one that fails is *named* rather than swallowed: a partial deletion the operator
does not know about is worse than a refusal."

**Every participant is tried, and the order of those two clauses is the whole design.** The
obvious implementation — `await` each participant in turn and let the first exception
propagate — produces exactly the failure this command exists to prevent: participant one
deletes, participant two raises, participants three and four are never asked, and the
operator is told about one failure while an unknown amount of derived data quietly survives
its source. So a raising participant is caught, recorded against its own name, and the
fan-out continues; the *command* then fails, naming every participant and what each one did.
`CancelledError` is the one exception that still propagates untouched, per G6 — a cancelled
delete is not a failed participant, and swallowing it would make the command uninterruptible.

**Who a participant is, is `weft_cli.fanout`'s question, not this module's** — task 5.1b lifted
that walk out when `weft reconcile` needed the identical answer about a different capability.
This module owns what happens *to* the participants once they are known.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, ConfigDict

from weft_cli.fanout import Participant, participants_for
from weft_kernel.payload import SourceId
from weft_kernel.registry import Registry
from weft_store import SourceDeletable


class ParticipantOutcome(BaseModel):
    """What one participant did, or why it could not.

    Exactly one of `node_count`/`error` is populated. `error` carries the exception's own
    type alongside its text, because a bare message like `connection refused` names nothing
    an operator can act on and a partial deletion is precisely the case where they need to
    know which layer refused.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: str
    plugin: str
    distribution: str
    node_count: int | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None


def participants(*, registry: Registry, store_name: str) -> tuple[Participant, ...]:
    """Every registered plugin that can delete a source — `weft_cli.fanout`, narrowed to one
    capability so that a caller says what it means rather than repeating the Protocol.
    """
    return participants_for(SourceDeletable, registry=registry, store_name=store_name)


async def delete_everywhere(
    source_id: SourceId, *, targets: tuple[Participant, ...]
) -> tuple[ParticipantOutcome, ...]:
    """Ask every participant to delete `source_id`, in order, recording each answer.

    Sequential rather than gathered, because `docs/03-cli.md` says *synchronously* and means
    it: a `TaskGroup` would cancel the participants still running the moment one raised,
    which is the "some were never asked" failure written a second way. Construction is
    inside the loop and inside the `try` for the same reason a call is — a pack whose
    `__init__` raises is a participant that failed, not a crash that hides the four after it.
    """
    outcomes: list[ParticipantOutcome] = []
    for target in targets:
        outcomes.append(await _ask(target, source_id))
    return tuple(outcomes)


async def _ask(target: Participant, source_id: SourceId) -> ParticipantOutcome:
    """One participant's whole turn — build, call, and answer with what happened either way.

    The broad `except Exception` is this function's subject rather than a lapse: every
    participant is tried, so a failure has to become *data* about that participant instead
    of control flow that ends the fan-out. `CancelledError` is re-raised first, per G6 — it
    is not an exception about this participant at all.
    """
    try:
        instance = target.build(None)
        removed = await _delete_from(instance, source_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return ParticipantOutcome(
            contract=target.contract,
            plugin=target.name,
            distribution=target.distribution,
            error=f"{type(exc).__name__}: {exc}",
        )
    return ParticipantOutcome(
        contract=target.contract,
        plugin=target.name,
        distribution=target.distribution,
        node_count=removed,
    )


async def _delete_from(instance: object, source_id: SourceId) -> int:
    """One participant's `delete_source`, with the `isinstance` that makes it callable.

    The class-level `issubclass` in `participants()` cannot be the last word: a factory may
    return something other than the class it was registered as, and a participant that is
    not what it claimed is a failure with a name rather than an `AttributeError` from
    somewhere deeper.
    """
    if not isinstance(instance, SourceDeletable):
        raise TypeError(
            f"{type(instance).__qualname__} was registered as a class satisfying "
            f"SourceDeletable but the instance it built does not — no 'delete_source' to call"
        )
    removed = await instance.delete_source(source_id)
    return removed.node_count


__all__ = [
    "ParticipantOutcome",
    "delete_everywhere",
    "participants",
]
