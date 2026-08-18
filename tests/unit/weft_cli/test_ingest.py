"""Unit tests for `weft_cli.ingest`.

Mirrors `packages/weft-cli/src/weft_cli/ingest.py`. `run_index` is exercised
against **fake** stand-ins for the four built-ins — the same composition
`tests/integration/test_ingest_pipeline.py` proves against the real container
— so this tier covers `run_index`'s own logic (deriving what to accept,
choosing which extractor runs, batching one directory's worth of documents,
reading `stored_count` back, closing every resolved stage that has an
`aclose`) without needing Postgres.

**The tests that carry the weight are the selection ones**, because that is
the defect this module was repaired for: ingest pinned `name="text"` and
filtered on one pack's `EXTENSIONS`, so a second extractor pack's format was
silently invisible and `weft index` reported success over zero documents. The
stand-in extractors below therefore declare `extensions` the way a real plugin
does, and the assertions are about what a *registered but unknown-to-this-file*
plugin makes reachable.
"""

from collections.abc import Sequence
from pathlib import Path

import pytest

from weft_chunk import Chunker
from weft_cli.ingest import (
    INDEX_DISTRIBUTIONS,
    AmbiguousExtractorError,
    UnclaimedFormatError,
    index_specs,
    run_index,
)
from weft_embed import Embedder
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry, UnknownPluginError
from weft_store import NodeStore


class _PassThroughStage:
    """Satisfies `Extractor`/`Chunker`/`Embedder`'s `run` by passing its input straight through.

    `destroys: tuple[type, ...] = ()` is here for `Chunker` alone —
    `weft_chunk.contract.Chunker.publishes_property_vocabulary` makes it
    mandatory (`02` §3 → *Ordering constraints*, task 1.2) — but declaring it
    on the one class shared across all three registrations costs the other
    two nothing; `Extractor` and `Embedder` never read it.

    `extensions` is what makes it usable as an extractor now that ingest reads
    the accept set off registered plugins rather than off a constant.
    """

    extensions: tuple[str, ...] = (".txt", ".md")
    destroys: tuple[type, ...] = ()

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="nothing to pass through")
        return Produced(value=payload)


class _PdfStage(_PassThroughStage):
    """A second extractor pack, claiming a format nothing in this file knows about."""

    extensions: tuple[str, ...] = (".pdf",)


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
    shape = tuple((spec.id, spec.contract, spec.name) for spec in index_specs("pdf-text"))

    # Assert — extract and embed are chosen at run time; chunk and store are not, and the
    # embedder defaults to the deterministic one so a run with no configuration at all needs
    # no credential.
    assert shape == (
        ("extract", Extractor, "pdf-text"),
        ("chunk", Chunker, "fixed-size"),
        ("embed", Embedder, "hash"),
        ("store", NodeStore, "pgvector"),
    )
    assert INDEX_DISTRIBUTIONS == ("weft-extract", "weft-chunk", "weft-embed")


def test_index_specs_takes_the_store_from_what_it_is_given() -> None:
    # Arrange / Act — repair for a reviewer finding against task 2.6. The store name arrives
    # from `[services] store`, so a second backend is selectable with no file in this
    # repository edited; `weft-store` left `INDEX_DISTRIBUTIONS` for the same reason
    # `--extract` and `[services] embed` are not in it — a hard-coded tuple can never
    # contain a stranger's pack, and `require_plugin` covers whichever one does provide it.
    shape = tuple(
        (spec.id, spec.contract, spec.name) for spec in index_specs("text", store="qdrant")
    )

    # Assert
    assert shape[-1] == ("store", NodeStore, "qdrant")


def test_index_specs_takes_the_embedder_from_what_it_is_given() -> None:
    # Arrange / Act — the same pipeline, resolving against a different embedder, with the
    # name arriving from `[services] embed` rather than from this module.
    shape = tuple((spec.id, spec.name) for spec in index_specs("text", embedder="openai"))

    # Assert
    assert shape == (
        ("extract", "text"),
        ("chunk", "fixed-size"),
        ("embed", "openai"),
        ("store", "pgvector"),
    )


async def test_run_index_embeds_with_the_embedder_it_was_given(tmp_path: Path) -> None:
    # Arrange — a second embedder, registered under the same contract by a distribution
    # this module knows nothing about, is reachable by name alone.
    (tmp_path / "one.txt").write_text("hello weft")
    registry, _ = _registry_with_fakes()
    ran: list[str] = []

    class _RecordingEmbedder(_PassThroughStage):
        async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
            ran.append("model")
            return await super().run(payload, ctx)

    registry.add(Embedder, "model", _RecordingEmbedder, distribution="acme-embed")

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_ctx(), embedder="model")

    # Assert
    assert result.summary.produced == 1
    assert ran == ["model"]


async def test_an_embedder_nobody_registered_fails_loudly_listing_the_options(
    tmp_path: Path,
) -> None:
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    registry, _ = _registry_with_fakes()

    # Act / Assert — requirement 5: never a silent substitution of the working embedder for
    # the one that was asked for, because an index built with the wrong one answers plausibly.
    with pytest.raises(UnknownPluginError) as raised:
        await run_index(tmp_path, registry=registry, ctx=_ctx(), embedder="typo")
    assert "hash" in str(raised.value)


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


async def test_a_format_only_a_second_pack_claims_reaches_the_pipeline(tmp_path: Path) -> None:
    # Arrange — the defect, in one test: `.pdf` is claimed by a plugin this module never
    # names, and nothing in `weft-cli` or `weft-extract` was edited to make it reachable.
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4")
    registry, store = _registry_with_fakes()
    registry.add(Extractor, "pdf-text", _PdfStage, distribution="weft-pdf")

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_ctx())

    # Assert
    assert result.summary.produced == 1
    assert result.stored_count == 1
    assert store.closed is True


async def test_two_extractors_claiming_one_format_refuse_and_name_both(tmp_path: Path) -> None:
    # Arrange — exactly `weft-pdf`'s shape: two backends for one media type, registered
    # separately because they read differently.
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4")
    registry, _ = _registry_with_fakes()
    registry.add(Extractor, "pdf-text", _PdfStage, distribution="weft-pdf")
    registry.add(Extractor, "pdf-layout", _PdfStage, distribution="weft-pdf")

    # Act / Assert
    with pytest.raises(AmbiguousExtractorError) as excinfo:
        await run_index(tmp_path, registry=registry, ctx=_ctx())

    message = str(excinfo.value)
    assert "pdf-text" in message
    assert "pdf-layout" in message
    assert "--extract" in message


async def test_naming_an_extractor_selects_it_and_narrows_what_is_discovered(
    tmp_path: Path,
) -> None:
    # Arrange — a mixed directory, and an operator who named one backend. The Markdown
    # is not handed to a PDF reader: the accept set narrows to what the named plugin
    # claims, which is the accept-then-fail bug the metadata exists to prevent.
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "notes.md").write_text("# notes")
    registry, store = _registry_with_fakes()
    registry.add(Extractor, "pdf-text", _PdfStage, distribution="weft-pdf")
    registry.add(Extractor, "pdf-layout", _PdfStage, distribution="weft-pdf")

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="pdf-text")

    # Assert — one document reached the store, not two: the Markdown was never
    # discovered, so a PDF reader was never handed bytes it would have refused.
    assert result.summary.produced == 1
    assert len(store.added) == 1
    assert ".pdf" in repr(store.added[0])


async def test_an_extractor_nobody_registered_fails_loudly_listing_the_options(
    tmp_path: Path,
) -> None:
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    registry, _ = _registry_with_fakes()

    # Act / Assert — the registry's own message, not a second, worse copy of it.
    with pytest.raises(UnknownPluginError) as excinfo:
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="ocr")

    assert "ocr" in str(excinfo.value)
    assert "text" in str(excinfo.value)


async def test_a_directory_no_installed_extractor_can_read_refuses_rather_than_succeeding(
    tmp_path: Path,
) -> None:
    # Arrange — the silent no-op, cornered: files are present and none of them is a
    # format anything installed claims.
    (tmp_path / "slides.pptx").write_bytes(b"not claimed")
    registry, _ = _registry_with_fakes()

    # Act / Assert
    with pytest.raises(UnclaimedFormatError) as excinfo:
        await run_index(tmp_path, registry=registry, ctx=_ctx())

    message = str(excinfo.value)
    assert ".pptx" in message
    assert ".txt" in message


async def test_run_index_on_an_empty_directory_reports_nothing_to_produce(tmp_path: Path) -> None:
    # Arrange — no files written under tmp_path.
    registry, store = _registry_with_fakes()

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_ctx())

    # Assert — and no pipeline is resolved at all, so no store is opened to close: there
    # is nothing whose format needs an extractor, so there is nothing to choose.
    assert result.summary.nothing_to_produce == 1
    assert result.summary.produced == 0
    assert result.stored_count is None
    assert store.closed is False
