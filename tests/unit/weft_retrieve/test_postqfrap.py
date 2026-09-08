"""Unit tests for `weft_retrieve.postqfrap` — ledger task **10.15**.

Mirrors `packages/weft-rag/src/weft_retrieve/postqfrap.py`. The technique is Chucri, Azouz & Ott,
*Recursive Abstractive Processing for Retrieval in Dynamic Datasets* (2024, arXiv:2410.01736) §5,
Algorithm 3, read at source: retrieve `k0` chunks, build a **query-focused** recursive-abstractive
tree over them with **one-step clustering**, then produce one final query-focused summary from the
tree's top layer instead of returning a top-k list.

**Why this is a `ContextPacker` and not an `Expander`, which is what grilling session G15 settled.**
The blocker recorded on this task's ledger line was that `Expander.run` takes `(payload, ctx)` and
no query. True, and beside the point — a query-time summariser is not an `Expander`. `Ranking`
carries `origin: Query`, `ContextPacker` is `Stage[Ranking, Passages]`, and the question is
therefore already in hand at exactly the position this technique occupies. No contract change, no
ambient query, and nothing stored, because the retrieval path has no `store` stage at all.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, Produced, SourceId, Vector
from weft_llm.contract import LLM
from weft_prompts.contract import Prompts
from weft_retrieve.contract import ContextPacker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_retrieve.postqfrap import NAME, PostQfrapConfig, PostQfrapPacker
from weft_store.contract import Scored

_SOURCE = SourceId("doc-1")


def _node(content: str, vector: Vector | None = None) -> Node:
    node = Node.synthetic(
        content=content, media_type=MediaType.TEXT, reason="fixture", sources=frozenset({_SOURCE})
    )
    return node if vector is None else node.with_embedding(vector)


def _hit(content: str, vector: Vector | None, rank: int) -> Passage:
    return Passage(
        scored=Scored(value=_node(content, vector), score=1.0 - rank / 100),
        rank=rank,
        retrieved_by="vector-top-k",
    )


class _RecordingLLM:
    """Answers every completion with the next scripted reply, and keeps every prompt it saw."""

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []

    async def complete(self, prompt: str, *, role: str, ctx: Context) -> object:
        del role, ctx
        self.prompts.append(prompt)
        from weft_llm.payload import Completion

        text = self._replies.pop(0) if self._replies else "a summary"
        return Produced(value=Completion(text=text, model="fixture"))


class _EchoPrompts:
    """Renders any request by joining its field values — enough to see the query travel."""

    async def render(self, name: str, values: object, ctx: Context) -> object:
        del ctx
        # `values` arrives typed `object` because `Prompts.render` accepts any request model.
        # Narrowed by `isinstance` rather than read through `getattr`, so pyright knows the
        # type of every value in the dump — `L10.20`'s rule: a `# type: ignore` on the access
        # line does not reach the comprehension below it.
        assert isinstance(values, BaseModel)
        rendered = "\n".join(str(value) for value in values.model_dump().values())
        return Produced(value=f"{name}\n{rendered}")


def _ctx(llm: object, prompts: object | None = None) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(Prompts, prompts if prompts is not None else _EchoPrompts())
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en", services=services)


def _ranking(hits: Sequence[Passage], question: str = "what did the study measure?") -> Ranking:
    return Ranking(origin=Query(text=question), hits=tuple(hits))


async def test_the_packer_returns_one_summary_built_from_every_hit() -> None:
    """Algorithm 3 step 5: one final summary replaces the top-k list.

    The paper's own reason is redundancy — *"a summarization step is applied to all nodes at the
    last layer of the tree, instead of using a top-k retrieval approach, to reduce redundancy"*.
    So the output is one `Passage`, and its lineage names the hits it was built from, which is what
    keeps a citation followable back to real documents.
    """
    # Arrange — four hits in two tight pairs, so one-step clustering forms two clusters.
    hits = [
        _hit("alpha one", Vector(values=(1.0, 0.0)), 0),
        _hit("alpha two", Vector(values=(0.99, 0.01)), 1),
        _hit("beta one", Vector(values=(0.0, 1.0)), 2),
        _hit("beta two", Vector(values=(0.01, 0.99)), 3),
    ]
    llm = _RecordingLLM(["alpha summary", "beta summary", "the final summary"])

    # Act
    outcome = await PostQfrapPacker(PostQfrapConfig(cluster_size=2)).run(_ranking(hits), _ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    passages = outcome.value.passages
    assert len(passages) == 1, (
        f"postQFRAP returns one final summary, not a list of passages: {len(passages)}"
    )
    summary = passages[0].node
    assert summary.content == "the final summary"
    assert set(summary.lineage.sources) == {_SOURCE}, (
        "the summary must carry its members' sources, or a cascade delete cannot reach it"
    )


async def test_the_question_reaches_every_summarising_call() -> None:
    """*Query-focused* is the paper's key modification, so it is the thing to assert.

    §5.2: *"The key modification is using query-focused summarization... Since the tree is
    constructed to answer q, summarizing information relevant to q ensures that key details are
    preserved while recursively filtering out irrelevant content."* A tree built with the ordinary
    cluster prompt would be RAPTOR at query time, which is a different and weaker technique.
    """
    # Arrange
    hits = [
        _hit("alpha one", Vector(values=(1.0, 0.0)), 0),
        _hit("alpha two", Vector(values=(0.99, 0.01)), 1),
    ]
    llm = _RecordingLLM(["a cluster summary", "the final summary"])

    # Act
    await PostQfrapPacker(PostQfrapConfig(cluster_size=2)).run(
        _ranking(hits, question="how many trials were run?"), _ctx(llm)
    )

    # Assert
    assert llm.prompts, "nothing was summarised at all"
    assert all("how many trials were run?" in prompt for prompt in llm.prompts), (
        "every summarising call must carry the question — that is what makes this "
        f"query-focused rather than RAPTOR at query time: {llm.prompts}"
    )


async def test_a_hit_with_no_vector_is_refused_by_name() -> None:
    """One-step clustering runs on the retrieved chunks' own embeddings and computes none.

    §5.2: *"we modify the clustering to rely solely on local embeddings, as retrieving k0 documents
    already serves as a global filtering step."* A store hands its vectors back with its nodes, so
    a hit without one means the stage was placed after something that stripped them — a `Failed`
    naming the count, exactly as `raptor` refuses an unembedded node rather than silently
    clustering a subset.
    """
    # Arrange
    hits = [
        _hit("alpha one", Vector(values=(1.0, 0.0)), 0),
        _hit("no vector here", None, 1),
    ]

    # Act
    outcome = await PostQfrapPacker(PostQfrapConfig(cluster_size=2)).run(
        _ranking(hits), _ctx(_RecordingLLM(["s"]))
    )

    # Assert
    assert isinstance(outcome, Failed)
    assert NAME in outcome.reason and "embedding" in outcome.reason, (
        f"the refusal must name the plugin and what was missing: {outcome.reason!r}"
    )


async def test_no_hits_packs_to_empty_passages_rather_than_a_summary_of_nothing() -> None:
    """The emptiness rule every stage in this module already keeps.

    `09` §4's V2 requires the engine to be able to answer *"not in this corpus"*, and a summariser
    that invents a paragraph from zero passages is the exact opposite of that answer.
    """
    # Arrange & Act
    outcome = await PostQfrapPacker().run(_ranking([]), _ctx(_RecordingLLM([])))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.passages == ()


def test_the_packer_satisfies_the_context_packer_contract_structurally() -> None:
    """Capability derived, never declared — the plugin never imports the contract it satisfies."""
    # Arrange & Act & Assert
    assert isinstance(PostQfrapPacker(), ContextPacker)
