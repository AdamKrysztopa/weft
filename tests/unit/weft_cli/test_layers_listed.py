"""Ledger task **43.10** — the layers built over a corpus are visible without reading a database.

`weft sources list` prints each source's layers and their statuses, so an operator can see which
documents a layer has reached and why one failed. `weft target list` prints, per target, the
layers complete on every source there: those are the layers a rung may require (`43.9`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from weft_cli import commands, render
from weft_cli.commands import (
    ListedSource,
    ListedTarget,
    SourcesListCommandResult,
    TargetListCommandResult,
)
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import (
    LayerRecord,
    LayerStatus,
    NodeStore,
    SourceFailure,
    SourceRecord,
    SourceStatus,
)
from weft_store.memory import MemoryStore

_WHEN = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def _layer(name: str, status: LayerStatus) -> LayerRecord:
    failure = (
        SourceFailure(
            error_type="Failed",
            stage="facts",
            message="the model refused",
            attempts=1,
            last_attempt_at=_WHEN,
        )
        if status is LayerStatus.FAILED
        else None
    )
    return LayerRecord(
        name=name, pipeline_identity="i", status=status, failure=failure, attempts=1, at=_WHEN
    )


def _record(name: str, *layers: LayerRecord) -> SourceRecord:
    return SourceRecord(
        id=SourceId(f"file:///corpus/{name}"),
        uri=f"file:///corpus/{name}",
        content_hash=f"hash-{name}",
        indexed_at=_WHEN,
        pipeline="index-text",
        status=SourceStatus.ACTIVE,
        layers=layers,
    )


def test_each_source_lists_its_layers_with_their_statuses() -> None:
    # Arrange — three sources, each layer status distinguishable from the others (`L12.6`).
    result = SourcesListCommandResult(
        sources=(
            ListedSource(
                store="pgvector",
                record=_record(
                    "a.txt",
                    _layer("enrich-with-questions", LayerStatus.ACTIVE),
                    _layer("enrich-with-facts", LayerStatus.FAILED),
                ),
            ),
            ListedSource(
                store="pgvector",
                record=_record("b.txt", _layer("enrich-with-questions", LayerStatus.INDEXING)),
            ),
            ListedSource(store="pgvector", record=_record("c.txt")),
        )
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout is not None
    assert rendered.stdout.splitlines() == [
        "file:///corpus/a.txt  active  layers: enrich-with-questions active, "
        "enrich-with-facts failed (stage: facts)",
        "file:///corpus/b.txt  active  layers: enrich-with-questions indexing",
        "file:///corpus/c.txt  active",
    ]


def test_a_target_lists_the_layers_complete_on_every_source() -> None:
    # Arrange
    result = TargetListCommandResult(
        targets=(
            ListedTarget(
                store="pgvector",
                name="default",
                live=True,
                previous=False,
                embedding=None,
                sources=3,
                layers_complete=("enrich-with-questions",),
            ),
            ListedTarget(
                store="pgvector",
                name="w128",
                live=False,
                previous=False,
                embedding=None,
                sources=3,
            ),
        )
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout is not None
    assert rendered.stdout.splitlines() == [
        "default  live  embedding not recorded  3 sources  layers complete: enrich-with-questions",
        "w128  -  embedding not recorded  3 sources",
    ]


async def _target_list(*records: SourceRecord) -> ListedTarget:
    store = MemoryStore()
    for record in records:
        await store.put_source(record)
    registry = Registry()

    def _factory(config: object) -> MemoryStore:
        del config
        return store

    registry.add(NodeStore, "memory", _factory, distribution="weft-store")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="memory"),
    )
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    outcome = await commands.TargetListCommand().run(commands.NoArgs(), ctx)
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, TargetListCommandResult)
    (target,) = result.targets
    return target


async def test_target_list_counts_a_layer_complete_only_when_every_source_has_it() -> None:
    # Act
    complete = await _target_list(
        _record("a.txt", _layer("enrich-with-questions", LayerStatus.ACTIVE)),
        _record("b.txt", _layer("enrich-with-questions", LayerStatus.ACTIVE)),
    )
    pending = await _target_list(
        _record("a.txt", _layer("enrich-with-questions", LayerStatus.ACTIVE)),
        _record("b.txt"),
    )

    # Assert
    assert complete.layers_complete == ("enrich-with-questions",)
    assert pending.layers_complete == ()
