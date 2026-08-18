"""Unit tests for `weft_cli.ask`.

Mirrors `packages/weft-cli/src/weft_cli/ask.py`. `run_ask` is exercised
against **fake** stand-ins for `weft-embed`'s `hash` plugin and `weft-store`'s
`pgvector` store — the real question-embedding-then-search path is
`tests/integration/test_cli_end_to_end.py`'s job, against the real container;
this tier covers `run_ask`'s own logic: the question becomes a synthetic
node, the embedder runs through `weft_kernel.seam.wrap`, a store that does
not satisfy `VectorSearch` is refused loudly, and an embedder that fails is
never silently treated as "no results".
"""

from collections.abc import Sequence

import pytest

from weft_cli.ask import EmbeddingFailedError, NotVectorSearchableError, render_results, run_ask
from weft_embed import Embedder
from weft_kernel.context import Context
from weft_kernel.payload import Failed, MediaType, Node, Outcome, Produced, Vector
from weft_kernel.registry import Registry
from weft_store import Filter, NodeStore, Scored


class _FakeEmbedder:
    """Sets a fixed one-component embedding on every node it is handed."""

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=[node.with_embedding(Vector(values=(1.0,))) for node in payload])


class _FailingEmbedder:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del payload, ctx
        return Failed(reason="the fake embedder always fails")


class _FakeVectorSearchStore:
    """Satisfies `NodeStore` + `VectorSearch` structurally: `run` is unused by `run_ask`."""

    def __init__(self, config: object) -> None:
        del config
        self.closed = False
        self.searched_with: tuple[Vector, int] | None = None

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del filter
        self.searched_with = (vector, top_k)
        found = Node.synthetic(
            content="a stored passage", media_type=MediaType.TEXT, reason="fixture"
        )
        return [Scored(value=found, score=0.9)]

    async def aclose(self) -> None:
        self.closed = True


class _FakeStoreWithoutVectorSearch:
    """A `NodeStore` that never implements `search_vector` — capability derivation must refuse."""

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_run_ask_embeds_the_question_and_returns_the_stores_results() -> None:
    # Arrange
    registry = Registry()
    registry.add(Embedder, "hash", _FakeEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _FakeVectorSearchStore, distribution="weft-store")

    # Act
    results = await run_ask("what changed?", registry=registry, ctx=_ctx(), top_k=3)

    # Assert
    assert len(results) == 1
    assert results[0].value.content == "a stored passage"
    assert results[0].score == 0.9


async def test_run_ask_raises_when_the_embedder_fails() -> None:
    # Arrange
    registry = Registry()
    registry.add(Embedder, "hash", _FailingEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _FakeVectorSearchStore, distribution="weft-store")

    # Act / Assert
    with pytest.raises(EmbeddingFailedError, match="the fake embedder always fails"):
        await run_ask("what changed?", registry=registry, ctx=_ctx(), top_k=3)


async def test_run_ask_refuses_a_store_that_does_not_satisfy_vector_search() -> None:
    # Arrange
    registry = Registry()
    registry.add(Embedder, "hash", _FakeEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _FakeStoreWithoutVectorSearch, distribution="weft-store")

    # Act / Assert
    with pytest.raises(NotVectorSearchableError):
        await run_ask("what changed?", registry=registry, ctx=_ctx(), top_k=3)


def test_render_results_ranks_without_printing_the_raw_score() -> None:
    # Arrange — `docs/03-cli.md` -> Output, *Score display*: a negative cosine similarity is
    # correct but not reader-facing; only rank order and content reach a human.
    first = Node.synthetic(content="closest passage", media_type=MediaType.TEXT, reason="fixture")
    second = Node.synthetic(content="second passage", media_type=MediaType.TEXT, reason="fixture")
    results = [Scored(value=first, score=0.91), Scored(value=second, score=-0.09)]

    # Act
    output = render_results(results)

    # Assert
    assert output == "1. closest passage\n2. second passage"
    assert "score" not in output
    assert "-0.09" not in output


def test_render_results_reports_no_matching_passages_when_empty() -> None:
    # Arrange / Act
    output = render_results([])

    # Assert
    assert output == "no matching passages found."
