"""Ledger task **36.4** — an operator can find a failed source without reading a database.

`weft sources list [--status failed]` (owner, 2026-09-21: noun-first beside `pipeline list` and
`plugins list`) reads the primary store's own records: URI, status, and for a failed one the stage,
error type, attempts, last attempt and message.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
    assert {record.uri for record in result.sources} == {
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
    assert [record.uri for record in result.sources] == ["file:///corpus/bad.txt"]


def test_a_failed_source_is_printed_with_what_went_wrong() -> None:
    # Arrange
    outcome: Outcome[CommandResult] = Produced(
        value=commands.SourcesListCommandResult(
            sources=(_record("bad.txt", failed=True), _record("good.txt", failed=False))
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
