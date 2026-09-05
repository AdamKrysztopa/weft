"""Unit tests for `weft_retrieve.hybrid` — ledger task **8.6**.

Mirrors `packages/weft-rag/src/weft_retrieve/hybrid.py`. The assertions that carry the weight
are the two the plugin's own docstring makes claims about: **both arms are searched from one
query**, and **the arms stay labelled apart** so a `Fuser` can weight them without a branch
asking which kind of multiplicity it was handed. The fusing itself is
`test_fusion.py`'s — this file proves the two lists arrive fusable, not that fusion works.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_embed.contract import Embedder
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, Outcome, Produced, Vector
from weft_retrieve.fusion import contributor_label
from weft_retrieve.hybrid import NAME, Hybrid, HybridConfig
from weft_retrieve.payload import Candidates, Channel, Query, QuerySet
from weft_store.contract import Filter, FilterOp, NodeStore, Scored


class _StubEmbedder:
    """A vector deterministic on the query's own text length — `test_vector_top_k.py`'s own
    double, restated rather than imported across test modules on this suite's "one
    self-contained scenario" convention."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(
            value=[
                node.with_embedding(Vector(values=(float(len(node.content)), 1.0)))
                for node in payload
            ]
        )


class _BothArmsStore:
    """A store satisfying `VectorSearch` **and** `TextSearch`, recording what each was asked.

    Two canned answers with **no node in common**, on purpose: the assertion that both arms
    ran is then about which content came back, not about a call count a single-arm plugin
    could also produce by being called twice.
    """

    def __init__(self) -> None:
        self.vector_calls: list[tuple[Vector, int, Filter | None]] = []
        self.text_calls: list[tuple[str, int, Filter | None]] = []

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        self.vector_calls.append((vector, top_k, filter))
        return (_hit("dense-a", 0.91), _hit("dense-b", 0.44))

    async def search_text(
        self, text: str, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        self.text_calls.append((text, top_k, filter))
        return (_hit("lexical-a", 7.2),)


class _VectorOnlyStore:
    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        return ()


def _hit(content: str, score: float) -> Scored[Node]:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Scored(value=node, score=score)


def _ctx(store: object) -> Context:
    services = ServiceRegistry()
    services.add(NodeStore, store)
    services.add(Embedder, _StubEmbedder())
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _query_set(text: str = "what is reciprocal rank fusion") -> QuerySet:
    query = Query(text=text)
    return QuerySet(origin=query, queries=(query,))


async def test_one_query_searches_both_arms_and_returns_both_rankings() -> None:
    """The headline claim: several bases at once, from one store, in one stage."""
    # Arrange
    store = _BothArmsStore()

    # Act
    outcome = await Hybrid().run(_query_set(), _ctx(store))

    # Assert
    assert isinstance(outcome, Produced)
    candidates = outcome.value
    assert isinstance(candidates, Candidates)
    assert len(candidates.lists) == 2
    contents = {hit.scored.value.content for ranked in candidates.lists for hit in ranked.hits}
    assert contents == {"dense-a", "dense-b", "lexical-a"}
    # The lexical arm is asked for words, never for an embedding of them.
    assert store.text_calls[0][0] == "what is reciprocal rank fusion"


async def test_the_two_arms_are_labelled_apart_so_a_fuser_can_weight_them() -> None:
    """Without distinct labels the `weights` mapping has no key to type, which is the whole
    reason `RankedList.channel` exists — `vector_top_k.VectorTopKConfig.arm`'s own docstring.
    """
    # Arrange / Act
    outcome = await Hybrid().run(_query_set(), _ctx(_BothArmsStore()))

    # Assert
    assert isinstance(outcome, Produced)
    labels = {contributor_label(ranked) for ranked in outcome.value.lists}
    assert labels == {f"{NAME}:vector", f"{NAME}:text"}


async def test_the_arm_labels_are_configurable_so_two_narrowings_can_be_told_apart() -> None:
    # Arrange
    config = HybridConfig(vector_arm="dense-leaves", text_arm="bm25-leaves")

    # Act
    outcome = await Hybrid(config).run(_query_set(), _ctx(_BothArmsStore()))

    # Assert
    assert isinstance(outcome, Produced)
    labels = {contributor_label(ranked) for ranked in outcome.value.lists}
    assert labels == {f"{NAME}:dense-leaves", f"{NAME}:bm25-leaves"}


async def test_one_filter_narrows_both_arms_and_is_combined_with_the_querys_own() -> None:
    """`combined_filter`'s contract, reused rather than reimplemented — a document's filter
    narrows, it never replaces what the query already asked for."""
    # Arrange
    store = _BothArmsStore()
    per_arm = Filter(op=FilterOp.EQ, field="ext.weft-index.technique", value="raptor")
    per_query = Filter(op=FilterOp.EQ, field="lang", value="en")
    query = Query(text="broad question", filter=per_query)

    # Act
    await Hybrid(HybridConfig(filter=per_arm)).run(
        QuerySet(origin=query, queries=(query,)), _ctx(store)
    )

    # Assert — both arms saw the same combined narrowing, neither saw a bare one.
    assert store.vector_calls[0][2] == store.text_calls[0][2]
    combined = store.vector_calls[0][2]
    assert combined is not None
    assert combined.op is FilterOp.AND


async def test_narrowing_channels_to_one_arm_searches_only_that_arm() -> None:
    """So a document can A/B a single arm against the pair without swapping the plugin."""
    # Arrange
    store = _BothArmsStore()

    # Act
    outcome = await Hybrid(HybridConfig(channels=(Channel.TEXT,))).run(_query_set(), _ctx(store))

    # Assert
    assert isinstance(outcome, Produced)
    assert [ranked.channel for ranked in outcome.value.lists] == ["text"]
    assert store.vector_calls == []


async def test_a_store_that_cannot_do_lexical_search_fails_loudly_naming_the_capability() -> None:
    """Requirement 5. Nothing adapts and nothing degrades: a run that wanted a text channel
    does not quietly become vector-only — `weft_store.contract.TextSearch`'s own promise."""
    # Arrange / Act
    outcome = await Hybrid().run(_query_set(), _ctx(_VectorOnlyStore()))

    # Assert
    assert isinstance(outcome, Failed)
    assert "TextSearch" in outcome.reason
    assert "vector-top-k" in outcome.reason


def test_needs_store_declares_both_capabilities_whatever_channels_says() -> None:
    """The declaration is read before any stage runs, by `check_store_capabilities`, so it has
    to describe what this plugin may call under *its own* config surface — not under the one
    configuration it happens to hold. Deriving it from `channels` would let `[vector]` resolve
    against a store with no `TextSearch` and move the refusal to a later `with:` edit."""
    # Arrange / Act
    declared = {capability.__name__ for capability in Hybrid.needs_store}

    # Assert
    assert declared == {"VectorSearch", "TextSearch"}


def test_no_channels_at_all_is_refused_rather_than_retrieving_nothing() -> None:
    """An empty tuple is a valid tuple and a meaningless retrieval — every query produces no
    list and the answer is "no evidence" from a run that never looked."""
    # Arrange / Act / Assert
    with pytest.raises(ValidationError) as raised:
        HybridConfig(channels=())
    assert "no channels at all" in str(raised.value)


def test_an_unknown_channel_name_is_refused_at_the_field() -> None:
    # Arrange / Act / Assert — pydantic's own, at the typo, naming the two members.
    with pytest.raises(ValidationError):
        HybridConfig.model_validate({"channels": ["vectr"]})
