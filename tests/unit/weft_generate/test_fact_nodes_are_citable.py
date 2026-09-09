"""Ledger task **11.1** — a `Node` carrying a fact is citable, and carries its own page.

Phase 11's `D1` is that a graph fact is a `Node` derived from the chunk it was read out of,
rather than a row of the graph pack's own tables. This file is the proof that decision rests
on, and it is written **before** any fact payload is fixed because it is cheap to prove now
and expensive to be wrong about later: everything below uses the shipped payload model and
the shipped query path, and `weft-graph` does not exist yet.

**The two halves are not the same claim, and only one of them is free.** *Provenance* is one
`NodeStore.get` away through `lineage.parents`, so a fact that says nothing about where it
came from is still traceable. *A page* is not: `Node.derive` and `Node.combine` both drop
`ext` on purpose (`weft_kernel.payload.node`, "later stages attach their own"), and
`weft_generate.page.page_for` walks only the same node's `ext` — it never follows lineage.
So a fact node that does not carry the page-bearing model **its parent carried** resolves to
no page at all, no matter what its parent knows. That makes the carry the future extractor's
obligation rather than the payload model's, which is exactly what this file pins down.

**Why the parent's `ChunkOffset` travels with it, and why that is not `G17`'s hazard.**
`page_for` needs two facts on one node: something with a `start` and something that can turn
a `start` into a page. `PdfPages.starts` and `ChunkOffset.start` are both offsets into the
*root's* extracted text (`weft_pdf.document.PdfPages`'s class docstring says so), so
carrying the pair forward unchanged keeps them in the one coordinate system they were built
in, and answers "which page is the evidence for this fact on". `G17` is open about what such
a locator means once a stage **rewrites the content it indexes**; a fact extractor rewrites
nothing — it reads a chunk and emits a new node beside it — so the two do not meet here.
Attaching a *fresh* `ChunkOffset` was the alternative and it has no referent: a fact's prose
is generated, not sliced, so there is no offset of its own to state.

**What this file therefore constrains in `11.7`, where the fact payload is fixed.** A fact is
cited as *itself*, which `weft_generate.representation.citable_nodes` will silently undo for
any single-parent node carrying an `ext` model with a `technique: str` attribute — it cites
such a node as its parent, by design, for `weft_index.payload.Representation`. A fact ext
model naming a field `technique` would therefore make every fact cite the chunk it came from
and nothing would report it.

**What this proves, and what it does not — measured rather than implied.** The property below is
a property of the payload model, and it has **no live instance on any shipped ladder today**. A
real paper indexed from outside this repository with `weft index corpus --pipeline index-pdf`
stored 70 nodes whose only `ext` namespaces are `weft-chunk` (57) and `weft-extract-table` (13):
`weft-pdf` is on none of them, because every `weft_clean` cleaner rebuilds its node with
`Node.derive`. That is carried repair `R9.1`, blocked on `G17`, and it means a fact node derived
from a chunk of a *text* pipeline inherits no page because its parent has none to give. The carry
is still the extractor's obligation and this file is still what fixes it; what a reader must not
take from a green run here is that facts will arrive with pages before `R9.1` lands.

The two facts under test are attached by two packs in two stages, which is the shape `L6.14`
says a hand-written double gets wrong — so the parent chunk here is produced by the **real**
`FixedSizeChunker` over a root carrying a **real** `PdfPages`, and only the fact node itself
is built by hand, that being the part actually under proof.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from weft_chunk.carry import carry_forward
from weft_chunk.fixed_size import FixedSizeChunker, FixedSizeChunkerConfig
from weft_chunk.payload import ChunkOffset
from weft_generate.cited_answer import CitedAnswer
from weft_generate.page import page_for
from weft_generate.payload import Answer, AnswerStance, Citation
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, NodeId, Outcome, Produced, SourceId
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_pdf import PdfPages
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Passage, Passages, Query
from weft_store.contract import NodeStore, Scored, SourceRecord, SourceStatus

#: The document under test: three pages, and long enough that a chunk lands on a page that is
#: not the first one. A page-1 expectation would be satisfied by a `page_at` that had lost its
#: offset and answered the beginning of the document, so the assertions below check that the
#: page they resolve is past the first boundary.
_ROOT_CONTENT = "".join(f"sentence {n:03d} about feature selection. " for n in range(12))
_PAGE_STARTS = (0, 100, 220)
_SOURCE = SourceId("doc-1")
_STATEMENT = "mRMR selects features that are relevant and mutually non-redundant."


class _StubLLM:
    """An `LLM` answering from a script — the model is not what this file is proving."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls = 0

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, role, ctx
        self.calls += 1
        return Produced(value=Completion(text=self._reply, model="stub-model"))

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own prompt, which is rendered for real."""

    def __init__(self) -> None:
        self._prompts: Mapping[str, object] = {
            ANSWER_WITH_CITATIONS_NAME: AnswerWithCitationsPrompt()
        }

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset(self._prompts)

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        raise AssertionError("this plugin resolves a capability by name, never a stage")

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        del contract, config
        return self._prompts[name]


class _StubStore:
    """A `NodeStore` answering the one source record and no nodes."""

    def __init__(self) -> None:
        self.fetched: list[object] = []

    async def get_source(self, source_id: object) -> SourceRecord | None:
        if str(source_id) != str(_SOURCE):
            return None
        return SourceRecord(
            id=_SOURCE,
            uri="corpus/mrmr.pdf",
            content_hash="h",
            indexed_at=datetime(2026, 1, 1, tzinfo=UTC),
            pipeline="index-with-facts",
            status=SourceStatus.ACTIVE,
        )

    async def get(self, ids: Sequence[NodeId]) -> tuple[Node, ...]:
        self.fetched.extend(ids)
        return ()


def _ctx(store: _StubStore, llm: _StubLLM) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, _StubLookup())
    services.add(NodeStore, store)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _root() -> Node:
    """The document as an extractor hands it over: root content, real page boundaries."""
    root = Node.synthetic(
        content=_ROOT_CONTENT,
        media_type=MediaType.TEXT,
        reason="test fixture standing in for extraction",
        sources=frozenset({_SOURCE}),
    )
    return root.with_ext(PdfPages(backend="pdf-text", starts=_PAGE_STARTS))


async def _chunks() -> tuple[Node, ...]:
    """The parent chunks, produced by the **real** chunker rather than assembled here.

    `ChunkOffset` and the carried `PdfPages` are then this stage's own output, so nothing
    below depends on a hand-populated pair agreeing with what the pipeline actually builds
    (`L6.14`).
    """
    chunker = FixedSizeChunker(config=FixedSizeChunkerConfig(size=60, overlap=10))
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    outcome = await chunker.run((_root(),), ctx)
    assert isinstance(outcome, Produced)
    return tuple(outcome.value)


async def _evidence() -> Node:
    """One chunk that sits past the first page boundary — the whole point of the fixture."""
    for chunk in await _chunks():
        if (page := page_for(chunk)) is not None and page > 1:
            return chunk
    raise AssertionError(
        f"no chunk of the fixture resolved past page 1, so the assertions below would be "
        f"satisfied by a locator that had lost its offset; page starts are {_PAGE_STARTS} "
        f"and the root is {len(_ROOT_CONTENT)} characters"
    )


def _fact(evidence: Node) -> Node:
    """A fact node as `weft-graph`'s extractor will build one: derived from the chunk it was
    read out of, carrying every fact that chunk's `ext` held."""
    return carry_forward(evidence.derive(content=_STATEMENT), parent=evidence)


def _passages(*passages: Passage) -> Passages:
    return Passages(
        origin=Query(text="why is mRMR preferred to plain relevance ranking?"), passages=passages
    )


def _passage(node: Node, *, label: str, rank: int = 0) -> Passage:
    return Passage(
        scored=Scored(value=node, score=0.9), rank=rank, retrieved_by="graph-facts", label=label
    )


async def test_a_fact_carrying_its_parents_facts_resolves_to_the_page_of_its_evidence() -> None:
    """The property `11.1` states: a fact node's page is its evidence's page, read off the
    fact node alone, because that is all `page_for` is ever given."""
    # Arrange
    evidence = await _evidence()

    # Act
    fact = _fact(evidence)

    # Assert — the fact answers for itself, and answers the same page its evidence does.
    assert page_for(fact) == page_for(evidence)
    assert fact.content != evidence.content
    offset = fact.ext[ChunkOffset.__namespace__]
    locator = fact.ext[PdfPages.__namespace__]
    assert isinstance(offset, ChunkOffset)
    assert isinstance(locator, PdfPages)
    assert page_for(fact) == locator.page_at(offset.start) > 1


async def test_a_fact_that_does_not_carry_its_parents_facts_has_no_page_at_all() -> None:
    """The contrast that makes the test above non-vacuous: lineage alone buys nothing.

    `derive` gives this node the same parent, the same source and the same ancestry as the
    fact above — and no page, because `page_for` never follows any of them.
    """
    # Arrange
    evidence = await _evidence()

    # Act
    uncarried = evidence.derive(content=_STATEMENT)

    # Assert
    assert uncarried.lineage.parents == (evidence.id,)
    assert uncarried.lineage.sources == frozenset({_SOURCE})
    assert uncarried.ext == {}
    assert page_for(uncarried) is None
    assert page_for(evidence) is not None


async def test_a_fact_node_is_offered_as_a_passage_labelled_and_cited_to_itself() -> None:
    """The whole query path over a fact node: offered, labelled, cited, and the citation
    names the **fact**, carries its page and resolves to the document it came from."""
    # Arrange
    evidence = await _evidence()
    fact = _fact(evidence)
    payload = _passages(_passage(fact, label="1"), _passage(evidence, label="2", rank=1))
    llm = _StubLLM(f"{_STATEMENT} [1]")
    store = _StubStore()

    # Act
    outcome = await CitedAnswer().run(payload, _ctx(store, llm))

    # Assert
    assert isinstance(outcome, Produced)
    answer = outcome.value
    assert answer.stance == AnswerStance.ANSWERED
    assert len(answer.citations) == 1
    citation = answer.citations[0]
    assert citation.marker == "1"
    assert citation.node_id == fact.id
    assert citation.node_id != evidence.id
    # `> 1` rather than "not None": a citation whose page had degenerated to the start of the
    # document would still satisfy an equality against a `page_for` that had degenerated with
    # it, both sides being read through the same call (`L9.28`).
    page = page_for(fact)
    assert page is not None and page > 1
    assert citation.page == page
    assert citation.source_id == _SOURCE
    assert citation.uri == "corpus/mrmr.pdf"


async def test_a_citation_naming_the_evidence_instead_of_the_fact_is_refused() -> None:
    """`Answer._citations_resolve`, unchanged, is what makes the assertion above load-bearing.

    A fact and the chunk it was read out of are two nodes, and only one of them entered the
    prompt. A citation naming the other resolves to evidence the model never saw, which is
    the failure task 2.9 makes unconstructable — and it stays unconstructable for a fact.
    """
    # Arrange
    evidence = await _evidence()
    fact = _fact(evidence)

    # Act / Assert
    with pytest.raises(ValidationError) as raised:
        Answer(
            origin=Query(text="why is mRMR preferred to plain relevance ranking?"),
            text=f"{_STATEMENT} [1]",
            citations=(Citation(marker="1", node_id=evidence.id, source_id=_SOURCE),),
            used=(_passage(fact, label="1"),),
            answered_by="cited-answer",
        )
    assert str(evidence.id) in str(raised.value)


async def test_a_fact_combined_from_two_chunks_carries_only_the_page_it_was_given() -> None:
    """The second way a fact is built, and the reason the carry is the extractor's obligation.

    A fact supported by two chunks has two parents, so it is built by `Node.combine`, which
    takes no single parent to carry from and drops `ext` exactly as `derive` does. There is
    no page to infer — the two members can sit on different pages — so a combined fact has
    none until the extractor states which member's position it is citing.
    """
    # Arrange
    chunks = await _chunks()
    first, last = chunks[0], chunks[-1]
    assert page_for(first) != page_for(last)

    # Act
    combined = Node.combine((first, last), content=_STATEMENT, media_type=MediaType.TEXT)
    attributed = carry_forward(combined, parent=last)

    # Assert
    assert combined.lineage.parents == (first.id, last.id)
    assert combined.ext == {}
    assert page_for(combined) is None
    assert page_for(attributed) == page_for(last)
