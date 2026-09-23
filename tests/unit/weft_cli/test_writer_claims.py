"""Carried repair **R43.15** — every command that writes a store claims its writer first.

`weft index` claimed a store before writing (`43.18`); `weft delete`, `weft reconcile` and the
reconcile pass `weft index` runs after it released its own claim wrote unclaimed. So a delete
landing between a layer's record read and its write brought the deleted source's record back.
Each of them now claims before its first write, releases when it is done, and is refused by
name while another writer holds the store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest

from weft_cli import commands
from weft_cli import ingest as ingest_module
from weft_cli.ingest import IndexResult
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import SourceId
from weft_kernel.registry import Registry
from weft_kernel.runner import RunSummary
from weft_store import NodeStore, ReconcileEstimate, ReconcileMode, ReconcileReport, Removed
from weft_store.contract import WriterBusyError, WriterClaim

_ELSEWHERE = WriterClaim(
    host="other-host", pid=4242, started_at=datetime(2026, 9, 23, tzinfo=UTC), command="weft index"
)


class _ClaimedStore:
    """A `SingleWriter` that deletes and reconciles, logging each act in order."""

    held_by: ClassVar[WriterClaim | None] = None
    events: ClassVar[list[str]] = []
    claims: ClassVar[list[WriterClaim]] = []

    def __init__(self, config: object = None) -> None:
        del config

    async def claim_writer(self, writer: WriterClaim) -> None:
        if _ClaimedStore.held_by is not None:
            raise WriterBusyError(_ClaimedStore.held_by)
        _ClaimedStore.held_by = writer
        _ClaimedStore.claims.append(writer)
        _ClaimedStore.events.append(f"claim:{writer.command}")

    async def release_writer(self) -> None:
        _ClaimedStore.held_by = None
        _ClaimedStore.events.append("release")

    async def delete_source(self, source_id: object) -> Removed:
        _ClaimedStore.events.append(f"delete:{source_id}")
        return Removed(source_id=SourceId(str(source_id)), node_count=1)

    async def reconcile(self, ctx: object, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        _ClaimedStore.events.append("reconcile")
        return ReconcileReport(mode=mode, examined=1, removed=0)

    async def estimate(self, ctx: object, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(mode=mode, pending=0, description="nothing", model_calls=0)


def _null_factory(config: object) -> object:
    del config
    return object()


@pytest.fixture(autouse=True)
def fresh_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_ClaimedStore, "held_by", None)
    monkeypatch.setattr(_ClaimedStore, "events", [])
    monkeypatch.setattr(_ClaimedStore, "claims", [])


def _ctx() -> Context:
    registry = Registry()
    registry.add(NodeStore, "pgvector", _ClaimedStore, distribution="weft-store")
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    deps = Dependencies(
        registry=registry,
        reports=tuple(
            PackReport(pack=pack, distribution=f"weft-{pack}", status=PackStatus.ACTIVE)
            for pack in ("extract", "chunk", "embed", "store")
        ),
        services=ServiceSelection(store="pgvector"),
    )
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


async def test_a_delete_claims_the_store_before_it_writes_and_releases_it() -> None:
    # Act
    await commands.DeleteCommand().run(commands.DeleteArgs(source_id="doc-1"), _ctx())

    # Assert
    assert _ClaimedStore.events == ["claim:weft delete", "delete:doc-1", "release"]
    assert _ClaimedStore.held_by is None


async def test_a_delete_while_another_writer_holds_the_store_is_refused_naming_it() -> None:
    # Arrange
    _ClaimedStore.held_by = _ELSEWHERE

    # Act — refused outright, never recorded as one participant's failure.
    with pytest.raises(WriterBusyError) as refused:
        await commands.DeleteCommand().run(commands.DeleteArgs(source_id="doc-1"), _ctx())

    # Assert
    assert "'weft index'" in str(refused.value)
    assert "other-host" in str(refused.value)
    assert not any(event.startswith("delete:") for event in _ClaimedStore.events)
    assert _ClaimedStore.held_by == _ELSEWHERE


async def test_a_reconcile_claims_the_store_before_it_writes_and_releases_it() -> None:
    # Act
    await commands.ReconcileCommand().run(
        commands.ReconcileArgs(mode=ReconcileMode.REPAIR, dry_run=False), _ctx()
    )

    # Assert
    assert _ClaimedStore.events == ["claim:weft reconcile", "reconcile", "release"]


async def test_a_reconcile_while_another_writer_holds_the_store_is_refused() -> None:
    # Arrange
    _ClaimedStore.held_by = _ELSEWHERE

    # Act
    with pytest.raises(WriterBusyError):
        await commands.ReconcileCommand().run(
            commands.ReconcileArgs(mode=ReconcileMode.REPAIR, dry_run=False), _ctx()
        )

    # Assert
    assert "reconcile" not in _ClaimedStore.events


async def test_a_dry_run_reconcile_writes_nothing_and_claims_nothing() -> None:
    # Arrange
    _ClaimedStore.held_by = _ELSEWHERE

    # Act
    await commands.ReconcileCommand().run(
        commands.ReconcileArgs(mode=ReconcileMode.FULL, dry_run=True), _ctx()
    )

    # Assert
    assert _ClaimedStore.claims == []


async def test_the_reconcile_after_an_index_claims_the_store_as_weft_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — `run_index` released its own claim before this pass began.
    async def _indexed(*_args: object, **_kwargs: object) -> IndexResult:
        return IndexResult(
            summary=RunSummary(produced=1, nothing_to_produce=0, failed=0), stored_count=1
        )

    monkeypatch.setattr(ingest_module, "run_index", _indexed)

    # Act
    await commands.IndexCommand().run(commands.IndexArgs(path=str(tmp_path)), _ctx())

    # Assert
    assert _ClaimedStore.events == ["claim:weft index", "reconcile", "release"]
