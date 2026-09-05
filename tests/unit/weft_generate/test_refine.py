"""Unit tests for `weft_generate.refine`.

Mirrors `packages/weft-rag/src/weft_generate/refine.py`. Ledger **2.24**: "a draft's
uncertainty is a replaceable, named signal rather than a phrase list, so the trigger cannot
break silently under another language or model." This module covers:

1. `refinement_stop` directly, with a hand-built `Assessment` — the same "testable on its
   own" shape `weft_retrieve.iterative.stop_reason`'s own test module already establishes,
   for the identical reason: a reader should not have to drive the whole loop through two
   fake services to know what stops it.
2. The loop itself: the happy path (confident on the first draft, one round, no retrieval),
   the edge case (insufficient once, a retriever hands back genuinely new evidence, confident
   on the second draft), a `NO_NEW_EVIDENCE` stop, a `MAX_ROUNDS` ceiling, the error case (a
   hard `on_signal_failure=FAIL` propagates rather than being read as "good enough" — the same
   defect this pack has already fixed once, on `weft_retrieve.iterative`), and a
   drive through `weft_kernel.seam.wrap`.
3. **`test_a_real_hedge_phrases_signal_triggers_a_redraft_on_a_polish_hedge`** — the actual
   evidence this ledger line asks for. `signal="hedge-phrases"` resolves, through the same
   `StageLookup` seam a document would use, to the *real* `weft_retrieve.sufficiency.
   HedgePhrases` — not a test double standing in for it — and a first draft written in
   Polish that hedges ("Nie jestem pewien …") is what triggers the extra round, exactly the
   way a fluent English hedge would. `corpus/pl-wiki` is this build's own Polish corpus, and
   the passages below are written about the same subject (`las-losowy` — random forests) a
   reader of that corpus would actually ask about. Delete `hedge-phrases`'s own `"pl"` marker
   table entry and this test goes red — a single-language mechanism could never have been
   checked against that failure, only assumed correct.

**The `LLM` is a stub and `Prompt.render` is real** — the same split `test_cited_answer.py`
and `test_contradiction.py` already take.

`out.origin == in.origin` (as `Answer.origin`) is asserted in every test that produces an
`Answer`, the obligation every plugin closing the query path carries.
"""

import pytest

from weft_generate.contract import Generator
from weft_generate.payload import AnswerStance
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt
from weft_generate.refine import (
    NAME,
    RefinementStop,
    RefineOnUncertainty,
    RefineOnUncertaintyConfig,
    refinement_stop,
)
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, Outcome, Produced
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_retrieve.contract import Retriever, StageLookup, Sufficiency
from weft_retrieve.payload import (
    Assessment,
    Candidates,
    Passage,
    Passages,
    Query,
    QuerySet,
    RankedList,
)
from weft_retrieve.sufficiency import HedgePhrases
from weft_store.contract import NodeStore, Scored, SourceRecord


class _StubLLM:
    """An `LLM` answering from a script, one reply per `complete` call — the same shape
    `test_cited_answer.py`'s and `test_contradiction.py`'s own stubs take."""

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


class _FakeSignal:
    """A `Sufficiency`, scripted one `Outcome[Assessment]` per call — the same repeat-last
    shape `test_iterative.py`'s own `_FakeSufficiency` takes."""

    def __init__(self, outcomes: list[Outcome[Assessment]]) -> None:
        self._outcomes = outcomes
        self.drafts_seen: list[str | None] = []

    async def assess(
        self, question: Query, evidence: Passages, draft: str | None, ctx: Context
    ) -> Outcome[Assessment]:
        del question, evidence, ctx
        self.drafts_seen.append(draft)
        return self._outcomes[min(len(self.drafts_seen) - 1, len(self._outcomes) - 1)]


class _FakeRetriever:
    """A `Retriever`-shaped callable, scripted one `Outcome[Candidates]` per call."""

    def __init__(self, outcomes: list[Outcome[Candidates]]) -> None:
        self._outcomes = outcomes
        self.calls: list[QuerySet] = []

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        self.calls.append(payload)
        return self._outcomes[min(len(self.calls) - 1, len(self._outcomes) - 1)]


class _StubLookup:
    """A `StageLookup` handing back one prompt, one signal and one retriever, dispatched by
    the contract asked for — the same dispatch-by-contract shape `test_iterative.py`'s own
    stub takes for `leaf`/`sufficiency`.
    """

    def __init__(self, signal: object, retriever: _FakeRetriever) -> None:
        self._signal = signal
        self._retriever = retriever
        self.signal_config: object = None
        self.retriever_config: object = None

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset()

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        assert contract is Retriever
        self.retriever_config = config
        return self._retriever.run

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        if contract is Sufficiency:
            self.signal_config = config
            return self._signal
        assert name == ANSWER_WITH_CITATIONS_NAME
        return AnswerWithCitationsPrompt()


class _StubStore:
    """A `NodeStore` with nothing registered — every citation resolves to an empty `uri`."""

    async def get_source(self, source_id: object) -> SourceRecord | None:
        del source_id
        return None


def _services(llm: _StubLLM, signal: object, retriever: _FakeRetriever) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, _StubLookup(signal, retriever))
    services.add(NodeStore, _StubStore())
    return services


def _ctx(services: ServiceRegistry, *, locale: str = "en") -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale=locale, services=services
    )


def _passage(label: str, content: str) -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")
    return Passage(
        scored=Scored(value=node, score=0.7), rank=0, retrieved_by="vector-top-k", label=label
    )


def _asked(*, locale: str | None = None) -> Query:
    return Query(text="does the corpus explain overfitting?", locale=locale)


def _assessment(*, sufficient: bool, confidence: float = 0.9, observed: bool = True) -> Assessment:
    return Assessment(sufficient=sufficient, confidence=confidence, missing=(), observed=observed)


def _candidates(origin: Query, *contents: str) -> Candidates:
    hits = tuple(_passage("", content) for content in contents)
    query = Query(text=origin.text, origin=origin.origin, locale=origin.locale)
    return Candidates(origin=origin, lists=(RankedList(query=query, retriever="fake", hits=hits),))


# --------------------------------------------------------------------------------------
# refinement_stop — driven directly, never by running the loop.
# --------------------------------------------------------------------------------------


def test_refinement_stop_reports_confident_at_or_above_threshold() -> None:
    assessment = _assessment(sufficient=True, confidence=0.8)
    assert (
        refinement_stop(round=1, max_rounds=1, assessment=assessment, threshold=0.5)
        is RefinementStop.CONFIDENT
    )


def test_refinement_stop_does_not_report_confident_below_threshold() -> None:
    assessment = _assessment(sufficient=True, confidence=0.2)
    assert refinement_stop(round=1, max_rounds=1, assessment=assessment, threshold=0.5) is None


def test_refinement_stop_reports_max_rounds_once_the_ceiling_is_reached() -> None:
    assessment = _assessment(sufficient=False, confidence=0.1)
    assert (
        refinement_stop(round=2, max_rounds=1, assessment=assessment, threshold=0.5)
        is RefinementStop.MAX_ROUNDS
    )


def test_refinement_stop_reports_signal_unobserved_before_the_floor_or_ceiling() -> None:
    assessment = _assessment(sufficient=False, observed=False)
    assert (
        refinement_stop(round=2, max_rounds=1, assessment=assessment, threshold=0.5)
        is RefinementStop.SIGNAL_UNOBSERVED
    )


# --------------------------------------------------------------------------------------
# The loop itself.
# --------------------------------------------------------------------------------------


async def test_a_confident_first_draft_stops_after_one_round_with_no_retrieval() -> None:
    # Arrange
    origin = _asked()
    passages = Passages(origin=origin, passages=(_passage("1", "random forests average trees"),))
    llm = _StubLLM(["Random forests average many trees [1]."])
    signal = _FakeSignal([Produced(value=_assessment(sufficient=True, confidence=0.9))])
    retriever = _FakeRetriever([Produced(value=_candidates(origin))])

    # Act
    outcome = await RefineOnUncertainty().run(passages, _ctx(_services(llm, signal, retriever)))

    # Assert
    assert isinstance(outcome, Produced)
    answer = outcome.value
    assert answer.origin == origin
    assert answer.stance is AnswerStance.ANSWERED
    assert [citation.marker for citation in answer.citations] == ["1"]
    assert llm.calls == 1
    assert retriever.calls == []
    assert signal.drafts_seen == ["Random forests average many trees [1]."]


async def test_an_insufficient_first_draft_retrieves_and_redrafts_until_confident() -> None:
    # Arrange — round 1 is insufficient; the retriever hands back one genuinely new passage;
    # round 2's draft is confident.
    origin = _asked()
    passages = Passages(origin=origin, passages=(_passage("1", "random forests average trees"),))
    llm = _StubLLM(
        [
            "I'm not sure this fully answers it [1].",
            "Random forests reduce variance by averaging decorrelated trees [1] [2].",
        ]
    )
    signal = _FakeSignal(
        [
            Produced(value=_assessment(sufficient=False, confidence=0.2)),
            Produced(value=_assessment(sufficient=True, confidence=0.9)),
        ]
    )
    retriever = _FakeRetriever([Produced(value=_candidates(origin, "variance reduction detail"))])
    config = RefineOnUncertaintyConfig(max_rounds=1)

    # Act
    outcome = await RefineOnUncertainty(config).run(
        passages, _ctx(_services(llm, signal, retriever))
    )

    # Assert
    assert isinstance(outcome, Produced)
    answer = outcome.value
    assert answer.origin == origin
    assert llm.calls == 2
    assert len(retriever.calls) == 1
    # The retrieval round searched with a *derived* query, never the original re-sent as-is,
    # built from what the signal said was missing (empty here, so it falls back to the
    # question's own text) — but it is still its own `Query`, distinct from `origin`.
    assert retriever.calls[0].origin == origin
    assert [citation.marker for citation in answer.citations] == ["1", "2"]


async def test_no_new_evidence_stops_the_loop_before_max_rounds() -> None:
    # Arrange — the retriever hands back exactly the passage already in hand, so redrafting
    # against it again would not change what the signal has to judge.
    origin = _asked()
    seed = _passage("1", "random forests average trees")
    passages = Passages(origin=origin, passages=(seed,))
    llm = _StubLLM(["I'm not sure [1]."])
    signal = _FakeSignal([Produced(value=_assessment(sufficient=False, confidence=0.1))])
    retriever = _FakeRetriever(
        [
            Produced(
                value=Candidates(
                    origin=origin, lists=(RankedList(query=origin, retriever="fake", hits=(seed,)),)
                )
            )
        ]
    )
    config = RefineOnUncertaintyConfig(max_rounds=3)

    # Act
    outcome = await RefineOnUncertainty(config).run(
        passages, _ctx(_services(llm, signal, retriever))
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert llm.calls == 1
    assert len(retriever.calls) == 1


async def test_the_loop_never_exceeds_max_rounds() -> None:
    # Arrange — a signal that never says sufficient, and a retriever that always hands back
    # fresh evidence, so nothing but the configured ceiling can stop this loop.
    origin = _asked()
    passages = Passages(origin=origin, passages=(_passage("1", "seed"),))
    llm = _StubLLM(["still not sure"])
    signal = _FakeSignal([Produced(value=_assessment(sufficient=False, confidence=0.1))])
    retriever = _FakeRetriever(
        [Produced(value=_candidates(origin, f"fresh evidence #{index}")) for index in range(10)]
    )
    config = RefineOnUncertaintyConfig(max_rounds=2)

    # Act
    outcome = await RefineOnUncertainty(config).run(
        passages, _ctx(_services(llm, signal, retriever))
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert llm.calls == 3  # one draft per round: max_rounds (2) extra rounds + the first
    assert len(retriever.calls) == 2


async def test_a_hard_signal_failure_fails_the_whole_generation() -> None:
    # Arrange — `on_signal_failure` defaults `FAIL`: relaying the signal's own outcome *is*
    # failing loudly, the same fix `weft_retrieve.iterative`'s own `on_critic_failure` makes.
    origin = _asked()
    passages = Passages(origin=origin, passages=(_passage("1", "seed"),))
    llm = _StubLLM(["a draft"])
    signal = _FakeSignal([Failed(reason="the signal's own model call raised")])
    retriever = _FakeRetriever([Produced(value=_candidates(origin))])

    # Act
    outcome = await RefineOnUncertainty().run(passages, _ctx(_services(llm, signal, retriever)))

    # Assert
    assert isinstance(outcome, Failed)
    assert "signal" in outcome.reason


async def test_driving_refine_on_uncertainty_through_the_seam_produces_an_answer() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call."""
    # Arrange
    origin = _asked()
    passages = Passages(origin=origin, passages=(_passage("1", "seed"),))
    llm = _StubLLM(["a confident draft [1]."])
    signal = _FakeSignal([Produced(value=_assessment(sufficient=True, confidence=0.9))])
    retriever = _FakeRetriever([Produced(value=_candidates(origin))])
    generator = RefineOnUncertainty()
    wrapped = wrap(generator.run, distribution="weft-generate", contract="Generator", plugin=NAME)

    # Act
    outcome = await wrapped(passages, _ctx(_services(llm, signal, retriever)))

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(generator, Generator)


def test_the_declared_cost_bound_is_two_to_four() -> None:
    assert RefineOnUncertainty.cost_bound == (2, 4)


def test_the_config_model_has_defaults_for_every_field() -> None:
    config = RefineOnUncertaintyConfig()
    assert config.signal == "llm-sufficiency"
    assert config.retriever == "vector-top-k"
    assert config.threshold == pytest.approx(0.5)
    assert config.max_rounds == 1


# --------------------------------------------------------------------------------------
# The ledger line's own evidence: a *real* Sufficiency implementation, swapped in by name,
# correctly triggering a refinement round on a non-English draft.
# --------------------------------------------------------------------------------------


async def test_a_real_hedge_phrases_signal_triggers_a_redraft_on_a_polish_hedge() -> None:
    """`signal: hedge-phrases` resolves to `weft_retrieve.sufficiency.HedgePhrases` itself —
    not a fake standing in for it — through the same `StageLookup.build_capability` seam a
    real pipeline document would use. The first draft is written in Polish and hedges
    ("Nie jestem pewien …"); `HedgePhrases`'s own `"pl"` marker table is what recognises
    that, exactly the way its `"en"` table would recognise the English equivalent, which is
    the whole property a hard-coded English phrase list could never have had. Passage
    content mirrors `corpus/pl-wiki/las-losowy.md`'s own subject (random forests), this
    build's actual Polish corpus.
    """
    # Arrange
    origin = Query(text="Czy las losowy redukuje wariancję?", locale="pl")
    passages = Passages(
        origin=origin, passages=(_passage("1", "Las losowy łączy wiele drzew decyzyjnych."),)
    )
    llm = _StubLLM(
        [
            "Nie jestem pewien, czy dostępne źródła jednoznacznie odpowiadają na to pytanie.",
            "Las losowy redukuje wariancję przez uśrednianie wielu nieskorelowanych drzew [1].",
        ]
    )
    retriever = _FakeRetriever(
        [Produced(value=_candidates(origin, "dodatkowy fragment o baggingu"))]
    )
    config = RefineOnUncertaintyConfig(signal="hedge-phrases", max_rounds=1)

    # Act — `HedgePhrases()`, the real plugin class, stands in for whatever `StageLookup`
    # would resolve `"hedge-phrases"` to in a running pipeline.
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, _StubLookup(HedgePhrases(), retriever))
    services.add(NodeStore, _StubStore())
    outcome = await RefineOnUncertainty(config).run(passages, _ctx(services, locale="pl"))

    # Assert — the Polish hedge in round one is what forced the second round: without a real
    # `Sufficiency` reading the draft's own Polish wording, this would have stopped after one
    # call, exactly as an English-only mechanism would have stopped at the wrong moment for
    # the wrong reason.
    assert isinstance(outcome, Produced)
    assert llm.calls == 2
    assert len(retriever.calls) == 1
    assert outcome.value.text.startswith("Las losowy redukuje wariancję")
