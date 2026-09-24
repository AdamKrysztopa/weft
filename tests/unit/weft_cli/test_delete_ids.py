"""Carried repair R43.17: `weft delete` takes the handle `weft sources list` prints.

Carried repair **R43.17** — `weft delete` takes the handle `weft sources list` prints, and says
so when nothing held the one it was given.

`weft sources list` prints each record's `uri`; `weft delete` took only the record's `id`. Handed
the uri it had just been shown, it answered `0 node(s) removed` at exit 0 with the source still
there, reading exactly like a delete that worked. A uri a record carries now resolves to that
record's id. An id nothing holds still exits 0 — deletion is idempotent, and a resumed fan-out
depends on re-running a finished delete succeeding — but the answer says nothing held it.
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

_PATH = "/corpus/a.txt"
_URI = "file:///corpus/a.txt"


class _RecordingStore:
    """A store holding one source, recorded under its path with a `file://` uri."""

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


@pytest.fixture(autouse=True)
def one_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    record = SourceRecord(
        id=SourceId(_PATH),
        uri=_URI,
        content_hash="hash-a",
        indexed_at=datetime(2026, 9, 23, tzinfo=UTC),
        pipeline="built-in",
        status=SourceStatus.ACTIVE,
    )
    monkeypatch.setattr(_RecordingStore, "records", {_PATH: record})
    monkeypatch.setattr(_RecordingStore, "deleted", [])


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


async def test_the_uri_sources_list_prints_deletes_its_source() -> None:
    # Act
    rendered = await _delete(_URI)

    # Assert
    assert _RecordingStore.deleted == [_PATH]
    assert _RecordingStore.records == {}
    assert rendered.stdout is not None
    assert "pgvector (weft-store): 3 node(s) removed" in rendered.stdout
    assert rendered.exit_code is ExitCode.SUCCESS


async def test_an_id_nothing_holds_says_so_and_still_succeeds() -> None:
    # Act
    rendered = await _delete("/corpus/typo.txt")

    # Assert
    assert rendered.stdout is not None
    assert "nothing held '/corpus/typo.txt'" in rendered.stdout
    assert "weft sources list" in rendered.stdout
    assert rendered.exit_code is ExitCode.SUCCESS
    assert _RecordingStore.records != {}


async def test_a_held_id_is_deleted_without_the_nothing_held_line() -> None:
    # Act
    rendered = await _delete(_PATH)

    # Assert
    assert _RecordingStore.deleted == [_PATH]
    assert rendered.stdout is not None
    assert "nothing held" not in rendered.stdout
