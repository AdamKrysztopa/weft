"""Ledger task **36.4** — an operator can find a failed source without reading a database.

`weft sources list [--status failed]` (owner, 2026-09-21: noun-first beside `pipeline list` and
`plugins list`) reads the primary store's own records: URI, status, and for a failed one the stage,
error type, attempts, last attempt and message.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import pytest

from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_command.contract import CommandResult
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore, SourceFailure, SourceRecord, SourceStatus
from weft_store.memory import MemoryStore

_WHEN = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
_STORES: list[MemoryStore] = []


def _fixed(store: MemoryStore, config: object) -> MemoryStore:
    del config
    return store


def _store_factory(config: object) -> MemoryStore:
    del config
    return _STORES[-1]


def _record(name: str, *, failed: bool) -> SourceRecord:
    return SourceRecord(
        id=SourceId(f"file:///corpus/{name}"),
        uri=f"file:///corpus/{name}",
        content_hash=f"hash-{name}",
        indexed_at=_WHEN,
        pipeline="index-text",
        status=SourceStatus.FAILED if failed else SourceStatus.ACTIVE,
        failure=SourceFailure(
            error_type="Failed",
            stage="extract",
            message="not valid UTF-8",
            attempts=2,
            last_attempt_at=_WHEN,
        )
        if failed
        else None,
    )


async def _ctx_with(records: tuple[SourceRecord, ...]) -> Context:
    _STORES.append(MemoryStore())
    for record in records:
        await _STORES[-1].put_source(record)
    registry = Registry()
    registry.add(NodeStore, "memory", _store_factory, distribution="weft-store")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="memory"),
    )
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


async def test_every_recorded_source_is_listed() -> None:
    # Arrange
    ctx = await _ctx_with((_record("good.txt", failed=False), _record("bad.txt", failed=True)))

    # Act
    outcome = await commands.SourcesListCommand().run(commands.SourcesListArgs(), ctx)

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.SourcesListCommandResult)
    assert {entry.record.uri for entry in result.sources} == {
        "file:///corpus/good.txt",
        "file:///corpus/bad.txt",
    }


async def test_the_status_filter_keeps_only_that_status() -> None:
    # Arrange
    ctx = await _ctx_with((_record("good.txt", failed=False), _record("bad.txt", failed=True)))

    # Act
    outcome = await commands.SourcesListCommand().run(
        commands.SourcesListArgs(status=SourceStatus.FAILED), ctx
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.SourcesListCommandResult)
    assert [entry.record.uri for entry in result.sources] == ["file:///corpus/bad.txt"]


def test_a_failed_source_is_printed_with_what_went_wrong() -> None:
    # Arrange
    outcome: Outcome[CommandResult] = Produced(
        value=commands.SourcesListCommandResult(
            sources=(
                commands.ListedSource(store="memory", record=_record("bad.txt", failed=True)),
                commands.ListedSource(store="memory", record=_record("good.txt", failed=False)),
            )
        )
    )

    # Act
    rendered = render.render_outcome(outcome)

    # Assert
    lines = (rendered.stdout or "").splitlines()
    bad = next(line for line in lines if "bad.txt" in line)
    assert "failed" in bad
    assert "stage: extract" in bad
    assert "error: Failed" in bad
    assert "attempts: 2" in bad
    assert "not valid UTF-8" in bad
    good = next(line for line in lines if "good.txt" in line)
    assert "active" in good
    assert "attempts" not in good
    assert rendered.exit_code is ExitCode.SUCCESS


def test_an_empty_store_says_so() -> None:
    # Act
    rendered = render.render_outcome(Produced(value=commands.SourcesListCommandResult(sources=())))

    # Assert
    assert rendered.stdout == "no sources recorded."


def test_an_empty_filtered_list_names_the_filter_rather_than_claiming_nothing_is_recorded() -> None:
    """Found running the wheel: `--status failed` over a store holding one active source printed
    "no sources recorded.", which is false."""
    # Act
    rendered = render.render_outcome(
        Produced(value=commands.SourcesListCommandResult(sources=(), status=SourceStatus.FAILED))
    )

    # Assert
    assert rendered.stdout == "no failed sources recorded."


async def test_every_store_a_project_indexes_into_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`R36.4`: ingest records sources on every store its pipeline names, so a listing of
    `[services] store` alone missed a pipeline's second store. The same stores `weft delete`
    reaches are the ones listed, each entry naming its store."""
    # Arrange
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / "kg.yaml").write_text(
        "name: kg\nstages:\n  - id: store\n    use: memory\n  - id: graph-store\n    use: graph\n",
        encoding="utf-8",
    )
    primary, graph = MemoryStore(), MemoryStore()
    await primary.put_source(_record("good.txt", failed=False))
    await graph.put_source(_record("bad.txt", failed=True))
    registry = Registry()
    registry.add(NodeStore, "memory", partial(_fixed, primary), distribution="weft-store")
    registry.add(NodeStore, "graph", partial(_fixed, graph), distribution="weft-example-graph")
    deps = Dependencies(
        registry=registry,
        reports=(
            PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),
            PackReport(pack="graph", distribution="weft-example-graph", status=PackStatus.ACTIVE),
        ),
        services=ServiceSelection(store="memory"),
    )
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)

    # Act
    outcome = await commands.SourcesListCommand().run(commands.SourcesListArgs(), ctx)

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.SourcesListCommandResult)
    assert {(entry.store, entry.record.uri) for entry in result.sources} == {
        ("memory", "file:///corpus/good.txt"),
        ("graph", "file:///corpus/bad.txt"),
    }


def test_each_line_names_its_store_when_more_than_one_was_read() -> None:
    # Act
    rendered = render.render_outcome(
        Produced(
            value=commands.SourcesListCommandResult(
                sources=(
                    commands.ListedSource(store="graph", record=_record("bad.txt", failed=True)),
                    commands.ListedSource(store="memory", record=_record("a.txt", failed=False)),
                )
            )
        )
    )

    # Assert
    lines = (rendered.stdout or "").splitlines()
    assert any(line.startswith("graph  file:///corpus/bad.txt") for line in lines)
    assert any(line.startswith("memory  file:///corpus/a.txt") for line in lines)
