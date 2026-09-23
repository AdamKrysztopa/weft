"""Ledger task **43.18** — `weft index` claims its store before it writes, and releases it.

Drop-to-talk means a second shell, and a second `weft index` in it is a realistic mistake: two
runs would interleave their `INDEXING`/`ACTIVE` records over one corpus. A store that satisfies
`SingleWriter` is claimed by `run_index` before anything is written or deleted — naming this run's
host, pid, start time and command — and released when the run ends, however it ends. A store that
does not satisfy it is written as before.
"""

import os
import socket
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import pytest

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli.ingest import run_index
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore
from weft_store.contract import Cursor, Page, Removed, SourceRecord, WriterBusyError, WriterClaim


class _Store:
    """A store that admits one writer, recording every claim and release."""

    def __init__(self, *, held_by: WriterClaim | None = None, fail_on_add: bool = False) -> None:
        self.held_by = held_by
        self.fail_on_add = fail_on_add
        self.claims: list[WriterClaim] = []
        self.releases = 0
        self.nodes: dict[NodeId, Node] = {}
        self.records: dict[SourceId, SourceRecord] = {}
        self.adds = 0

    async def claim_writer(self, writer: WriterClaim) -> None:
        if self.held_by is not None:
            raise WriterBusyError(self.held_by)
        self.claims.append(writer)
        self.held_by = writer

    async def release_writer(self) -> None:
        self.releases += 1
        self.held_by = None

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        self.adds += 1
        if self.fail_on_add:
            raise WeftError("the database went away")
        for node in nodes:
            self.nodes[node.id] = node

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return len(self.nodes)

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self.nodes[i] for i in ids if i in self.nodes)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        return Page(items=tuple(self.nodes.values()))

    async def delete_source(self, source_id: SourceId) -> Removed:
        return Removed(source_id=source_id, node_count=0)

    async def put_source(self, record: SourceRecord) -> None:
        self.records[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return self.records.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self.records.values())


def _factory(store: _Store, config: object) -> _Store:
    del config
    return store


def _registry(store: _Store) -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_factory, store), distribution="weft-store")
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    for i in range(3):
        (tmp_path / f"doc{i}.txt").write_text(f"document number {i}.")
    return tmp_path


async def test_a_second_writer_is_refused_before_it_writes_naming_the_first(corpus: Path) -> None:
    # Arrange
    holder = WriterClaim(
        host="other-host", pid=99, started_at=datetime.now(UTC), command="weft index corpus"
    )
    store = _Store(held_by=holder)

    # Act
    with pytest.raises(WriterBusyError) as refused:
        await run_index(corpus, registry=_registry(store), ctx=_ctx())

    # Assert
    assert refused.value.holder == holder
    assert store.adds == 0
    assert store.records == {}


async def test_a_run_claims_the_store_as_this_process_and_releases_it(corpus: Path) -> None:
    # Arrange
    store = _Store()

    # Act
    await run_index(corpus, registry=_registry(store), ctx=_ctx())

    # Assert
    (claim,) = store.claims
    assert (claim.host, claim.pid, claim.command) == (
        socket.gethostname(),
        os.getpid(),
        "weft index",
    )
    assert store.releases == 1
    assert store.held_by is None


async def test_a_run_that_fails_still_releases_the_store(corpus: Path) -> None:
    # Arrange
    store = _Store(fail_on_add=True)

    # Act
    with pytest.raises(WeftError):
        await run_index(corpus, registry=_registry(store), ctx=_ctx())

    # Assert
    assert store.releases == 1
