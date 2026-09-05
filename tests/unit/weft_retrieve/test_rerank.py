"""Unit tests for `weft_retrieve.rerank`.

Mirrors `packages/weft-rag/src/weft_retrieve/rerank.py`. Task **2.7**: "fusion and
reranking are composable plugins a third party can retune, not a fixed ladder." This module
covers the reranking half — the happy path (three passages rescored and reordered against the
question, ranks renumbered, `top_n` honoured), the edge case (an empty ranking comes back
untouched and *no model is called*, which is what makes `cost_bound`'s floor of zero a fact
rather than a claim), the error case (a judgement set that is not exactly one per offered
passage is refused by name rather than half-applied), and a drive through
`weft_kernel.seam.wrap`.

**The `LLM` is a stub and the cascade is real.** `weft_prompts.cascade.execute` is the one
path a technique in this tree takes to a typed answer, and stubbing it out here would leave
this plugin's own reading of that answer untested against the shape the cascade actually
returns. The stub sits one layer lower, at `weft_llm.contract.LLM`, exactly where the run
assembler will put a real client.

`out.origin == in.origin` is asserted rather than assumed — `QuerySet.origin` is a contract
term nothing in the kernel checks, and task 2.4's ledger line leaves the obligation with each
query-path plugin. `out.ext == in.ext` is asserted for the same reason and with more at stake:
it is one of this task's recorded decisions, and nothing in the kernel or the contract would
notice a reranker that dropped it.
"""

from collections.abc import Mapping

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import ExtMap, ExtModel, Failed, MediaType, Node, Outcome, Produced
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_retrieve.contract import Reranker, StageLookup
from weft_retrieve.payload import Passage, Query, Ranking
from weft_retrieve.prompts import PASSAGE_RELEVANCE_NAME, PassageRelevancePrompt
from weft_retrieve.rerank import NAME, LlmRerank, LlmRerankConfig
from weft_store.contract import Scored


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script, and counting what it was asked.

    `native_structured_available` is `False`, so tier 1 is skipped structurally rather than by
    a flag — the same derived-capability check a real provider is subject to.
    """

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del role, ctx
        self.last_prompt = rendered.conversation.messages[-1].content
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own prompts, and recording what was asked for.

    The real one refuses an unregistered name with the registry's own `UnknownPluginError`,
    naming the contract, the name and every valid option — requirement 5, held by the registry
    rather than by anything in this plugin, which is why nothing here tests for it.
    """

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


def _services(llm: _StubLLM, lookup: _StubLookup) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, lookup)
    return services


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _lookup() -> _StubLookup:
    return _StubLookup({PASSAGE_RELEVANCE_NAME: PassageRelevancePrompt()})


class _Note(ExtModel):
    """A carrier extension, to prove `ext` survives a rerank — G5's mechanism is the settled
    answer to "a strategy needs to pass something along", and a stage that rebuilds its
    carrier from parts, as this one must to reorder the hits, is exactly where such a pass
    -along is dropped without anything noticing."""

    __namespace__ = "test-rerank"
    __schema_version__ = "1.0.0"

    text: str


def _passage(content: str, score: float, rank: int) -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by="vector-top-k")


def _ranking(*contents: str, ext: ExtMap | None = None) -> Ranking:
    asked = Query(text="why is mRMR preferred to plain relevance ranking?")
    hits = tuple(
        _passage(content, 1.0 - (rank / 10), rank) for rank, content in enumerate(contents)
    )
    return Ranking(
        origin=asked, hits=hits, contributors=("vector-top-k:vector",), ext=ext if ext else {}
    )


async def test_the_model_reorders_and_rescores_the_passages_it_was_given() -> None:
    # Arrange — retrieval put "redundancy" first; the model says the third passage is the one
    # that answers the question. What arrives back is the model's order, not retrieval's.
    payload = _ranking("about redundancy", "off topic", "the actual answer")
    llm = _StubLLM(
        [
            '{"judgements": [{"index": 0, "relevance": 0.4}, '
            '{"index": 1, "relevance": 0.0}, {"index": 2, "relevance": 0.95}]}'
        ]
    )
    lookup = _lookup()

    # Act
    outcome = await LlmRerank().run(payload, _ctx(_services(llm, lookup)))

    # Assert
    assert isinstance(outcome, Produced)
    ranking: Ranking = outcome.value
    assert ranking.origin == payload.origin
    assert [passage.node.content for passage in ranking.hits] == [
        "the actual answer",
        "about redundancy",
        "off topic",
    ]
    assert [passage.rank for passage in ranking.hits] == [0, 1, 2]
    assert [passage.score for passage in ranking.hits] == [0.95, 0.4, 0.0]
    assert ranking.contributors == payload.contributors
    assert lookup.asked == [PASSAGE_RELEVANCE_NAME]
    assert llm.calls == 1


async def test_top_n_keeps_the_best_and_drops_the_rest() -> None:
    # Arrange — `top_n` is what a third party retunes without touching this file.
    payload = _ranking("first", "second", "third")
    llm = _StubLLM(
        [
            '{"judgements": [{"index": 0, "relevance": 0.1}, '
            '{"index": 1, "relevance": 0.9}, {"index": 2, "relevance": 0.5}]}'
        ]
    )

    # Act
    outcome = await LlmRerank(LlmRerankConfig(top_n=2)).run(
        payload, _ctx(_services(llm, _lookup()))
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["second", "third"]


async def test_an_empty_ranking_comes_back_untouched_without_asking_a_model() -> None:
    # Arrange — the emptiness rule, and `cost_bound`'s floor of zero in the same test: there
    # is nothing to judge, so there is nothing to pay for, and a `NothingToProduce` here would
    # stop the pipeline where V2 requires an answer of "not in this corpus".
    asked = Query(text="a question this corpus has no answer for")
    payload = Ranking(origin=asked, hits=(), contributors=("vector-top-k:vector",))
    llm = _StubLLM(["never asked"])

    # Act
    outcome = await LlmRerank().run(payload, _ctx(_services(llm, _lookup())))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value == payload
    assert llm.calls == 0


async def test_a_judgement_set_that_is_not_one_per_passage_is_refused_by_name() -> None:
    # Arrange — the model judged two of three and invented a fourth index. Applying what
    # arrived and leaving the rest where they were is the silent half-rerank this refuses:
    # the result would be an ordering nobody chose, indistinguishable from one somebody did.
    payload = _ranking("first", "second", "third")
    llm = _StubLLM(
        ['{"judgements": [{"index": 0, "relevance": 0.4}, {"index": 7, "relevance": 0.9}]}']
    )

    # Act
    outcome = await LlmRerank().run(payload, _ctx(_services(llm, _lookup())))

    # Assert
    assert isinstance(outcome, Failed)
    assert NAME in outcome.reason
    assert "7" in outcome.reason


async def test_a_repeated_index_is_refused_rather_than_quietly_resolved() -> None:
    # Arrange
    payload = _ranking("first", "second")
    llm = _StubLLM(
        [
            '{"judgements": [{"index": 0, "relevance": 0.4}, '
            '{"index": 0, "relevance": 0.9}, {"index": 1, "relevance": 0.2}]}'
        ]
    )

    # Act
    outcome = await LlmRerank().run(payload, _ctx(_services(llm, _lookup())))

    # Assert
    assert isinstance(outcome, Failed)
    assert "0" in outcome.reason


async def test_driving_llm_rerank_through_the_seam_produces_a_ranking() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    payload = _ranking("only candidate")
    llm = _StubLLM(['{"judgements": [{"index": 0, "relevance": 0.6}]}'])
    reranker = LlmRerank()
    wrapped = wrap(reranker.run, distribution="weft-retrieve", contract="Reranker", plugin=NAME)

    # Act
    outcome = await wrapped(payload, _ctx(_services(llm, _lookup())))

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.score for passage in outcome.value.hits] == [0.6]
    assert isinstance(reranker, Reranker)


async def test_an_extension_attached_before_the_rerank_survives_it() -> None:
    """The reranker rebuilds its `Ranking` to reorder it, and everything it does not name in
    that construction is lost. `ext` is named, and this is what says so — driven through
    `weft_kernel.seam.wrap`, because the seam is where `__transient__` namespaces are stripped
    and a carrier extension must be shown to cross that too, not only the plugin."""
    # Arrange
    note = _Note(text="carried")
    payload = _ranking("first", "second", ext={_Note.__namespace__: note})
    llm = _StubLLM(
        ['{"judgements": [{"index": 0, "relevance": 0.2}, {"index": 1, "relevance": 0.8}]}']
    )
    wrapped = wrap(LlmRerank().run, distribution="weft-retrieve", contract="Reranker", plugin=NAME)

    # Act
    outcome = await wrapped(payload, _ctx(_services(llm, _lookup())))

    # Assert — reordered, and still carrying what was attached to the ranking it was given.
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["second", "first"]
    assert outcome.value.ext == payload.ext


def test_the_prompt_and_the_role_are_configuration_rather_than_constants() -> None:
    # Act / Assert — requirement 6's second clause, read off the config model: an operator
    # retunes the wording and which model answers without touching this distribution.
    config = LlmRerankConfig(prompt="my-own-grader", role="cheap")
    assert (config.prompt, config.role) == ("my-own-grader", "cheap")
    assert LlmRerankConfig().prompt == PASSAGE_RELEVANCE_NAME
    assert LlmRerank.config_model is LlmRerankConfig


def test_the_declared_cost_bound_is_zero_to_one() -> None:
    # Act / Assert — zero when there is nothing to judge (asserted above against a counting
    # stub), one otherwise. A cascade stepping down is one ask re-put, not a second question,
    # which is the same arithmetic `.phase2-design.md` §10 uses for `graded-retrieval`'s `(1, 4)`.
    assert LlmRerank.cost_bound == (0, 1)
