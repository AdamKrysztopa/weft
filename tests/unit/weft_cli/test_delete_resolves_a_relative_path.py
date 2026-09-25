"""Task 43.31: `weft delete` resolves a relative path against the working directory.

A source is recorded under its resolved absolute path
(`weft_extract/text.py:128 "source_id=SourceId(str(path.resolve()))"`) and a `file://` uri.
`weft delete corpus/a.md`
compared the argument with both as typed, matched neither, and answered `nothing held` at exit 0
while the source stayed. A relative path now resolves against the working directory first, so it
deletes what the absolute path deletes — including a file already gone from disk, which is the
usual reason to delete one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest

from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore, Removed, SourceRecord, SourceStatus


class _RecordingStore:
    """`test_delete_ids._RecordingStore`: sources recorded by resolved path and `file://` uri."""

    records: ClassVar[dict[str, SourceRecord]] = {}
    deleted: ClassVar[list[str]] = []

    def __init__(self, config: object = None) -> None:
        del config

    async def list_sources(self) -> tuple[SourceRecord, ...]:
        return tuple(_RecordingStore.records.values())

    async def delete_source(self, source_id: SourceId) -> Removed:
        _RecordingStore.deleted.append(str(source_id))
        held = _RecordingStore.records.pop(str(source_id), None)
        return Removed(source_id=source_id, node_count=3 if held is not None else 0)


def _null_factory(config: object) -> object:
    del config
    return object()


def _record(path: Path) -> SourceRecord:
    resolved = path.resolve()
    return SourceRecord(
        id=SourceId(str(resolved)),
        uri=resolved.as_uri(),
        content_hash="hash-a",
        indexed_at=datetime(2026, 9, 25, tzinfo=UTC),
        pipeline="built-in",
        status=SourceStatus.ACTIVE,
    )


@pytest.fixture
def held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """One source, `corpus/a.md` under the working directory, recorded but never on disk."""
    monkeypatch.chdir(tmp_path)
    record = _record(tmp_path / "corpus" / "a.md")
    monkeypatch.setattr(_RecordingStore, "records", {str(record.id): record})
    monkeypatch.setattr(_RecordingStore, "deleted", [])
    return str(record.id)


def _ctx() -> Context:
    registry = Registry()
    registry.add(NodeStore, "pgvector", _RecordingStore, distribution="weft-store")
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="pgvector"),
    )
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


async def _delete(source_id: str) -> render.Rendered:
    outcome = await commands.DeleteCommand().run(commands.DeleteArgs(source_id=source_id), _ctx())
    assert isinstance(outcome, Produced)
    return render.render_outcome(outcome)


@pytest.mark.parametrize("given", ["corpus/a.md", "./corpus/a.md", "corpus/../corpus/a.md"])
async def test_a_relative_path_deletes_the_source_recorded_under_its_absolute_path(
    held: str, given: str
) -> None:
    # Act
    rendered = await _delete(given)

    # Assert
    assert _RecordingStore.deleted == [held]
    assert _RecordingStore.records == {}
    assert rendered.stdout is not None
    assert "pgvector (weft-store): 3 node(s) removed" in rendered.stdout
    assert "nothing held" not in rendered.stdout
    assert rendered.exit_code is ExitCode.SUCCESS


async def test_a_relative_path_nothing_holds_still_says_so_and_succeeds(held: str) -> None:
    # Act
    rendered = await _delete("corpus/typo.md")

    # Assert
    assert rendered.stdout is not None
    assert "nothing held 'corpus/typo.md'" in rendered.stdout
    assert rendered.exit_code is ExitCode.SUCCESS
    assert set(_RecordingStore.records) == {held}
