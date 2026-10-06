"""`weft index` — carried repair **R20.1**: a write refused before storing anything claims nothing.

`weft_cli.ingest` claims the embedder's identity against the target before any vector is embedded
(ledger task 34.4), so a run that the server then refuses — Ollama answering `bge-m3` at 1024 when
`dimensions = 512` asked for 512 — used to leave the live target claiming width 512 with nothing in
it. The live target cannot be dropped, and the printed remedy, the same run without `dimensions`,
was refused for disagreeing with that claim. When the target records no identity yet, one probe is
now embedded through the run's own embedder first, so the refusal comes before the claim.

The embedder is the real `OpenAIEmbedder` over a stub client, the double `test_embedder.py` uses,
so the refusal under test is the one a real server provokes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import pytest
from openai import Omit, omit
from pydantic import SecretStr

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli import ingest as ingest_module
from weft_cli.ingest import EmbeddingProbeFailedError, run_index_for
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_kernel.context import Context
from weft_kernel.payload import Failed, Node, Outcome
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_openai import Settings
from weft_openai.embedder import EmbeddingRequestFailedError, OpenAIEmbedder
from weft_store import NodeStore
from weft_store.contract import DEFAULT_TARGET
from weft_store.memory import MemoryStore

#: What the stub server answers whatever is asked, as Ollama answers `bge-m3`.
_SERVED_WIDTH = 1024


@dataclass
class _Item:
    index: int
    embedding: Sequence[float]


@dataclass
class _Response:
    data: Sequence[_Item]
    usage: None = None


@dataclass
class _Embeddings:
    """`test_embedder.py`'s stand-in, answering one fixed width as a server that cannot shorten."""

    width: int = _SERVED_WIDTH
    inputs: list[list[str]] = field(default_factory=lambda: [])

    async def create(
        self, *, input: list[str], model: str, dimensions: int | Omit = omit
    ) -> _Response:
        del model, dimensions
        self.inputs.append(list(input))
        return _Response(
            data=[
                _Item(index=position, embedding=[float(len(text)) + position] * self.width)
                for position, text in enumerate(input)
            ]
        )


@dataclass
class _Client:
    embeddings: _Embeddings = field(default_factory=_Embeddings)

    async def close(self) -> None:
        return


def _index(name: str, *, dimensions: int | None) -> Pipeline:
    embed = (
        StageDeclaration(id="embed", use="server")
        if dimensions is None
        else StageDeclaration(id="embed", use="server", config={"dimensions": dimensions})
    )
    return Pipeline(
        name=name,
        stages=(
            StageDeclaration(id="extract", use="text"),
            StageDeclaration(id="chunk", use="fixed-size"),
            embed,
            StageDeclaration(id="store", use="memory"),
        ),
    )


def _stub_catalogue(catalogue: dict[str, Pipeline]) -> Callable[..., dict[str, Pipeline]]:
    def _full_catalogue(
        *, directory: Path = Path("pipelines"), reports: Sequence[object] = ()
    ) -> dict[str, Pipeline]:
        del directory, reports
        return catalogue

    return _full_catalogue


def _deps(store: MemoryStore, client: _Client) -> Dependencies:
    def _store_factory(config: object) -> MemoryStore:
        del config
        return store

    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(
        Embedder,
        "server",
        partial(
            OpenAIEmbedder,
            Settings(api_key=SecretStr("unused"), base_url="http://127.0.0.1:11434/v1"),
            client=client,
            account="openai-compatible",
        ),
        distribution="weft-openai",
    )
    registry.add(NodeStore, "memory", _store_factory, distribution="weft-store")
    return Dependencies(registry=registry, reports=(), services=ServiceSelection(store="memory"))


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def _claimed(store: MemoryStore) -> object:
    catalogue = await store.target_catalogue()
    return next(record.embedding for record in catalogue.targets if record.name == DEFAULT_TARGET)


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "corpus"
    directory.mkdir()
    (directory / "weft.txt").write_text("weft is the thread across the warp", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        ingest_module,
        "full_catalogue",
        _stub_catalogue(
            {
                "shortened": _index("shortened", dimensions=512),
                "native": _index("native", dimensions=None),
            }
        ),
    )
    return directory


async def test_a_refused_first_write_claims_nothing(corpus: Path) -> None:
    # Arrange
    store = MemoryStore()
    deps = _deps(store, _Client())

    # Act
    with pytest.raises(EmbeddingRequestFailedError):
        await run_index_for(deps, corpus, ctx=_ctx(), pipeline="shortened")

    # Assert
    assert await _claimed(store) is None


async def test_the_remedy_the_refusal_prints_then_indexes(corpus: Path) -> None:
    """The refusal says to remove `dimensions`; that run must not meet a claim the first left."""
    # Arrange
    store = MemoryStore()
    deps = _deps(store, _Client())
    with pytest.raises(EmbeddingRequestFailedError):
        await run_index_for(deps, corpus, ctx=_ctx(), pipeline="shortened")

    # Act
    result = await run_index_for(deps, corpus, ctx=_ctx(), pipeline="native", retry_failed=True)

    # Assert
    assert result.stored_count is not None
    assert result.stored_count > 0
    claimed = await _claimed(store)
    assert claimed is not None
    assert getattr(claimed, "width", "unset") is None


async def test_a_target_that_already_records_an_identity_is_not_probed(corpus: Path) -> None:
    """The probe is paid once, on a fresh claim; a target that records one goes straight in."""
    # Arrange
    store = MemoryStore()
    first = _Client()
    await run_index_for(_deps(store, first), corpus, ctx=_ctx(), pipeline="native")
    (corpus / "warp.txt").write_text("a warp runs lengthwise", encoding="utf-8")
    second = _Client()

    # Act
    await run_index_for(_deps(store, second), corpus, ctx=_ctx(), pipeline="native")

    # Assert
    embedded_first = [text for batch in first.embeddings.inputs for text in batch]
    embedded_second = [text for batch in second.embeddings.inputs for text in batch]
    assert len(embedded_first) == 2, "a fresh claim embeds one probe beside its one chunk"
    assert len(embedded_second) == 1, "a recorded claim embeds only the new document's chunk"


class _RefusingEmbedder:
    """States an identity and answers every batch `Failed`, as a stranger's embedder might."""

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del payload, ctx
        return Failed(reason="no model is loaded")

    async def embedding_model(self) -> object:
        from weft_embed.contract import EmbeddingModel

        return EmbeddingModel(model="refusing", width=8)


async def test_a_probe_answered_failed_stops_the_run_naming_the_reason(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    store = MemoryStore()
    deps = _deps(store, _Client())
    deps.registry.add(Embedder, "refusing", _RefusingEmbedder, distribution="test")
    pipeline = Pipeline(
        name="refusing",
        stages=(
            StageDeclaration(id="extract", use="text"),
            StageDeclaration(id="chunk", use="fixed-size"),
            StageDeclaration(id="embed", use="refusing"),
            StageDeclaration(id="store", use="memory"),
        ),
    )
    monkeypatch.setattr(ingest_module, "full_catalogue", _stub_catalogue({"refusing": pipeline}))

    # Act / Assert
    with pytest.raises(EmbeddingProbeFailedError) as raised:
        await run_index_for(deps, corpus, ctx=_ctx(), pipeline="refusing")
    assert "no model is loaded" in str(raised.value)
    assert "'default'" in str(raised.value)
    assert await _claimed(store) is None
