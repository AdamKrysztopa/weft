"""A fan-out closes the connection it constructed. Ledger task **11.5**.

Mirrors `packages/weft-rag/src/weft_cli/deletion.py` and `weft_cli/reconcile.py`. Task 11.5's own
clause: the graph store *"closes its own connection when a fan-out constructed it"*.

**Why this is the fan-out's job and not the participant's.** `weft_cli.fanout.participants_for`
hands back a factory, never an instance — *"asking who would be involved costs no connection to any
backend"* — so the thing that builds a participant is `deletion._ask`/`reconcile._ask`, one call
per participant, and nothing else ever holds that object. A store that opened a connection on first
use therefore has no other moment at which anybody could close it. `weft_cli.ingest` and
`weft_cli.ask` already do this for the stores *they* build; `deletion.py`, `fanout.py` and
`reconcile.py` contained no `aclose` at all (`grep` → 0 on 2026-09-09), which was fine for exactly
as long as every participant was the store some other path had already opened.

**`aclose` is a fact read off the instance, never a contract method.** `weft_store.contract`
publishes no `aclose` and this must not start requiring one: a participant that has none is asked
nothing and closes nothing, which is what an in-memory store and every third-party pack that keeps
no socket should do. `weft_cli.ingest._aclose_of` is the existing defensive read and the shape
these follow — `getattr(instance, "aclose", None)`, called only when it is callable.

**Cancellation still propagates.** `CancelledError` is never swallowed to close a connection: the
close runs in a `finally`, so a cancelled fan-out still releases what it opened and still raises.
"""

from __future__ import annotations

from weft_cli.deletion import delete_everywhere
from weft_cli.deletion import participants as deletion_participants
from weft_cli.fanout import Participant
from weft_cli.reconcile import estimate_everywhere, reconcile_everywhere
from weft_cli.reconcile import participants as reconcile_participants
from weft_kernel.context import Context
from weft_kernel.payload import SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore, ReconcileEstimate, ReconcileMode, ReconcileReport, Removed


class _ClosingStore:
    """A participant that holds a connection and reports whether it was closed.

    Counts rather than flags: closing twice is as wrong as closing not at all, and a flag cannot
    tell the two apart.
    """

    closed: int = 0

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: SourceId) -> Removed:
        del source_id
        return Removed(source_id=SourceId("s"), node_count=1)

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        return ReconcileReport(mode=mode, examined=1, removed=0)

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(mode=mode, pending=0, description="nothing outstanding")

    async def aclose(self) -> None:
        type(self).closed += 1


class _StoreWithNoConnection:
    """A participant with no `aclose` at all — asked nothing, and that is the point.

    `aclose` is not on any published contract, so a fan-out that required one would be adding a
    method every third-party pack has to write in order to be reaped.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def delete_source(self, source_id: SourceId) -> Removed:
        del source_id
        return Removed(source_id=SourceId("s"), node_count=0)

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        return ReconcileReport(mode=mode, examined=0, removed=0)

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(mode=mode, pending=0, description="nothing outstanding")


class _FailingStore(_ClosingStore):
    """A participant whose work raises — the branch where a leak is most likely and worst.

    A connection opened by a call that then failed is exactly the one nothing else will close,
    and a fan-out that closes only on the happy path leaks precisely when things go wrong.
    """

    closed: int = 0

    async def delete_source(self, source_id: SourceId) -> Removed:
        del source_id
        raise RuntimeError("the backend refused")

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx, mode
        raise RuntimeError("the backend refused")


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _targets(kind: type[object], *, name: str = "graph") -> tuple[Participant, ...]:
    registry = Registry()
    registry.add(NodeStore, name, kind, distribution="weft-rag")
    return deletion_participants(registry=registry, store_names=frozenset({name}))


def _reconcile_targets(kind: type[object], *, name: str = "graph") -> tuple[Participant, ...]:
    registry = Registry()
    registry.add(NodeStore, name, kind, distribution="weft-rag")
    return reconcile_participants(registry=registry, store_names=frozenset({name}))


async def test_a_deletion_closes_the_participant_it_built() -> None:
    # Arrange
    _ClosingStore.closed = 0
    targets = _targets(_ClosingStore)

    # Act
    outcomes = await delete_everywhere(SourceId("doc-a"), targets=targets)

    # Assert — the work happened *and* the connection was released exactly once.
    assert [outcome.plugin for outcome in outcomes] == ["graph"]
    assert _ClosingStore.closed == 1


async def test_a_reconcile_closes_the_participant_it_built() -> None:
    # Arrange
    _ClosingStore.closed = 0
    targets = _reconcile_targets(_ClosingStore)

    # Act
    outcomes = await reconcile_everywhere(ReconcileMode.REPAIR, targets=targets, ctx=_ctx())

    # Assert
    assert [outcome.plugin for outcome in outcomes] == ["graph"]
    assert _ClosingStore.closed == 1


async def test_an_estimate_closes_the_participant_it_built() -> None:
    """`weft reconcile --dry-run full` builds participants to ask them what they would do.

    It opens the same connection the run would; a pass that only closes on the doing path leaks
    one per dry run, which is the invocation an operator repeats while deciding.
    """
    # Arrange
    _ClosingStore.closed = 0
    targets = _reconcile_targets(_ClosingStore)

    # Act
    estimates = await estimate_everywhere(ReconcileMode.FULL, targets=targets, ctx=_ctx())

    # Assert
    assert [estimate.plugin for estimate in estimates] == ["graph"]
    assert _ClosingStore.closed == 1


async def test_a_participant_whose_work_raised_is_still_closed() -> None:
    """The branch a happy-path close never reaches, and the one that leaks.

    The outcome still reports the failure by name — closing the connection must not swallow what
    went wrong, which is the whole reason `ParticipantOutcome` carries an `error` at all.
    """
    # Arrange
    _FailingStore.closed = 0
    targets = _targets(_FailingStore)

    # Act
    outcomes = await delete_everywhere(SourceId("doc-a"), targets=targets)

    # Assert
    assert outcomes[0].error is not None
    assert "the backend refused" in outcomes[0].error
    assert _FailingStore.closed == 1


async def test_a_participant_with_no_aclose_is_asked_for_none() -> None:
    """`aclose` is read off the instance, never required of it — no contract publishes one."""
    # Arrange
    targets = _targets(_StoreWithNoConnection)

    # Act
    outcomes = await delete_everywhere(SourceId("doc-a"), targets=targets)

    # Assert — it ran, it reported, and nothing raised for the method it does not have.
    assert outcomes[0].error is None
