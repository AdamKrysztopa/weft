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

**Task 4.0's own tests are the `pipeline=` ones**, at the bottom of this file: a document's
own `with:` block reaching a stage (the whole point — `weft_cli.ingest`'s module docstring
carries the argument), a document with no `Extractor`-contract stage refusing by name
(`PipelineMissingExtractStageError`), and a name the catalogue does not hold refusing by
name (`weft_cli.pipeline_catalogue.UnknownPipelineNameError`, reused rather than
duplicated). `weft_cli.pipeline_catalogue.full_catalogue` is stubbed rather than pointed at
a real `pipelines/` directory — that lookup's own logic is `test_pipeline_catalogue.py`'s,
not this file's.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from weft_chunk import Chunker
from weft_cli import ingest as ingest_module
from weft_cli.ingest import (
    INDEX_DISTRIBUTIONS,
    AmbiguousExtractorError,
    PipelineMissingExtractStageError,
    UnclaimedFormatError,
    index_specs,
    run_index,
)
from weft_cli.pipeline_catalogue import UnknownPipelineNameError
from weft_embed import Embedder
from weft_enhance.contract import Enhancer
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced
from weft_kernel.pipeline import Pipeline, SlotDeclaration, StageDeclaration
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.resolution import Contribution
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


# --- task 4.0: `pipeline=` resolves a document, reaching a stage's own `with:` -------------


class _EmbedderConfig(BaseModel):
    """A stub `with:` block — the fact this whole task exists to make reachable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = "default"


def _configured_embedder(built: list[_EmbedderConfig]) -> type:
    """A fresh `Embedder` class that records every `config` it was built with, in `built`."""

    class _ConfiguredEmbedder:
        config_model: type[_EmbedderConfig] = _EmbedderConfig

        def __init__(self, config: _EmbedderConfig | None = None) -> None:
            self.config = config or _EmbedderConfig()
            built.append(self.config)

        async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
            del ctx
            return Produced(value=payload)

    return _ConfiguredEmbedder


def _document(name: str, *stages: StageDeclaration) -> Pipeline:
    return Pipeline(name=name, stages=stages)


def _stub_catalogue(
    catalogue: dict[str, Pipeline],
) -> Callable[..., dict[str, Pipeline]]:
    """A typed stand-in for `weft_cli.pipeline_catalogue.full_catalogue`, so `monkeypatch.
    setattr` has a real signature to check rather than a bare lambda `pyright` cannot type.
    """

    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return catalogue

    return _full_catalogue


async def test_run_index_with_pipeline_resolves_a_document_and_reaches_its_with_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the exit demonstration's own claim, at unit scale: a document names its own
    # plugin per stage, and that stage's `with:` block is what actually built the instance —
    # never `[services] embed`, which this call never even passes.
    (tmp_path / "one.txt").write_text("hello weft")
    registry, store = _registry_with_fakes()
    built: list[_EmbedderConfig] = []
    registry.add(Embedder, "model", _configured_embedder(built), distribution="acme-embed")
    document = _document(
        "custom",
        StageDeclaration(id="extract", use="text"),
        StageDeclaration(id="chunk", use="fixed-size"),
        StageDeclaration(id="embed", use="model", config={"model": "big"}),
        StageDeclaration(id="store", use="pgvector"),
    )
    monkeypatch.setattr(ingest_module, "full_catalogue", _stub_catalogue({"custom": document}))

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_ctx(), pipeline="custom")

    # Assert
    assert result.summary.produced == 1
    assert result.stored_count == 1
    assert store.closed is True
    assert built == [_EmbedderConfig(model="big")]
    # Task 4.6: `resolved_pipeline`/`document_ids` — a run record's own two needs, carried
    # back rather than discarded (`IndexResult`'s own docstring).
    assert result.resolved_pipeline is not None
    assert result.resolved_pipeline.name == "custom"
    assert result.document_ids == (str((tmp_path / "one.txt").resolve()),)


async def test_run_index_with_pipeline_runs_a_contribution_placed_in_its_declared_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task **5.3a** (`S8`) end to end: a document declares a slot, a pack's own
    `Contribution` names it, and the contributed stage actually runs — never merely
    resolves. `contributions=` reaches `run_index` through `_specs_from_document`'s own
    `contracts_for`/`resolve` calls, exactly the seam `weft_cli.registry_bootstrap.
    Dependencies.contributions` feeds every real caller.
    """
    # Arrange — an `Enhancer` slots in cleanly between `chunk` and `embed`: all three
    # contracts declare `Stage[Sequence[Node], Sequence[Node]]` (see `weft_enhance.contract`'s
    # own docstring), so composition holds with no bespoke payload type for this test.
    (tmp_path / "one.txt").write_text("hello weft")
    registry, store = _registry_with_fakes()
    ran: list[str] = []

    class _Enrich:
        def __init__(self, config: object = None) -> None:
            del config

        async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
            del ctx
            ran.append("enrich")
            return Produced(value=payload)

    registry.add(Enhancer, "wordcount", _Enrich, distribution="weft-graph")
    document = Pipeline(
        name="custom",
        stages=(
            StageDeclaration(id="extract", use="text"),
            StageDeclaration(id="chunk", use="fixed-size"),
            StageDeclaration(id="embed", use="hash"),
            StageDeclaration(id="store", use="pgvector"),
        ),
        slots=(SlotDeclaration(id="enrich", after="chunk"),),
    )
    monkeypatch.setattr(ingest_module, "full_catalogue", _stub_catalogue({"custom": document}))
    contribution = Contribution(
        slot="enrich",
        distribution="weft-graph",
        stage=StageDeclaration(id="wordcount", use="wordcount"),
    )

    # Act
    result = await run_index(
        tmp_path,
        registry=registry,
        ctx=_ctx(),
        pipeline="custom",
        contributions=(contribution,),
    )

    # Assert
    assert result.resolved_pipeline is not None
    assert [stage.id for stage in result.resolved_pipeline.stages] == [
        "extract",
        "chunk",
        "weft-graph:wordcount",
        "embed",
        "store",
    ]
    assert result.resolved_pipeline.unplaced_contributions == ()
    assert ran == ["enrich"]
    assert store.closed is True


async def test_a_document_with_no_extract_stage_refuses_naming_the_stages_it_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a document that could never say what to read from disk: no stage in it is
    # registered under the `Extractor` contract at all.
    (tmp_path / "one.txt").write_text("hello weft")
    registry, _ = _registry_with_fakes()
    document = _document(
        "no-extract",
        StageDeclaration(id="chunk", use="fixed-size"),
        StageDeclaration(id="embed", use="hash"),
        StageDeclaration(id="store", use="pgvector"),
    )
    monkeypatch.setattr(ingest_module, "full_catalogue", _stub_catalogue({"no-extract": document}))

    # Act / Assert
    with pytest.raises(PipelineMissingExtractStageError) as excinfo:
        await run_index(tmp_path, registry=registry, ctx=_ctx(), pipeline="no-extract")

    assert excinfo.value.valid_options == ("chunk", "embed", "store")
    assert "no-extract" in str(excinfo.value)


async def test_an_unknown_pipeline_name_fails_loudly_listing_the_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the catalogue this run resolved against is real, and simply does not hold
    # the name given; `weft_cli.pipeline_catalogue`'s own refusal is reused, not duplicated.
    (tmp_path / "one.txt").write_text("hello weft")
    registry, _ = _registry_with_fakes()
    document = _document("known", StageDeclaration(id="extract", use="text"))
    monkeypatch.setattr(ingest_module, "full_catalogue", _stub_catalogue({"known": document}))

    # Act / Assert
    with pytest.raises(UnknownPipelineNameError) as excinfo:
        await run_index(tmp_path, registry=registry, ctx=_ctx(), pipeline="missing")

    assert excinfo.value.valid_options == ("known",)


async def test_pipeline_and_extractor_together_are_refused_rather_than_one_winning(
    tmp_path: Path,
) -> None:
    # Arrange — a document's own `extract` stage already names a plugin, so `--extract`
    # would have nothing left to narrow; giving both is refused rather than one silently
    # taking precedence over the other (CLAUDE.md: "a silent fallback is worse than a
    # failure"). `weft_cli.commands.IndexCommand` refuses this earlier, at the CLI surface —
    # this proves `run_index` itself does not depend on that caller to be safe.
    registry, _ = _registry_with_fakes()

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await run_index(
            tmp_path, registry=registry, ctx=_ctx(), extractor="text", pipeline="custom"
        )

    message = str(excinfo.value)
    assert "pipeline" in message
    assert "extractor" in message
