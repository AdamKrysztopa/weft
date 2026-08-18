"""Unit tests for `weft_retrieve.vector_top_k`.

Mirrors `packages/weft-retrieve/src/weft_retrieve/vector_top_k.py`. Task **2.14**: "the
single-pass baseline is a plugin whose name states its cost, so an operator choosing what
to run in a loop is not misled by the registry." Covers the happy path (two queries, each
turned into a vector through the resolved `Embedder` service and searched through the
resolved `NodeStore`'s `search_vector`, producing one ranked list per query, in rank
order), the edge case (a query the store finds nothing for still comes back `Produced`,
carrying a `RankedList` with no hits — never `NothingToProduce`, `weft_retrieve.contract`'s
own emptiness rule restated on this plugin), the error case (a `channels` value this
retriever cannot search is refused at construction, naming `hybrid` as the plugin that
can), and drives the plugin through `weft_kernel.seam.wrap` for fitness function 7(b) —
proof the plugin was actually exercised through the one path a registered plugin is called
through in production, the same structural claim task 2.13's own seam-driving test for
`NoRetrieval` makes and no more.

**On `cost_bound` and why no call-counting double is wired in here.** A repair against
three reviewer findings removed a `_CountingProvider` this module used to construct and
wrap `weft_llm.scripted.ScriptedProvider` with: it was never registered into any run's
`ServiceRegistry`, `VectorTopK.run` never calls `ctx.require` for anything LLM-shaped, and
no `LLM` service exists anywhere in this tree yet for it to be registered under
(`weft_llm.contract.LLMProvider`'s own docstring: the service that resolves a role to a
provider "is the `LLM` service `weft-llm` will publish...one task later"). `provider.calls
== 0` was therefore true before the run ever executed, unconditionally — it did not depend
on anything `VectorTopK.run` did or did not call, and would have passed unchanged had
`run` been rewritten to call a model through any channel other than the unregistered
double. `.phase2-design.md` §10's call-counting mechanism makes sense for a technique that
resolves `LLM` a variable number of times; it has no work to do against a technique that
never resolves it at all. `test_the_declared_cost_bound_is_zero_zero` below asserts the
class attribute directly, the same honest shape `test_no_retrieval.py` already uses for
its own `(0, 0)`.
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_embed.contract import Embedder
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import ExtModel, Failed, MediaType, Node, Outcome, Produced, Vector
from weft_kernel.seam import wrap
from weft_retrieve.contract import Retriever
from weft_retrieve.payload import Candidates, Channel, Query, QuerySet, RankedList
from weft_retrieve.vector_top_k import NAME, VectorTopK, VectorTopKConfig
from weft_store.contract import NodeStore, Scored


def _ctx(services: ServiceRegistry | None = None) -> Context:
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=services if services is not None else ServiceRegistry(),
    )


class _StubEmbedder:
    """A vector deterministic on the query's own text length — enough to prove this plugin
    reaches for an embedding rather than inventing one: two different questions produce
    two different vectors, and the same question always produces the same one."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        embedded = [
            node.with_embedding(Vector(values=(float(len(node.content)), 1.0))) for node in payload
        ]
        return Produced(value=embedded)


class _StubVectorStore:
    """`search_vector`, answered from a canned table keyed by the vector's own first
    component — enough to route a fixture's canned hits back to the query that asked for
    them without this test needing a real index."""

    def __init__(self, by_key: dict[float, Sequence[Scored[Node]]]) -> None:
        self._by_key = by_key
        self.calls: list[tuple[Vector, int]] = []

    async def search_vector(
        self, vector: Vector, top_k: int, filter: object = None
    ) -> Sequence[Scored[Node]]:
        del filter
        self.calls.append((vector, top_k))
        return self._by_key.get(vector.values[0], ())


def _hit(content: str, score: float) -> Scored[Node]:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Scored(value=node, score=score)


async def test_run_searches_the_store_once_per_query_and_ranks_the_hits() -> None:
    # Arrange
    first = Query(text="why is mRMR preferred to plain relevance ranking?")
    second = Query(text="hi")
    store = _StubVectorStore(
        {
            float(len(first.text)): (_hit("a", 0.9), _hit("b", 0.5)),
            float(len(second.text)): (_hit("c", 0.7),),
        }
    )
    services = ServiceRegistry()
    services.add(NodeStore, store)
    services.add(Embedder, _StubEmbedder())
    payload = QuerySet(origin=first, queries=(first, second))
    retriever = VectorTopK(VectorTopKConfig(top_k=5))

    # Act
    outcome = await retriever.run(payload, _ctx(services))

    # Assert
    assert isinstance(outcome, Produced)
    candidates: Candidates = outcome.value
    assert candidates.origin == first
    assert len(candidates.lists) == 2
    first_list, second_list = candidates.lists
    assert first_list.query == first
    assert first_list.retriever == NAME
    assert first_list.channel == Channel.VECTOR.value
    assert [passage.node.content for passage in first_list.hits] == ["a", "b"]
    assert [passage.rank for passage in first_list.hits] == [0, 1]
    assert all(passage.retrieved_by == NAME for passage in first_list.hits)
    assert second_list.query == second
    assert [passage.node.content for passage in second_list.hits] == ["c"]
    # top_k propagated to every search, not silently dropped.
    assert all(top_k == 5 for _, top_k in store.calls)


async def test_a_query_the_store_finds_nothing_for_still_comes_back_as_an_empty_list() -> None:
    # Arrange — the emptiness rule stated on `weft_retrieve.contract`: a stage that ran and
    # found nothing returns `Produced` carrying an empty collection, never
    # `NothingToProduce`, which on the query path would stop the pipeline with no `Answer`.
    asked = Query(text="a question this corpus has no answer for")
    store = _StubVectorStore(by_key={})
    services = ServiceRegistry()
    services.add(NodeStore, store)
    services.add(Embedder, _StubEmbedder())
    payload = QuerySet(origin=asked, queries=(asked,))
    retriever = VectorTopK()

    # Act
    outcome = await retriever.run(payload, _ctx(services))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value == Candidates(
        origin=asked,
        lists=(RankedList(query=asked, retriever=NAME, channel=Channel.VECTOR.value, hits=()),),
    )


async def test_querysets_ext_is_carried_onto_the_produced_candidates() -> None:
    # Arrange — the edge case ledger 2.23 exposed: `QuerySet.ext` is where a `QueryTransform`
    # attaches something a later stage needs (`weft_retrieve.payload`'s own module
    # docstring), and this plugin used to drop it silently the moment it ran. Any
    # `ExtModel` proves the point; `weft_retrieve.boolean.BooleanPlan` is the one real
    # caller this fix exists for, but importing that pack's own extension type here would
    # test a fixture no more thoroughly than a private one does.
    class _Carried(ExtModel):
        __namespace__ = "test-vector-top-k"

        text: str

    asked = Query(text="does ext survive a retrieval?")
    store = _StubVectorStore(by_key={})
    services = ServiceRegistry()
    services.add(NodeStore, store)
    services.add(Embedder, _StubEmbedder())
    payload = QuerySet(
        origin=asked,
        queries=(asked,),
        ext={_Carried.__namespace__: _Carried(text="carried")},
    )
    retriever = VectorTopK()

    # Act
    outcome = await retriever.run(payload, _ctx(services))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.ext == payload.ext


async def test_a_store_with_no_vector_search_fails_named_rather_than_crashing() -> None:
    # Arrange — nothing yet calls `weft_cli.run_services.check_store_capabilities` against
    # a query pipeline (that module's own docstring says the assembler lands with tasks 2.8
    # and 2.10), so this is today's one line between a misconfigured store and the
    # `AttributeError` mid-batch task 2.5's own repair closed for the fallback chain.
    class _StoreWithNoVectorSearch:
        pass

    asked = Query(text="what happens without VectorSearch?")
    services = ServiceRegistry()
    services.add(NodeStore, _StoreWithNoVectorSearch())
    services.add(Embedder, _StubEmbedder())
    payload = QuerySet(origin=asked, queries=(asked,))
    retriever = VectorTopK()

    # Act
    outcome = await retriever.run(payload, _ctx(services))

    # Assert
    assert isinstance(outcome, Failed)
    assert "VectorSearch" in outcome.reason


def test_config_refuses_a_channel_this_retriever_cannot_search() -> None:
    # Act / Assert — `vector-top-k` declares `needs_store = (VectorSearch,)` alone; a
    # `channels` value it has no store capability to service is refused here rather than
    # accepted and silently dropped at the first `search_text` call this plugin never makes.
    with pytest.raises(ValidationError, match="hybrid"):
        VectorTopKConfig(channels=(Channel.TEXT,))


async def test_driving_vector_top_k_through_the_seam_produces_a_ranked_list() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives. `VectorTopK` opens no connection and calls no model, so
    nothing here is expected to fail; the value of this test is structural, the same shape
    task 2.13's own seam-driving test for `NoRetrieval` uses."""
    # Arrange
    asked = Query(text="does this pass through the seam?")
    store = _StubVectorStore({float(len(asked.text)): (_hit("hit", 0.8),)})
    services = ServiceRegistry()
    services.add(NodeStore, store)
    services.add(Embedder, _StubEmbedder())
    retriever = VectorTopK()
    wrapped = wrap(retriever.run, distribution="weft-retrieve", contract="Retriever", plugin=NAME)
    payload = QuerySet(origin=asked, queries=(asked,))

    # Act
    outcome = await wrapped(payload, _ctx(services))

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.lists[0].hits] == ["hit"]
    assert isinstance(retriever, Retriever)


def test_the_declared_cost_bound_is_zero_zero() -> None:
    # Act / Assert — the class attribute this module's docstring claims for `run`'s two
    # `ctx.require` calls (`NodeStore`, `Embedder`) and no LLM-shaped one, read directly
    # rather than inferred from a counter — the same honest shape `test_no_retrieval.py`
    # already uses for its own `(0, 0)`.
    assert VectorTopK.cost_bound == (0, 0)
