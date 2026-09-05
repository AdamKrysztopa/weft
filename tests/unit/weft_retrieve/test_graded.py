"""Unit tests for `weft_retrieve.graded`.

Mirrors `packages/weft-rag/src/weft_retrieve/graded.py`. Ledger **2.21**: "per-document
relevance grading is a reusable post-retrieval filter." This module covers the happy path
(three hits, two batches, one grade below the floor filtered out and the survivors renumbered
contiguously), the edge case (an empty ranking comes back untouched and no model is called,
the same emptiness rule `weft_retrieve.rerank`'s own test module already establishes for
`llm-rerank`), the error case (a batch the model did not grade exactly once per offered
passage is refused by name), and a drive through `weft_kernel.seam.wrap`.

**The `LLM` is a stub and the cascade is real** — the identical shape `test_rerank.py` takes,
for the identical reason: `weft_prompts.cascade.execute` is the one path to a typed answer,
and stubbing it out here would leave this plugin's own reading of the cascade's answer
untested.

`out.origin == in.origin` is asserted, per this pack's own recorded obligation
(`weft_retrieve.payload.QuerySet.origin`'s docstring).
"""

from collections.abc import Mapping

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, Outcome, Produced
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_retrieve.contract import Reranker, StageLookup
from weft_retrieve.graded import NAME, GradedRetrieval, GradedRetrievalConfig
from weft_retrieve.payload import Passage, Query, Ranking
from weft_retrieve.prompts import RELEVANCE_GRADE_NAME, Grade, RelevanceGradePrompt
from weft_store.contract import Scored


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script, one reply per batch call."""

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
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own prompt, recording what was asked for."""

    def __init__(self) -> None:
        self._prompts = {RELEVANCE_GRADE_NAME: RelevanceGradePrompt()}
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


def _passage(content: str, rank: int, retrieved_by: str = "vector-top-k") -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Passage(
        scored=Scored(value=node, score=1.0 - rank / 10), rank=rank, retrieved_by=retrieved_by
    )


def _ranking(*contents: str) -> Ranking:
    asked = Query(text="what caused the 2003 blackout?")
    hits = tuple(_passage(content, rank) for rank, content in enumerate(contents))
    return Ranking(origin=asked, hits=hits, contributors=("vector-top-k:vector",))


def _grades_json(*grades: tuple[int, str]) -> str:
    body = ", ".join(f'{{"index": {index}, "grade": "{grade}"}}' for index, grade in grades)
    return f'{{"grades": [{body}]}}'


# --------------------------------------------------------------------------------------
# Happy path — two batches, one grade below the floor filtered out.
# --------------------------------------------------------------------------------------


async def test_kept_hits_survive_below_floor_ones_are_dropped_and_renumbered() -> None:
    # Arrange — `batch=2` splits three hits into two calls: the first grades "overloaded"
    # relevant and "off topic" irrelevant, the second grades "FirstEnergy" ambiguous, which
    # the default floor (RELEVANT) does not clear either.
    payload = _ranking("overloaded", "off topic", "FirstEnergy")
    llm = _StubLLM(
        [
            _grades_json((0, "relevant"), (1, "irrelevant")),
            _grades_json((0, "ambiguous")),
        ]
    )
    lookup = _StubLookup()
    config = GradedRetrievalConfig(batch=2)

    # Act
    outcome = await GradedRetrieval(config).run(payload, _ctx(_services(llm, lookup)))

    # Assert
    assert isinstance(outcome, Produced)
    ranking: Ranking = outcome.value
    assert ranking.origin == payload.origin
    assert [passage.node.content for passage in ranking.hits] == ["overloaded"]
    assert [passage.rank for passage in ranking.hits] == [0]
    assert ranking.contributors == payload.contributors
    assert llm.calls == 2
    # The prompt is resolved once and reused across every batch, not once per batch — the
    # same "ask once, call the cascade per unit of work" split `weft_retrieve.iterative`'s
    # own `leaf`/`sufficiency` resolution takes.
    assert lookup.asked == [RELEVANCE_GRADE_NAME]


async def test_keep_at_or_above_ambiguous_keeps_the_ambiguous_hit_too() -> None:
    # Arrange — a lower floor is a document edit, not a code edit: the same "FirstEnergy"
    # grade from the test above now clears the (retuned) floor.
    payload = _ranking("overloaded", "FirstEnergy")
    llm = _StubLLM([_grades_json((0, "relevant"), (1, "ambiguous"))])

    # Act
    outcome = await GradedRetrieval(GradedRetrievalConfig(keep_at_or_above=Grade.AMBIGUOUS)).run(
        payload, _ctx(_services(llm, _StubLookup()))
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["overloaded", "FirstEnergy"]


# --------------------------------------------------------------------------------------
# Edge case — the emptiness rule, and `cost_bound`'s floor of one describing the non-empty
# case only.
# --------------------------------------------------------------------------------------


async def test_an_empty_ranking_comes_back_untouched_without_asking_a_model() -> None:
    asked = Query(text="a question this corpus has no answer for")
    payload = Ranking(origin=asked, hits=(), contributors=("vector-top-k:vector",))
    llm = _StubLLM(["never asked"])

    outcome = await GradedRetrieval().run(payload, _ctx(_services(llm, _StubLookup())))

    assert isinstance(outcome, Produced)
    assert outcome.value == payload
    assert llm.calls == 0


async def test_max_graded_caps_how_many_hits_are_ever_offered() -> None:
    # Arrange — five hits, `max_graded=2`: only the top two are ever sent to the model, and
    # the other three do not survive even though nothing ever graded them.
    payload = _ranking("first", "second", "third", "fourth", "fifth")
    llm = _StubLLM([_grades_json((0, "relevant"), (1, "relevant"))])

    # Act
    outcome = await GradedRetrieval(GradedRetrievalConfig(max_graded=2, batch=5)).run(
        payload, _ctx(_services(llm, _StubLookup()))
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["first", "second"]
    assert llm.calls == 1


# --------------------------------------------------------------------------------------
# Error case — a batch not graded exactly once per offered passage is refused by name.
# --------------------------------------------------------------------------------------


async def test_a_grade_set_that_is_not_one_per_passage_is_refused_by_name() -> None:
    payload = _ranking("first", "second")
    llm = _StubLLM([_grades_json((0, "relevant"), (7, "relevant"))])

    outcome = await GradedRetrieval().run(payload, _ctx(_services(llm, _StubLookup())))

    assert isinstance(outcome, Failed)
    assert NAME in outcome.reason
    assert "7" in outcome.reason


# --------------------------------------------------------------------------------------
# Seam and configuration.
# --------------------------------------------------------------------------------------


async def test_driving_graded_retrieval_through_the_seam_filters_a_ranking() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call."""
    payload = _ranking("only candidate")
    llm = _StubLLM([_grades_json((0, "relevant"))])
    reranker = GradedRetrieval()
    wrapped = wrap(reranker.run, distribution="weft-retrieve", contract="Reranker", plugin=NAME)

    outcome = await wrapped(payload, _ctx(_services(llm, _StubLookup())))

    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["only candidate"]
    assert isinstance(reranker, Reranker)


def test_the_prompt_role_and_floor_are_configuration_rather_than_constants() -> None:
    config = GradedRetrievalConfig(
        prompt="my-own-grader", role="cheap", keep_at_or_above=Grade.IRRELEVANT
    )

    assert (config.prompt, config.role, config.keep_at_or_above) == (
        "my-own-grader",
        "cheap",
        Grade.IRRELEVANT,
    )
    assert GradedRetrievalConfig().prompt == RELEVANCE_GRADE_NAME
    assert GradedRetrieval.config_model is GradedRetrievalConfig


def test_the_declared_cost_bound_is_one_to_four() -> None:
    # `ceil(max_graded=20 / batch=5) = 4` at the ceiling, one batch at the floor — see
    # `GradedRetrieval`'s own docstring for the empty-ranking edge case this tuple does not
    # describe (checked above, at zero calls).
    assert GradedRetrieval.cost_bound == (1, 4)
