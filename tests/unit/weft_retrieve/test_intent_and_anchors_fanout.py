"""Ledger task **39.2** — the fan-out and the absence, through the stages a query path really runs.

`intent-and-anchors` labels queries; `hybrid` honours the labels; fusion keeps the labels of the
lists it merged; the packer hands them to whoever scores the passages. The property G24 asks for
is at the far end of that chain — **a record says which branch a question took** — so the test
drives the real stages rather than asserting on the transform alone: one text search per anchor,
each ranking kept whole beside the dense ranking of the unrewritten question, and a question with
no anchor producing **no** text list at all, visible as an absent `hybrid:text` contributor.
"""

from __future__ import annotations

from collections.abc import Sequence

from weft_embed.contract import Embedder
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, Outcome, Produced, Vector
from weft_retrieve.fusion import NormalizedScoreFusion
from weft_retrieve.hybrid import Hybrid
from weft_retrieve.intent_and_anchors import IntentAndAnchors
from weft_retrieve.payload import Candidates, Channel, Passages, Query, QuerySet, Ranking
from weft_retrieve.repack import Repack
from weft_store.contract import Filter, NodeStore, Scored


class _StubEmbedder:
    """`test_hybrid.py`'s own double: a vector deterministic on the text's length."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(
            value=[
                node.with_embedding(Vector(values=(float(len(node.content)), 1.0)))
                for node in payload
            ]
        )


class _BothArmsStore:
    """Records each text query it is asked, so a test can count the anchor fan-out per arm.

    `test_hybrid.py`'s own double, answering each text search with a hit named after what
    it was asked, so a ranking can be traced back to the anchor that produced it.
    """

    def __init__(self) -> None:
        self.vector_calls = 0
        self.text_calls: list[str] = []

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        self.vector_calls += 1
        return (_hit("dense-a", 0.91), _hit("dense-b", 0.44))

    async def search_text(
        self, text: str, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del top_k, filter
        self.text_calls.append(text)
        return (_hit(f"lexical-{text}-a", 7.2), _hit(f"lexical-{text}-b", 3.1))


def _hit(content: str, score: float) -> Scored[Node]:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Scored(value=node, score=score)


def _ctx(store: _BothArmsStore) -> Context:
    services = ServiceRegistry()
    services.add(NodeStore, store)
    services.add(Embedder, _StubEmbedder())
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


async def _retrieve(text: str, store: _BothArmsStore) -> Candidates:
    ctx = _ctx(store)
    asked = Query(text=text)
    labelled = await IntentAndAnchors().run(QuerySet(origin=asked, queries=(asked,)), ctx)
    assert isinstance(labelled, Produced)
    retrieved = await Hybrid().run(labelled.value, ctx)
    assert isinstance(retrieved, Produced)
    return retrieved.value


async def _packed(candidates: Candidates, store: _BothArmsStore) -> Passages:
    ctx = _ctx(store)
    fused = await NormalizedScoreFusion().run(candidates, ctx)
    assert isinstance(fused, Produced)
    assert isinstance(fused.value, Ranking)
    packed = await Repack().run(fused.value, ctx)
    assert isinstance(packed, Produced)
    return packed.value


async def test_each_anchor_is_one_text_search_and_the_intent_is_one_dense_search() -> None:
    # Arrange
    store = _BothArmsStore()
    question = "What is the difference between the controller WRH123 and STX58"

    # Act
    candidates = await _retrieve(question, store)

    # Assert
    assert store.text_calls == ["WRH123", "STX58"]
    assert store.vector_calls == 1
    dense = [ranked for ranked in candidates.lists if ranked.channel == Channel.VECTOR.value]
    lexical = [ranked for ranked in candidates.lists if ranked.channel == Channel.TEXT.value]
    assert [ranked.query.text for ranked in dense] == [question]
    assert [ranked.query.text for ranked in lexical] == ["WRH123", "STX58"]


async def test_each_anchors_ranking_arrives_whole_rather_than_merged_with_another() -> None:
    # Arrange
    store = _BothArmsStore()

    # Act
    candidates = await _retrieve("compare WRH123 with STX58", store)

    # Assert
    lexical = {
        ranked.query.text: [hit.node.content for hit in ranked.hits]
        for ranked in candidates.lists
        if ranked.channel == Channel.TEXT.value
    }
    assert lexical == {
        "WRH123": ["lexical-WRH123-a", "lexical-WRH123-b"],
        "STX58": ["lexical-STX58-a", "lexical-STX58-b"],
    }


async def test_a_question_with_no_anchor_produces_no_text_list_at_all() -> None:
    # Arrange
    store = _BothArmsStore()

    # Act
    candidates = await _retrieve("I am looking for the best controller for underwater RC", store)

    # Assert
    assert store.text_calls == []
    assert all(ranked.channel != Channel.TEXT.value for ranked in candidates.lists)
    assert len(candidates.lists) == 1


async def test_the_packed_passages_say_which_arms_answered_an_anchored_question() -> None:
    # Arrange
    store = _BothArmsStore()
    candidates = await _retrieve("compare WRH123 with STX58", store)

    # Act
    passages = await _packed(candidates, store)

    # Assert
    assert set(passages.contributors) == {"hybrid:vector", "hybrid:text"}


async def test_the_packed_passages_of_a_question_with_no_anchor_name_no_text_arm() -> None:
    # Arrange
    store = _BothArmsStore()
    candidates = await _retrieve("the best controller for underwater RC", store)

    # Act
    passages = await _packed(candidates, store)

    # Assert
    assert tuple(passages.contributors) == ("hybrid:vector",)
