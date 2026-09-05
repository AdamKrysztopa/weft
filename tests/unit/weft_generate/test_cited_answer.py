"""Unit tests for `weft_generate.cited_answer`.

Mirrors `packages/weft-rag/src/weft_generate/cited_answer.py`. Task **2.9**: "an
answer carries citations a reader can follow back to a passage — not to a document, and
not to a paraphrase." Covers the happy path (a completion whose markers match offered
labels becomes exactly those citations, with page and uri resolved), the two shapes of
the empty-evidence edge case (`REFUSE` costs no model call, `ANSWER_FROM_MEMORY` asks
anyway with nothing shown), the error case of a marker the model wrote that was never
offered (silently dropped rather than fabricated), and a drive through
`weft_kernel.seam.wrap`.

**The `LLM` is a stub and `Prompt.render` is real.** The same split `test_rerank.py`
takes, one layer down: `AnswerWithCitationsPrompt` is exercised for real so this plugin's
reading of what it renders is tested against the shape rendering actually produces,
while the model answering it is a script.

`out.origin == in.origin` is asserted rather than assumed, for the same reason
`test_rerank.py` asserts it: `QuerySet.origin` is a contract term nothing in the kernel
checks, and 2.4's ledger line leaves the obligation with each query-path plugin —
`cited-answer` closes the query path, so it is the last place that obligation applies.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from weft_chunk.payload import ChunkOffset
from weft_generate.cited_answer import NAME, CitedAnswer, CitedAnswerConfig, WhenNoEvidence
from weft_generate.contract import Generator
from weft_generate.payload import AnswerStance
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import ExtModel, MediaType, Node, NodeId, Outcome, Produced, SourceId
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_pdf import PdfPages
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Passage, Passages, Query
from weft_store.contract import NodeStore, Scored, SourceRecord, SourceStatus


class _StubLLM:
    """An `LLM` answering from a script, and counting what it was asked."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del role, ctx
        self.last_prompt = rendered.conversation.messages[-1].content
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own prompt, and refusing the other verb."""

    def __init__(self, prompts: Mapping[str, object]) -> None:
        self._prompts = prompts
        self.asked: list[str] = []

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset(self._prompts)

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        raise AssertionError("this plugin resolves a capability by name, never a stage")

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        del contract, config
        self.asked.append(name)
        return self._prompts[name]


class _StubStore:
    """A `NodeStore` answering `get_source` and `get` from fixed tables, and nothing else."""

    def __init__(
        self, records: Mapping[str, SourceRecord], nodes: Mapping[NodeId, Node] | None = None
    ) -> None:
        self._records = records
        self._nodes = nodes or {}
        self.looked_up: list[str] = []
        self.fetched: list[object] = []

    async def get_source(self, source_id: object) -> SourceRecord | None:
        self.looked_up.append(str(source_id))
        return self._records.get(str(source_id))

    async def get(self, ids: Sequence[NodeId]) -> tuple[Node, ...]:
        self.fetched.extend(ids)
        return tuple(self._nodes[node_id] for node_id in ids if node_id in self._nodes)


def _lookup() -> _StubLookup:
    return _StubLookup({ANSWER_WITH_CITATIONS_NAME: AnswerWithCitationsPrompt()})


def _services(llm: _StubLLM, *, store: _StubStore | None = None) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, _lookup())
    services.add(NodeStore, store if store is not None else _StubStore({}))
    return services


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _passage(label: str, content: str, *, retrieved_by: str = "vector-top-k") -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")
    return Passage(
        scored=Scored(value=node, score=0.5), rank=0, retrieved_by=retrieved_by, label=label
    )


def _passages(*items: Passage) -> Passages:
    asked = Query(text="why is mRMR preferred to plain relevance ranking?")
    return Passages(origin=asked, passages=items)


async def test_markers_the_model_wrote_become_citations_with_page_and_uri_resolved() -> None:
    # Arrange — the cited passage carries the two facts `weft_generate.page.page_for`
    # needs, and its one source resolves through the store.
    node = Node.synthetic(
        content="mRMR reduces redundancy between selected features.",
        media_type=MediaType.TEXT,
        reason="test fixture",
        sources=frozenset({SourceId("doc-1")}),
    )
    node = node.with_ext(PdfPages(backend="pdf-text", starts=(0, 50))).with_ext(
        ChunkOffset(start=10)
    )
    cited = Passage(
        scored=Scored(value=node, score=0.9), rank=0, retrieved_by="vector-top-k", label="1"
    )
    uncited = _passage("2", "an unrelated passage about something else")
    payload = _passages(cited, uncited)
    llm = _StubLLM(["mRMR reduces redundancy [1]."])
    store = _StubStore(
        {
            "doc-1": SourceRecord(
                id=SourceId("doc-1"),
                uri="corpus/mrmr.pdf",
                content_hash="h",
                indexed_at=datetime(2026, 1, 1, tzinfo=UTC),
                pipeline="ingest",
                status=SourceStatus.ACTIVE,
            )
        }
    )

    # Act
    outcome = await CitedAnswer().run(payload, _ctx(_services(llm, store=store)))

    # Assert
    assert isinstance(outcome, Produced)
    answer = outcome.value
    assert answer.origin == payload.origin
    assert answer.stance == AnswerStance.ANSWERED
    assert answer.used == (cited, uncited)
    assert len(answer.citations) == 1
    citation = answer.citations[0]
    assert citation.marker == "1"
    assert citation.node_id == node.id
    assert citation.source_id == "doc-1"
    assert citation.uri == "corpus/mrmr.pdf"
    assert citation.page == 1
    assert llm.calls == 1


async def test_empty_evidence_refuses_without_calling_a_model() -> None:
    # Arrange — the default behaviour: "cited-answer is the stage that turns empty
    # evidence into Answer(stance=NOT_IN_CORPUS)", `.phase2-design.md` §3, verbatim.
    payload = _passages()
    llm = _StubLLM(["never asked"])

    # Act
    outcome = await CitedAnswer().run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.stance == AnswerStance.NOT_IN_CORPUS
    assert outcome.value.text == ""
    assert outcome.value.used == ()
    assert outcome.value.citations == ()
    assert llm.calls == 0


async def test_empty_evidence_answers_from_memory_when_so_configured() -> None:
    # Arrange — what `no-retrieval`'s own pipeline sets: the null-retrieval branch is a
    # deliberate choice to answer from parametric memory, not a retrieval failure.
    payload = _passages()
    llm = _StubLLM(["mRMR is a feature-selection criterion."])
    config = CitedAnswerConfig(when_no_evidence=WhenNoEvidence.ANSWER_FROM_MEMORY)

    # Act
    outcome = await CitedAnswer(config).run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.stance == AnswerStance.ANSWERED
    assert outcome.value.used == ()
    assert outcome.value.citations == ()
    assert llm.calls == 1
    assert "Passages:\n\n" in llm.last_prompt or llm.last_prompt.endswith("Passages:\n")


async def test_a_marker_the_model_wrote_for_a_passage_never_offered_is_dropped_not_fabricated() -> (
    None
):
    # Arrange — `max_passages=1` truncates the offer to one passage, but the model
    # hallucinates a second marker anyway. A citation for it would name a passage that
    # never entered the prompt, which `Answer._citations_resolve` refuses by construction;
    # this plugin must never build one to construct against.
    first = _passage("1", "first passage")
    second = _passage("2", "second passage")
    payload = _passages(first, second)
    llm = _StubLLM(["the answer rests on [1] and also, implausibly, [2]."])
    config = CitedAnswerConfig(max_passages=1)

    # Act
    outcome = await CitedAnswer(config).run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.used == (first,)
    assert [c.marker for c in outcome.value.citations] == ["1"]


async def test_a_summary_node_with_more_than_one_source_cites_with_no_source_id() -> None:
    # Arrange — `Node.combine` sources from several documents at once; naming one as *the*
    # source would misattribute the claim, so `source_id` and `uri` stay empty rather than
    # guessing, and the citation still resolves — to the node, if not to one document.
    members = (
        Node.synthetic(
            content="a", media_type=MediaType.TEXT, reason="t", sources=frozenset({SourceId("a")})
        ),
        Node.synthetic(
            content="b", media_type=MediaType.TEXT, reason="t", sources=frozenset({SourceId("b")})
        ),
    )
    summary = Node.combine(members, content="a and b, summarised", media_type=MediaType.TEXT)
    passage = Passage(
        scored=Scored(value=summary, score=0.5), rank=0, retrieved_by="raptor", label="1"
    )
    payload = _passages(passage)
    llm = _StubLLM(["a summary claim [1]."])

    # Act
    outcome = await CitedAnswer().run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    citation = outcome.value.citations[0]
    assert citation.source_id is None
    assert citation.uri == ""


class _ThirdPartyRepresentation(ExtModel):
    """A structural stand-in for `weft_index.payload.Representation`, deliberately not that
    class — proving the read in `weft_generate.representation` is duck-typed, per that
    module's own docstring, rather than an import of the one pack that ships it today.
    """

    __namespace__ = "test-fixture-pack"
    __schema_version__ = "1.0.0"

    technique: str = "test-representation"


async def test_a_citation_for_a_representation_node_resolves_to_its_one_parent() -> None:
    # Arrange — `parent` is the real, page-locatable passage; `question` is a derived
    # node standing in for it (`.phase2-findings.md` §11's own shape: one `Lineage.parents`
    # entry, a marker carrying `technique`). The retrieved hit is `question`; the citation
    # a reader follows must land on `parent`, never on the generated question's own text.
    parent = Node.synthetic(
        content="mRMR reduces redundancy between selected features.",
        media_type=MediaType.TEXT,
        reason="test fixture",
        sources=frozenset({SourceId("doc-1")}),
    )
    parent = parent.with_ext(PdfPages(backend="pdf-text", starts=(0, 50))).with_ext(
        ChunkOffset(start=10)
    )
    question = parent.derive(content="What does mRMR reduce?").with_ext(_ThirdPartyRepresentation())
    cited = Passage(
        scored=Scored(value=question, score=0.9),
        rank=0,
        retrieved_by="hypothetical-questions",
        label="1",
    )
    payload = _passages(cited)
    llm = _StubLLM(["mRMR reduces redundancy [1]."])
    store = _StubStore(
        {
            "doc-1": SourceRecord(
                id=SourceId("doc-1"),
                uri="corpus/mrmr.pdf",
                content_hash="h",
                indexed_at=datetime(2026, 1, 1, tzinfo=UTC),
                pipeline="ingest",
                status=SourceStatus.ACTIVE,
            )
        },
        nodes={parent.id: parent},
    )

    # Act
    outcome = await CitedAnswer().run(payload, _ctx(_services(llm, store=store)))

    # Assert — the citation names the parent chunk, not the generated question, and its
    # page resolves from the parent's own offset, which the question node does not carry.
    assert isinstance(outcome, Produced)
    citation = outcome.value.citations[0]
    assert citation.node_id == parent.id
    assert citation.node_id != question.id
    assert citation.page == 1
    assert citation.source_id == "doc-1"
    assert citation.uri == "corpus/mrmr.pdf"
    # `used` and what the model was shown both carry the real passage, not the question —
    # the corollary `cited_answer.py`'s own module docstring records: a reader inspecting
    # the answer's evidence sees the same node the citation resolves to.
    assert outcome.value.used[0].node.id == parent.id
    assert "mRMR reduces redundancy between selected features." in llm.last_prompt


async def test_a_representation_with_more_than_one_parent_is_cited_as_itself() -> None:
    # Arrange — `Node.combine`'s shape (a cluster summary): several parents, so there is
    # no single "the" parent to stand in for. Even carrying the marker, this node must be
    # cited as itself, not silently resolved to one arbitrary member.
    members = (
        Node.synthetic(
            content="a", media_type=MediaType.TEXT, reason="t", sources=frozenset({SourceId("a")})
        ),
        Node.synthetic(
            content="b", media_type=MediaType.TEXT, reason="t", sources=frozenset({SourceId("b")})
        ),
    )
    summary = Node.combine(members, content="a and b, summarised", media_type=MediaType.TEXT)
    summary = summary.with_ext(_ThirdPartyRepresentation())
    passage = Passage(
        scored=Scored(value=summary, score=0.5), rank=0, retrieved_by="raptor", label="1"
    )
    payload = _passages(passage)
    llm = _StubLLM(["a summary claim [1]."])

    # Act
    outcome = await CitedAnswer().run(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.citations[0].node_id == summary.id


async def test_driving_cited_answer_through_the_seam_produces_an_answer() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a
    registered instance never receives."""
    # Arrange
    payload = _passages(_passage("1", "only candidate"))
    llm = _StubLLM(["the only candidate answers it [1]."])
    generator = CitedAnswer()
    wrapped = wrap(generator.run, distribution="weft-generate", contract="Generator", plugin=NAME)

    # Act
    outcome = await wrapped(payload, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    assert [c.marker for c in outcome.value.citations] == ["1"]
    assert isinstance(generator, Generator)


def test_the_declared_cost_bound_is_zero_one() -> None:
    # Act / Assert — zero when `run` returns before resolving anything (empty evidence,
    # `REFUSE`), one otherwise: at most one `LLM.complete` call, ever.
    assert CitedAnswer.cost_bound == (0, 1)
