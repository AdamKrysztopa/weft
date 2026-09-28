"""A position-swapped pairwise judge for answers with no single gold — task 44.43a.

Corpus-wide questions have no reference answer, so two arms' answers are compared head to head on
a criterion (GraphRAG's comprehensiveness, diversity and empowerment, with directness as a control).
A judge prefers whichever answer it reads first often enough to matter, so each pair is judged once
in each order, and a verdict that changes with the order is a tie, never a win. The win rate carries
a paired interval over questions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from weft_eval import Settings, register
from weft_eval.pairwise import (
    PairwiseChoice,
    PairwiseCriterion,
    PairwiseVerdict,
    Position,
    Preference,
    judge_pair,
    reconcile,
    summarise,
)
from weft_eval.prompts import PairwiseJudgePrompt
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Failed, Produced
from weft_kernel.registry import Registry
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_prompts.contract import Prompt


class _ScriptedLLM:
    """Answers each call from a script of replies, keeping every prompt it was sent."""

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self.sent: list[Rendered] = []

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> object:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(
        self, rendered: Rendered, *, role: str, ctx: Context
    ) -> Produced[Completion]:
        del role, ctx
        self.sent.append(rendered)
        return Produced(value=Completion(text=self._replies.pop(0), model="scripted"))

    async def close(self) -> None: ...


def _choice(position: Position) -> str:
    return PairwiseChoice(winner=position, reasoning="scripted").model_dump_json()


def _ctx(llm: _ScriptedLLM) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _text(rendered: Rendered) -> str:
    return "\n".join(message.content for message in rendered.conversation.messages)


def test_the_criteria_are_graphrag_s_three_targets_and_its_control() -> None:
    # Assert
    assert {criterion.value for criterion in PairwiseCriterion} == {
        "comprehensiveness",
        "diversity",
        "empowerment",
        "directness",
    }


@pytest.mark.parametrize(
    ("first", "swapped", "outcome"),
    [
        (Preference.A, Preference.A, Preference.A),
        (Preference.B, Preference.B, Preference.B),
        (Preference.TIE, Preference.TIE, Preference.TIE),
        (Preference.A, Preference.B, Preference.TIE),
        (Preference.TIE, Preference.A, Preference.TIE),
    ],
)
def test_a_verdict_stands_only_when_both_orders_agree(
    first: Preference, swapped: Preference, outcome: Preference
) -> None:
    # Assert
    assert reconcile(first, swapped) is outcome


async def test_a_consistent_preference_wins_and_each_order_is_asked() -> None:
    # Arrange — a first, then b first: the judge picks a both times.
    llm = _ScriptedLLM([_choice(Position.FIRST), _choice(Position.SECOND)])

    # Act
    outcome = await judge_pair(
        question_id="g-1",
        question="What themes recur across the collection?",
        answer_a="ANSWER-ALPHA covers dependence and redundancy.",
        answer_b="ANSWER-BETA covers only redundancy.",
        criterion=PairwiseCriterion.COMPREHENSIVENESS,
        ctx=_ctx(llm),
    )

    # Assert
    assert isinstance(outcome, Produced)
    verdict = outcome.value
    assert verdict.outcome is Preference.A
    assert (verdict.first, verdict.swapped) == (Preference.A, Preference.A)
    first_text, second_text = (_text(sent) for sent in llm.sent)
    assert first_text.index("ANSWER-ALPHA") < first_text.index("ANSWER-BETA")
    assert second_text.index("ANSWER-BETA") < second_text.index("ANSWER-ALPHA")
    assert all(sent.prompt == "pairwise-judge" for sent in llm.sent)


async def test_an_order_dependent_judgement_is_a_tie() -> None:
    # Arrange — the judge always picks whichever answer it reads first.
    llm = _ScriptedLLM([_choice(Position.FIRST), _choice(Position.FIRST)])

    # Act
    outcome = await judge_pair(
        question_id="g-1",
        question="Which papers disagree about redundancy?",
        answer_a="ANSWER-ALPHA",
        answer_b="ANSWER-BETA",
        criterion=PairwiseCriterion.DIVERSITY,
        ctx=_ctx(llm),
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.outcome is Preference.TIE
    assert (outcome.value.first, outcome.value.swapped) == (Preference.A, Preference.B)


async def test_an_unreadable_judgement_fails_rather_than_counting_as_a_tie() -> None:
    # Arrange
    llm = _ScriptedLLM(["no json here", "still none", "nor here", "nothing"])

    # Act
    outcome = await judge_pair(
        question_id="g-1",
        question="q",
        answer_a="a",
        answer_b="b",
        criterion=PairwiseCriterion.EMPOWERMENT,
        ctx=_ctx(llm),
    )

    # Assert
    assert isinstance(outcome, Failed)


def _verdict(question_id: str, outcome: Preference) -> PairwiseVerdict:
    return PairwiseVerdict(
        question_id=question_id,
        criterion=PairwiseCriterion.COMPREHENSIVENESS,
        first=outcome,
        swapped=outcome,
        outcome=outcome,
    )


def test_the_win_rate_counts_a_tie_as_half() -> None:
    # Arrange — b wins twice, ties once, loses once.
    verdicts = [
        _verdict("g-1", Preference.B),
        _verdict("g-2", Preference.B),
        _verdict("g-3", Preference.TIE),
        _verdict("g-4", Preference.A),
    ]

    # Act
    summary = summarise(verdicts)

    # Assert
    assert (summary.n, summary.wins_a, summary.wins_b, summary.ties) == (4, 1, 2, 1)
    assert summary.win_rate_b == pytest.approx(0.625)
    assert summary.low is not None and summary.high is not None
    assert summary.low <= summary.win_rate_b <= summary.high


def test_one_question_has_no_interval() -> None:
    # Act
    summary = summarise([_verdict("g-1", Preference.B)])

    # Assert
    assert summary.win_rate_b == pytest.approx(1.0)
    assert summary.low is None and summary.high is None


def test_the_prompt_is_registered_under_its_name() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()

    # Act
    entry = registry.entry(Prompt, "pairwise-judge")

    # Assert
    assert entry.factory is PairwiseJudgePrompt
    assert PairwiseJudgePrompt.output_model is PairwiseChoice


def test_no_verdicts_have_no_win_rate() -> None:
    # Act — R44.6: nothing judged is not a loss.
    summary = summarise([])

    # Assert
    assert summary.n == 0
    assert summary.win_rate_b is None
    assert summary.low is None and summary.high is None
