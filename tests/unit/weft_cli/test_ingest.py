"""Unit tests for `weft_cli.ingest`.

Mirrors `packages/weft-cli/src/weft_cli/ingest.py`. `run_index` is exercised
against **fake** stand-ins for the four built-ins — the same composition
`tests/integration/test_ingest_pipeline.py` proves against the real container
— so this tier covers `run_index`'s own logic (batching one directory's worth
of documents, reading `stored_count` back, closing every resolved stage that
has an `aclose`) without needing Postgres. `INDEX_SPECS`'s exact shape is
covered directly: it is the one constant `docs/06-phase-0-build.md` step 9
fixes as Phase 0's built-in pipeline, and a silent reorder of it would be the
kind of drift this test exists to catch.
"""

from collections.abc import Sequence
from pathlib import Path

from weft_chunk import Chunker
from weft_cli.ingest import INDEX_DISTRIBUTIONS, INDEX_SPECS, run_index
from weft_embed import Embedder
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry
from weft_store import NodeStore


class _PassThroughStage:
    """Satisfies `Extractor`/`Chunker`/`Embedder`'s `run` by passing its input straight through."""

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="nothing to pass through")
        return Produced(value=payload)


class _FakeStore:
    """A minimal `NodeStore` double — `run`/`add`/`flush`/`count`, nothing else this test needs."""

    def __init__(self, config: object) -> None:
        del config
        self.added: list[Node] = []
        self.closed = False

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        self.added.extend(nodes)

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return len(self.added)

    async def aclose(self) -> None:
        self.closed = True


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _registry_with_fakes() -> tuple[Registry, _FakeStore]:
    registry = Registry()
    registry.add(Extractor, "text", _PassThroughStage, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _PassThroughStage, distribution="weft-chunk")
    registry.add(Embedder, "hash", _PassThroughStage, distribution="weft-embed")
    store = _FakeStore(None)

    def _store_factory(config: object) -> _FakeStore:
        del config
        return store

    registry.add(NodeStore, "pgvector", _store_factory, distribution="weft-store")
    return registry, store


def test_index_specs_is_the_fixed_extract_chunk_embed_store_pipeline() -> None:
    # Arrange / Act
    shape = tuple((spec.id, spec.contract, spec.name) for spec in INDEX_SPECS)

    # Assert
    assert shape == (
        ("extract", Extractor, "text"),
        ("chunk", Chunker, "fixed-size"),
        ("embed", Embedder, "hash"),
        ("store", NodeStore, "pgvector"),
    )
    assert INDEX_DISTRIBUTIONS == ("weft-extract", "weft-chunk", "weft-embed", "weft-store")


async def test_run_index_stores_every_document_and_reports_the_stored_count(
    tmp_path: Path,
) -> None:
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    registry, store = _registry_with_fakes()

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_ctx())

    # Assert
    assert result.summary.produced == 1
    assert result.stored_count == 1
    assert store.closed is True


async def test_run_index_on_an_empty_directory_reports_nothing_to_produce(tmp_path: Path) -> None:
    # Arrange — no files written under tmp_path.
    registry, store = _registry_with_fakes()

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_ctx())

    # Assert
    assert result.summary.nothing_to_produce == 1
    assert result.summary.produced == 0
    assert store.closed is True
