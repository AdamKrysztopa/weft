"""Unit tests for `weft_cli.reconcile`.

Mirrors `packages/weft-cli/src/weft_cli/reconcile.py`. Task **5.1b**: "derived state converges
on what the corpus actually holds, whatever was missed and whoever was not installed at the
time: `Reconcilable` is published, `weft reconcile` runs it, and a pass interrupted part-way
resumes rather than restarting."

The resumption property is what the fakes below exist for, and it is the one that cannot be
proven by inspection. A participant whose backlog is durable — the shape `02` §1 requires of a
real one, and the shape `PgVectorStore.reconcile` actually has, where the backlog *is* the
tombstone rows — is interrupted after part of its work, and the *next* pass is asserted to
finish the rest rather than to start over. A participant that raises is named, and the ones
after it are still asked. `CancelledError` propagates out of the fan-out untouched, per G6.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

import pytest

from weft_cli.reconcile import estimate_everywhere, participants, reconcile_everywhere
from weft_kernel.context import Context
from weft_kernel.payload import SourceId
from weft_kernel.registry import Registry
from weft_store import (
    NodeStore,
    Reconcilable,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
)


@runtime_checkable
class _GraphStore(Protocol):
    """A contract `weft_cli.reconcile` has never heard of — the graph pack's own, in miniature.

    Declared here rather than imported from `test_deletion`, which carries the same stand-in
    for the same reason: a test module's private names are its own, and pyright says so.
    """

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport: ...


class _DeleteOnlyStore:
    """A participant that can delete a source and cannot reconcile.

    The asymmetry is what makes "capability is derived, never declared" observable: it joins
    one fan-out and stays out of the other, with nothing written down either way.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: SourceId) -> Removed:
        return Removed(source_id=source_id, node_count=0)


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


class _DurableBacklog:
    """A participant with a backlog it re-reads, and a budget for how much it may do per pass.

    This is the shape the contract requires and the real stores have: the work outstanding
    lives *outside* the pass, so a pass that stops early loses nothing but its own progress.
    Class-level state stands in for a database, so a second `reconcile()` on a freshly built
    instance sees what the first one left — exactly the situation the CLI creates, since it
    builds a participant from the registry on every invocation.
    """

    backlog: list[str] = []
    per_pass = 2

    def __init__(self, config: object = None) -> None:
        del config

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        done = 0
        while _DurableBacklog.backlog and done < _DurableBacklog.per_pass:
            _DurableBacklog.backlog.pop(0)
            done += 1
        return ReconcileReport(
            mode=mode, examined=done, removed=done, remaining=len(_DurableBacklog.backlog)
        )

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(
            mode=mode,
            pending=len(_DurableBacklog.backlog),
            description=f"{len(_DurableBacklog.backlog)} item(s) outstanding",
            model_calls=len(_DurableBacklog.backlog) if mode is ReconcileMode.FULL else 0,
        )


class _Failing:
    def __init__(self, config: object = None) -> None:
        del config

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx, mode
        raise RuntimeError("graph index unavailable")

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx, mode
        raise RuntimeError("graph index unavailable")


class _Cancelling:
    def __init__(self, config: object = None) -> None:
        del config

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx, mode
        raise asyncio.CancelledError

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx, mode
        raise asyncio.CancelledError


async def test_a_converged_pass_reports_nothing_remaining() -> None:
    # Arrange
    _DurableBacklog.backlog = ["a", "b"]
    registry = Registry()
    registry.add(_GraphStore, "graph", _DurableBacklog, distribution="weft-graph")
    targets = participants(registry=registry, store_name="pgvector")

    # Act
    outcomes = await reconcile_everywhere(ReconcileMode.REPAIR, targets=targets, ctx=_ctx())

    # Assert
    assert (outcomes[0].converged, outcomes[0].report and outcomes[0].report.removed) == (True, 2)


async def test_an_interrupted_pass_resumes_rather_than_restarting() -> None:
    # Arrange — five items, two per pass: the first pass cannot finish.
    _DurableBacklog.backlog = ["a", "b", "c", "d", "e"]
    registry = Registry()
    registry.add(_GraphStore, "graph", _DurableBacklog, distribution="weft-graph")
    targets = participants(registry=registry, store_name="pgvector")

    # Act — three passes, each one a fresh instance built from the registry.
    passes = [
        (await reconcile_everywhere(ReconcileMode.REPAIR, targets=targets, ctx=_ctx()))[0]
        for _ in range(3)
    ]

    # Assert — each pass removed only what was left, never the whole backlog again.
    assert [(p.report and p.report.removed, p.report and p.report.remaining) for p in passes] == [
        (2, 3),
        (2, 1),
        (1, 0),
    ]


async def test_a_failing_participant_is_named_and_the_rest_are_still_asked() -> None:
    # Arrange
    _DurableBacklog.backlog = ["a"]
    registry = Registry()
    registry.add(_GraphStore, "broken", _Failing, distribution="weft-broken")
    registry.add(_GraphStore, "graph", _DurableBacklog, distribution="weft-graph")
    targets = participants(registry=registry, store_name="pgvector")

    # Act
    outcomes = await reconcile_everywhere(ReconcileMode.FULL, targets=targets, ctx=_ctx())

    # Assert
    assert [(o.plugin, o.error, o.converged) for o in outcomes] == [
        ("broken", "RuntimeError: graph index unavailable", False),
        ("graph", None, True),
    ]


async def test_cancellation_propagates_rather_than_becoming_a_named_failure() -> None:
    # Arrange
    registry = Registry()
    registry.add(_GraphStore, "cancels", _Cancelling, distribution="weft-graph")
    targets = participants(registry=registry, store_name="pgvector")

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await reconcile_everywhere(ReconcileMode.REPAIR, targets=targets, ctx=_ctx())


async def test_estimate_everywhere_reports_each_participant_s_own_cost() -> None:
    # Arrange — task 5.1c: a participant's own estimate travels unchanged, the same shape
    # `reconcile_everywhere` already carries `ReconcileReport` in.
    _DurableBacklog.backlog = ["a", "b", "c"]
    registry = Registry()
    registry.add(_GraphStore, "graph", _DurableBacklog, distribution="weft-graph")
    targets = participants(registry=registry, store_name="pgvector")

    # Act
    outcomes = await estimate_everywhere(ReconcileMode.FULL, targets=targets, ctx=_ctx())

    # Assert
    assert outcomes[0].estimate == ReconcileEstimate(
        mode=ReconcileMode.FULL, pending=3, description="3 item(s) outstanding", model_calls=3
    )


async def test_estimate_everywhere_names_a_failing_participant_rather_than_raising() -> None:
    # Arrange
    registry = Registry()
    registry.add(_GraphStore, "broken", _Failing, distribution="weft-broken")
    targets = participants(registry=registry, store_name="pgvector")

    # Act
    outcomes = await estimate_everywhere(ReconcileMode.FULL, targets=targets, ctx=_ctx())

    # Assert
    assert (outcomes[0].estimate, outcomes[0].error) == (
        None,
        "RuntimeError: graph index unavailable",
    )


async def test_estimate_everywhere_propagates_cancellation() -> None:
    # Arrange
    registry = Registry()
    registry.add(_GraphStore, "cancels", _Cancelling, distribution="weft-graph")
    targets = participants(registry=registry, store_name="pgvector")

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await estimate_everywhere(ReconcileMode.FULL, targets=targets, ctx=_ctx())


def test_a_node_store_that_cannot_reconcile_is_not_a_participant() -> None:
    """`_DeleteOnlyStore` is a full `NodeStore` with no `reconcile` — capability derived, not
    declared, so it joins the delete fan-out and stays out of this one with nothing written
    down either way.
    """
    # Arrange
    registry = Registry()
    registry.add(NodeStore, "pgvector", _DeleteOnlyStore, distribution="weft-store")

    # Act
    found = participants(registry=registry, store_name="pgvector")

    # Assert
    assert (found, isinstance(_DeleteOnlyStore(), Reconcilable)) == ((), False)
