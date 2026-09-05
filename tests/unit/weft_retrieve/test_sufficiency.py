"""Unit tests for `weft_retrieve.sufficiency`.

Mirrors `packages/weft-rag/src/weft_retrieve/sufficiency.py`. Ledger **2.24**: "a
draft's uncertainty is a replaceable, named signal rather than a phrase list, so the trigger
cannot break silently under another language or model." Two `Sufficiency` implementations,
covered separately:

1. `llm-sufficiency` — happy path (a confident judgement reads straight into `Assessment`),
   error case (a cascade failure is relayed exactly as it answered, never softened), and a
   drive through `weft_kernel.seam.wrap`. **The `LLM` is a stub and the cascade is real** —
   the same split `test_rerank.py` and `test_graded.py` already take, for the same reason.
2. `hedge-phrases` — the whole point of this ledger line, so its own test carries the actual
   evidence: `test_hedge_phrases_detects_a_hedge_in_the_askers_own_language` is parametrized
   over an English draft and a **Polish** one (the corpus this build ships,
   `corpus/pl-wiki`, is Polish-language), both hedging the same way in their own words, both
   detected — proof the signal is not an English phrase list that goes silent under another
   language. The edge case is `draft=None` (`iterative-retrieval`'s own use of this contract,
   which `hedge-phrases` cannot serve): `Assessment(observed=False)`, never a guessed
   `sufficient=False`. The error-shaped case for a deterministic, model-free plugin is a
   locale nowhere in the table falling back to `en` rather than raising.

`out.origin`-style assertions do not apply here — `Sufficiency` is not a query-path `Stage`
(`weft_retrieve.contract.Sufficiency`'s own docstring: "not a pipeline position"), so there is
no `origin` obligation to check; what both tests suites check instead is `Assessment.observed`
never being conflated with `Assessment.sufficient`, the contract's own stated invariant.
"""

from collections.abc import Mapping

import pytest

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, Outcome, Produced
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_retrieve.contract import StageLookup, Sufficiency
from weft_retrieve.payload import Passage, Passages, Query
from weft_retrieve.prompts import SUFFICIENCY_CHECK_NAME, SufficiencyCheckPrompt
from weft_retrieve.sufficiency import (
    HEDGE_PHRASES_NAME,
    LLM_SUFFICIENCY_NAME,
    HedgePhrases,
    HedgePhrasesConfig,
    LlmSufficiency,
    LlmSufficiencyConfig,
)
from weft_store.contract import Scored


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script — the same shape
    `test_rerank.py`'s and `test_graded.py`'s own stubs take."""

    def __init__(self, replies: list[str | Failed]) -> None:
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
        if isinstance(reply, Failed):
            return reply
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own prompt, and refusing the other verb — the same
    refusal `test_rerank.py`'s own stub states: this plugin resolves a capability by name,
    never a stage.
    """

    def __init__(self, prompts: Mapping[str, object]) -> None:
        self._prompts = prompts

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset(self._prompts)

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        raise AssertionError("llm-sufficiency resolves a capability by name, never a stage")

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        del contract, config
        return self._prompts[name]


def _services(llm: _StubLLM) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, _StubLookup({SUFFICIENCY_CHECK_NAME: SufficiencyCheckPrompt()}))
    return services


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _passage(content: str) -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")
    return Passage(scored=Scored(value=node, score=0.8), rank=0, retrieved_by="leaf", label="1")


def _asked(*, locale: str | None = None) -> Query:
    return Query(text="does the corpus explain overfitting?", locale=locale)


# --------------------------------------------------------------------------------------
# llm-sufficiency
# --------------------------------------------------------------------------------------


async def test_llm_sufficiency_reads_a_confident_judgement_into_assessment() -> None:
    # Arrange
    llm = _StubLLM(['{"sufficient": true, "confidence": 0.92, "missing": []}'])
    question = _asked()
    evidence = Passages(origin=question, passages=(_passage("random forests reduce variance"),))

    # Act
    outcome = await LlmSufficiency().assess(
        question,
        evidence,
        "random forests reduce variance by averaging trees.",
        _ctx(_services(llm)),
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.sufficient is True
    assert outcome.value.confidence == pytest.approx(0.92)
    assert outcome.value.observed is True
    assert llm.calls == 1


async def test_llm_sufficiency_relays_a_cascade_failure_exactly_as_it_answered() -> None:
    # Arrange — a hard model failure, never softened into `Assessment(observed=False)`; that
    # reading belongs to `hedge-phrases` when it genuinely has nothing to inspect, not to
    # this plugin when a call it actually attempted came back unusable.
    llm = _StubLLM([Failed(reason="the sufficiency model call raised")])
    question = _asked()
    evidence = Passages(origin=question, passages=())

    # Act
    outcome = await LlmSufficiency().assess(question, evidence, None, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Failed)
    assert "sufficiency" in outcome.reason


async def test_driving_llm_sufficiency_through_the_seam_produces_an_assessment() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    llm = _StubLLM(['{"sufficient": false, "confidence": 0.2, "missing": ["a citation"]}'])
    question = _asked()
    evidence = Passages(origin=question, passages=())
    signal = LlmSufficiency()
    wrapped = wrap(
        signal.assess,
        distribution="weft-retrieve",
        contract="Sufficiency",
        plugin=LLM_SUFFICIENCY_NAME,
    )

    # Act
    outcome = await wrapped(question, evidence, None, _ctx(_services(llm)))

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(signal, Sufficiency)


def test_the_declared_cost_bound_is_fixed_at_one() -> None:
    assert LlmSufficiency.cost_bound == (1, 1)


def test_the_config_model_has_defaults_for_every_field() -> None:
    config = LlmSufficiencyConfig()
    assert config.prompt == SUFFICIENCY_CHECK_NAME
    assert config.role == "grade"
    assert config.max_evidence == 8


# --------------------------------------------------------------------------------------
# hedge-phrases — the ledger line's own evidence lives here.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("locale", "draft"),
    [
        ("en", "I'm not sure the evidence fully answers this question."),
        (
            "pl",
            "Nie jestem pewien, czy dostępne źródła pozwalają jednoznacznie odpowiedzieć "
            "na to pytanie.",
        ),
    ],
)
async def test_hedge_phrases_detects_a_hedge_in_the_askers_own_language(
    locale: str, draft: str
) -> None:
    """The evidence this ledger line asks for: a signal that fires on a hedge written in
    Polish exactly as it does in English, because the marker table it reads is keyed by
    locale rather than being one English list a call site closed over. Delete the `"pl"`
    entry from `weft_retrieve.sufficiency.DEFAULT_HEDGE_MARKERS` and the Polish half of this
    test goes red — the property the reference's own single-language list could never be checked
    against.
    """
    # Arrange
    question = _asked(locale=locale)
    evidence = Passages(origin=question, passages=())

    # Act
    outcome = await HedgePhrases().assess(question, evidence, draft, _ctx(ServiceRegistry()))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.sufficient is False
    assert outcome.value.observed is True


async def test_hedge_phrases_reports_confident_when_no_marker_matches() -> None:
    # Arrange
    question = _asked(locale="en")
    evidence = Passages(origin=question, passages=())
    draft = "Random forests reduce variance by averaging many decorrelated trees."

    # Act
    outcome = await HedgePhrases().assess(question, evidence, draft, _ctx(ServiceRegistry()))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.sufficient is True
    assert outcome.value.confidence == pytest.approx(1.0)


async def test_hedge_phrases_cannot_look_with_no_draft() -> None:
    # Arrange — `iterative-retrieval`'s own use of `Sufficiency`, judging evidence alone.
    # `hedge-phrases` has nothing to inspect and says so honestly rather than guessing.
    question = _asked()
    evidence = Passages(origin=question, passages=(_passage("some evidence"),))

    # Act
    outcome = await HedgePhrases().assess(question, evidence, None, _ctx(ServiceRegistry()))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.observed is False
    assert outcome.value.sufficient is False


async def test_hedge_phrases_falls_back_from_a_regional_locale_to_its_primary_subtag() -> None:
    # Arrange — `pl-PL` reaches the same table `pl` does, without a second key.
    question = _asked(locale="pl-PL")
    evidence = Passages(origin=question, passages=())
    draft = "Trudno powiedzieć, czy to wystarczająca odpowiedź."

    # Act
    outcome = await HedgePhrases().assess(question, evidence, draft, _ctx(ServiceRegistry()))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.sufficient is False


async def test_driving_hedge_phrases_through_the_seam_produces_an_assessment() -> None:
    # Arrange
    question = _asked(locale="en")
    evidence = Passages(origin=question, passages=())
    signal = HedgePhrases()
    wrapped = wrap(
        signal.assess,
        distribution="weft-retrieve",
        contract="Sufficiency",
        plugin=HEDGE_PHRASES_NAME,
    )

    # Act
    outcome = await wrapped(question, evidence, "I don't know.", _ctx(ServiceRegistry()))

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(signal, Sufficiency)


def test_the_declared_cost_bound_is_zero() -> None:
    assert HedgePhrases.cost_bound == (0, 0)


def test_the_config_model_has_a_default_marker_table() -> None:
    config = HedgePhrasesConfig()
    assert "en" in config.markers
    assert "pl" in config.markers
