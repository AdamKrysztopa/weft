"""A judge metric counts the questions a rung failed as excluded — carried repair **R44.11**.

`score_generation_gate_subset` folds a rung's failed questions into each aggregate as excluded
(R38.12), and `score_named_generation_metrics` — which scores the judges, `answer_correctness`
among them — did not. E2's `iterative` arm failed 266 of 600 questions and reported
`answer_correctness` as `n=334, excluded=0`: a survivor mean with nothing saying so. A failed
question is excluded and counted, never absent (`09` V4).
"""

from __future__ import annotations

from typing import ClassVar

from weft_eval.contract import GenerationMetric, GenerationSample, MetricScore
from weft_eval.harness import score_named_generation_metrics
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_llm.errors import LLMGenerationLoopError


class _Always:
    """A judge stand-in scoring every answer 1.0."""

    runs_in_gate: ClassVar[bool] = False

    def __init__(self, config: object = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del payload, ctx
        return Produced(value=MetricScore(metric_name="always", value=1.0))


def _sample(query: str) -> GenerationSample:
    return GenerationSample(query=query, prediction="an answer", reference="the answer")


async def test_a_question_the_rung_failed_is_counted_as_excluded() -> None:
    # Arrange
    registry = Registry()
    registry.add(GenerationMetric, "always", _Always, distribution="weft-eval")
    samples = [("q-1", _sample("one")), ("q-2", _sample("two"))]

    # Act
    scores = await score_named_generation_metrics(
        registry,
        ("always",),
        samples,
        ctx=Context(tenant_id="t", run_id="r", trace_id="x", locale="en"),
        failed_questions={"q-3": "'single-list' fuses nothing and was handed 3 lists"},
    )

    # Assert
    [aggregate] = scores.metrics.values()
    assert isinstance(aggregate, Produced)
    assert (aggregate.value.n, aggregate.value.excluded) == (2, 1)
    [per_question] = scores.per_question.values()
    assert set(per_question) == {"q-1", "q-2", "q-3"}
    assert not isinstance(per_question["q-3"], Produced)


class _LoopsOnOne:
    """A judge stand-in the loop-breaker stops on one answer and not the others — R44.12."""

    runs_in_gate: ClassVar[bool] = False

    def __init__(self, config: object = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if payload.query == "loops":
            raise LLMGenerationLoopError(
                "was generating a repeating span", provider="openai", model="gpt"
            )
        return Produced(value=MetricScore(metric_name="loops-on-one", value=1.0))


async def test_a_judge_that_loops_on_one_answer_excludes_that_question_and_goes_on() -> None:
    # Arrange — E3's third arm answered 910 questions and died judging one of them.
    registry = Registry()
    registry.add(GenerationMetric, "loops-on-one", _LoopsOnOne, distribution="weft-eval")
    samples = [("q-1", _sample("one")), ("q-2", _sample("loops")), ("q-3", _sample("three"))]

    # Act
    scores = await score_named_generation_metrics(
        registry,
        ("loops-on-one",),
        samples,
        ctx=Context(tenant_id="t", run_id="r", trace_id="x", locale="en"),
    )

    # Assert
    [aggregate] = scores.metrics.values()
    assert isinstance(aggregate, Produced)
    assert (aggregate.value.n, aggregate.value.excluded) == (2, 1)
    [per_question] = scores.per_question.values()
    assert isinstance(per_question["q-1"], Produced)
    assert not isinstance(per_question["q-2"], Produced)
    assert "repeating span" in str(per_question["q-2"])
