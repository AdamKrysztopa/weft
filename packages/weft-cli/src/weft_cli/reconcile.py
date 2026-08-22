"""Converging every participant's derived state against what the corpus actually holds.

Task **5.1b**. `docs/02-extension-model.md` §1 → *Extended by G7*: "`Reconcilable` is the safety
net, and it is why there is no bus. A bus reaches only subscribers live when the event fired; it
cannot repair a pack installed *after* the corpus was built, a drain killed mid-flight, or a
second machine sharing one database. Convergence can."

**The same fan-out shape as `weft_cli.deletion`, and deliberately the same failure rule.** Every
participant is asked; one that raises is recorded against its own name and the pass continues; the
*command* then fails, naming what each participant did. A convergence that stopped at the first
failure would leave the operator believing the rest had converged.

**`CancelledError` propagates untouched, and here that is the feature rather than the caveat.** A
reconciliation pass is `O(corpus)` and a person will interrupt one. G6 says it propagates; `02` §1
says a pass interrupted at 2,000 of 4,312 "resumes there rather than starting again", and the two
clauses only hold together because a participant's backlog is **durable state it re-reads**, never
a cursor held in this process. So there is nothing here to save on the way out: what a cancelled
pass did not do is still there to be found, and the honest thing for this module to do with a
cancellation is get out of the way.

**What this module decided as of 5.1c, and what it still leaves to the caller.** `estimate_
everywhere` below is the fan-out `ReconcileEstimate` needs — the identical shape as `reconcile_
everywhere`, over `Reconcilable.estimate` instead of `.reconcile` — but *whether* a caller asks
for one, and what it prints, stays `docs/03-cli.md`'s and `weft_cli.commands`': the automatic
post-index pass, the per-run flag, and the cost stated before it is spent are all decided at the
command layer, never here. This module takes a `ReconcileMode` and carries it to every
participant unchanged, for either question.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, ConfigDict

from weft_cli.fanout import Participant, participants_for
from weft_kernel.context import Context
from weft_kernel.registry import Registry
from weft_store import Reconcilable, ReconcileEstimate, ReconcileMode, ReconcileReport


class ReconcileOutcome(BaseModel):
    """What one participant's pass did, or why it could not.

    Exactly one of `report`/`error` is populated. The whole `ReconcileReport` is carried rather
    than a flattened count, because `remaining` is the field that says whether another pass is
    owed and a summary that dropped it would turn "interrupted" into "finished".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: str
    plugin: str
    distribution: str
    report: ReconcileReport | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def converged(self) -> bool:
        """Whether this participant finished. A failure never counts as converged."""
        return self.report is not None and self.report.converged


class ReconcileEstimateOutcome(BaseModel):
    """What one participant said converging would cost, or why it could not say.

    Exactly one of `estimate`/`error` is populated — the same shape `ReconcileOutcome` already
    has, for the same reason: a participant whose `estimate` raises is named rather than
    swallowed, so a caller printing a cost block sees "this pack could not be asked" rather
    than a missing line with no explanation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: str
    plugin: str
    distribution: str
    estimate: ReconcileEstimate | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None


def participants(*, registry: Registry, store_name: str) -> tuple[Participant, ...]:
    """Every registered plugin that can converge its own state — `weft_cli.fanout`, narrowed."""
    return participants_for(Reconcilable, registry=registry, store_name=store_name)


async def reconcile_everywhere(
    mode: ReconcileMode, *, targets: tuple[Participant, ...], ctx: Context
) -> tuple[ReconcileOutcome, ...]:
    """Ask every participant to converge, in order, recording each answer."""
    return tuple([await _ask(target, mode, ctx) for target in targets])


async def _ask(target: Participant, mode: ReconcileMode, ctx: Context) -> ReconcileOutcome:
    """One participant's whole turn — build, converge, and answer with what happened either way.

    The broad `except Exception` is this function's subject rather than a lapse: every
    participant is asked, so a failure has to become *data* about that participant instead of
    control flow that ends the pass. `CancelledError` is re-raised first, per G6 — see the
    module docstring for why a cancelled pass needs nothing saved here.
    """
    try:
        instance = target.build(None)
        report = await _converge(instance, mode, ctx)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return ReconcileOutcome(
            contract=target.contract,
            plugin=target.name,
            distribution=target.distribution,
            error=f"{type(exc).__name__}: {exc}",
        )
    return ReconcileOutcome(
        contract=target.contract,
        plugin=target.name,
        distribution=target.distribution,
        report=report,
    )


async def _converge(instance: object, mode: ReconcileMode, ctx: Context) -> ReconcileReport:
    """One participant's `reconcile`, with the `isinstance` that makes it callable.

    The class-level `issubclass` in `participants_for` cannot be the last word: a factory may
    return something other than the class it was registered as, and a participant that is not
    what it claimed is a failure with a name rather than an `AttributeError` from deeper down.
    """
    if not isinstance(instance, Reconcilable):
        raise TypeError(
            f"{type(instance).__qualname__} was registered as a class satisfying Reconcilable "
            f"but the instance it built does not — no 'reconcile' to call"
        )
    return await instance.reconcile(ctx, mode)


async def estimate_everywhere(
    mode: ReconcileMode, *, targets: tuple[Participant, ...], ctx: Context
) -> tuple[ReconcileEstimateOutcome, ...]:
    """Ask every participant what converging would cost, in order, recording each answer.

    The identical fan-out `reconcile_everywhere` above is, over `Reconcilable.estimate`
    instead of `.reconcile` — a participant is never asked to converge by *this* function, so
    calling it costs nothing an operator did not already choose to spend by asking. Whether a
    caller calls this at all, for which mode, is `weft_cli.commands`' — see the module
    docstring.
    """
    return tuple([await _ask_estimate(target, mode, ctx) for target in targets])


async def _ask_estimate(
    target: Participant, mode: ReconcileMode, ctx: Context
) -> ReconcileEstimateOutcome:
    """One participant's whole turn — build, ask, and answer with what happened either way.

    The same failure-isolation shape as `_ask` above, for the same reason: one participant
    that cannot say its own cost must not stop the rest from being asked, or turn "unknown"
    into a fatal error for a caller that only wanted a number to print.
    """
    try:
        instance = target.build(None)
        estimate = await _estimate_of(instance, mode, ctx)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return ReconcileEstimateOutcome(
            contract=target.contract,
            plugin=target.name,
            distribution=target.distribution,
            error=f"{type(exc).__name__}: {exc}",
        )
    return ReconcileEstimateOutcome(
        contract=target.contract,
        plugin=target.name,
        distribution=target.distribution,
        estimate=estimate,
    )


async def _estimate_of(instance: object, mode: ReconcileMode, ctx: Context) -> ReconcileEstimate:
    """One participant's `estimate`, with the `isinstance` that makes it callable.

    Mirrors `_converge`'s own reasoning: the class-level `issubclass` in `participants_for`
    cannot be the last word, since a factory may return something other than the class it was
    registered as.
    """
    if not isinstance(instance, Reconcilable):
        raise TypeError(
            f"{type(instance).__qualname__} was registered as a class satisfying Reconcilable "
            f"but the instance it built does not — no 'estimate' to call"
        )
    return await instance.estimate(ctx, mode)


__all__ = [
    "ReconcileEstimateOutcome",
    "ReconcileOutcome",
    "estimate_everywhere",
    "participants",
    "reconcile_everywhere",
]
