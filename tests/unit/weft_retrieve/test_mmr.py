"""Unit tests for `weft_retrieve.mmr` — ledger task **32.5**.

Carbonell & Goldstein, SIGIR '98: select greedily the passage maximising
`λ·Sim1(passage, query) − (1−λ)·max Sim2(passage, already selected)`. `Sim1` is the cosine
between the question's embedding — one call to the index's own embedder — and a hit's stored
vector; `Sim2` is the cosine between stored vectors. The incoming score is not `Sim1`: a fused
or reranked score is on another scale, so the relevance term is recomputed from vectors.

Vectors below are chosen so each expected order can be checked by hand; the arithmetic sits
beside the assertion that depends on it.
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_embed.contract import Embedder
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, Outcome, Produced, Vector
from weft_retrieve.contract import Reranker
from weft_retrieve.mmr import NAME, Mmr, MmrConfig
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store.contract import Scored

_QUERY_VECTOR = (1.0, 0.0)


class _CountingEmbedder:
    """Embeds every text as `_QUERY_VECTOR` and counts how many batches it was asked for."""

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        self.calls += 1
        return Produced(
            value=[node.with_embedding(Vector(values=_QUERY_VECTOR)) for node in payload]
        )


def _ctx(embedder: _CountingEmbedder) -> Context:
    services = ServiceRegistry()
    services.add(Embedder, embedder)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _hit(content: str, vector: tuple[float, float] | None, *, score: float, rank: int) -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="mmr fixture")
    if vector is not None:
        node = node.with_embedding(Vector(values=vector))
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by="vector-top-k")


def _ranking(*hits: Passage) -> Ranking:
    return Ranking(origin=Query(text="which passages?"), hits=hits)


async def _run(ranking: Ranking, config: MmrConfig, embedder: _CountingEmbedder) -> Ranking:
    outcome = await Mmr(config).run(ranking, _ctx(embedder))
    assert isinstance(outcome, Produced)
    return outcome.value


def test_it_is_selectable_by_its_literature_name_and_is_a_reranker() -> None:
    # Act / Assert
    assert NAME == "mmr"
    assert isinstance(Mmr(MmrConfig()), Reranker)


def test_relevance_weight_defaults_to_the_papers_recommended_seven_tenths() -> None:
    # Act / Assert — p. 335: "a larger value of λ (e.g. λ = .7)".
    assert MmrConfig().relevance_weight == 0.7


@pytest.mark.parametrize("weight", [-0.1, 1.1])
def test_a_relevance_weight_outside_zero_to_one_is_refused(weight: float) -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        MmrConfig(relevance_weight=weight)


async def test_an_exact_duplicate_yields_its_slot_to_a_different_passage() -> None:
    # Arrange — q = (1,0). A = B = (0.8, 0.6): Sim1 0.8 each. C = (0.8, -0.6): Sim1 0.8,
    # Sim2(A, C) = 0.64 - 0.36 = 0.28. At λ = 0.5, A is taken first (tied with B on 0.4,
    # earlier incoming rank wins); then C scores 0.4 - 0.5·0.28 = 0.26 and B scores
    # 0.4 - 0.5·1.0 = -0.1, so C comes second and the duplicate last.
    a = _hit("A", (0.8, 0.6), score=0.9, rank=0)
    b = _hit("B, a copy of A", (0.8, 0.6), score=0.9, rank=1)
    c = _hit("C", (0.8, -0.6), score=0.5, rank=2)

    # Act
    reranked = await _run(_ranking(a, b, c), MmrConfig(relevance_weight=0.5), _CountingEmbedder())

    # Assert
    assert [hit.node.content for hit in reranked.hits] == ["A", "C", "B, a copy of A"]
    assert [hit.rank for hit in reranked.hits] == [0, 1, 2]


async def test_at_full_relevance_weight_the_order_is_by_cosine_to_the_question_not_the_score() -> (
    None
):
    # Arrange — incoming scores rank X first; cosine to q = (1,0) ranks Y (1.0) above X (0.6).
    x = _hit("X", (0.6, 0.8), score=0.99, rank=0)
    y = _hit("Y", (1.0, 0.0), score=0.10, rank=1)

    # Act
    reranked = await _run(_ranking(x, y), MmrConfig(relevance_weight=1.0), _CountingEmbedder())

    # Assert
    assert [hit.node.content for hit in reranked.hits] == ["Y", "X"]


async def test_each_emitted_score_is_the_mmr_value_it_was_selected_with() -> None:
    # Arrange — same fixture as the duplicate test: selected values 0.4, 0.26, -0.1.
    a = _hit("A", (0.8, 0.6), score=0.9, rank=0)
    b = _hit("B", (0.8, 0.6), score=0.9, rank=1)
    c = _hit("C", (0.8, -0.6), score=0.5, rank=2)

    # Act
    reranked = await _run(_ranking(a, b, c), MmrConfig(relevance_weight=0.5), _CountingEmbedder())

    # Assert
    assert [hit.score for hit in reranked.hits] == pytest.approx([0.4, 0.26, -0.1])
    assert "mmr" in Mmr.score_semantics.lower()


async def test_top_n_keeps_only_the_first_n_selections() -> None:
    # Arrange
    a = _hit("A", (0.8, 0.6), score=0.9, rank=0)
    b = _hit("B", (0.8, 0.6), score=0.9, rank=1)
    c = _hit("C", (0.8, -0.6), score=0.5, rank=2)

    # Act
    reranked = await _run(
        _ranking(a, b, c), MmrConfig(relevance_weight=0.5, top_n=2), _CountingEmbedder()
    )

    # Assert
    assert [hit.node.content for hit in reranked.hits] == ["A", "C"]


async def test_the_question_is_embedded_exactly_once_whatever_the_number_of_hits() -> None:
    # Arrange
    embedder = _CountingEmbedder()
    hits = [_hit(f"H{i}", (1.0, float(i)), score=1.0, rank=i) for i in range(5)]

    # Act
    await _run(_ranking(*hits), MmrConfig(), embedder)

    # Assert
    assert embedder.calls == 1


async def test_a_hit_that_arrives_without_a_vector_is_refused_by_name_never_scored_as_zero() -> (
    None
):
    # Arrange
    a = _hit("A", (1.0, 0.0), score=0.9, rank=0)
    bare = _hit("no vector here", None, score=0.8, rank=1)

    # Act
    outcome = await Mmr(MmrConfig()).run(_ranking(a, bare), _ctx(_CountingEmbedder()))

    # Assert
    assert isinstance(outcome, Failed)
    assert "mmr" in outcome.reason
    assert bare.node.id in outcome.reason


async def test_an_empty_ranking_passes_through_and_embeds_nothing() -> None:
    # Arrange
    embedder = _CountingEmbedder()
    empty = Ranking(origin=Query(text="nothing found"), contributors=("hybrid:vector",))

    # Act
    reranked = await _run(empty, MmrConfig(), embedder)

    # Assert
    assert reranked.hits == ()
    assert reranked.contributors == ("hybrid:vector",)
    assert embedder.calls == 0
