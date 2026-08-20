"""Unit tests for `weft_eval.qa_metrics`.

Mirrors `packages/weft-eval/src/weft_eval/qa_metrics.py`. `ExactMatch` is the one metric in the
whole suite that scores an empty-and-empty pair as a real match rather than `NothingToProduce` —
the module's own module docstring states why, and this file proves it. `F1Score` and `Accuracy`
each get one happy path and one edge/error case.
"""

from weft_eval.contract import GenerationSample
from weft_eval.qa_metrics import Accuracy, ExactMatch, F1Score, NoConfig
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_exact_match_normalizes_case_and_whitespace() -> None:
    # Arrange
    metric = ExactMatch(NoConfig())
    sample = GenerationSample(query="q", prediction="  Paris  ", reference="paris")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1.0


async def test_exact_match_scores_two_empty_strings_as_a_real_match() -> None:
    # Arrange — the one deliberate exception to the suite's "empty reference is NothingToProduce"
    # rule: both sides are present here, and both happen to be empty.
    metric = ExactMatch(NoConfig())
    sample = GenerationSample(query="q", prediction="", reference="")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1.0


async def test_f1_score_partial_token_overlap() -> None:
    # Arrange — prediction {the, capital, of, france}, reference {the, capital, is, paris}:
    # overlap 2 ("the", "capital"), precision 2/4, recall 2/4, F1 0.5.
    metric = F1Score(NoConfig())
    sample = GenerationSample(
        query="q", prediction="the capital of france", reference="the capital is paris"
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 0.5


async def test_f1_score_no_prediction_fails_rather_than_scoring_zero() -> None:
    # Arrange
    metric = F1Score(NoConfig())
    sample = GenerationSample(query="q", prediction=None, reference="paris")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Failed)


async def test_accuracy_scores_the_reference_contained_in_a_longer_prediction() -> None:
    # Arrange — strict exact-match would fail this; accuracy is the looser containment check.
    metric = Accuracy(NoConfig())
    sample = GenerationSample(
        query="q", prediction="I believe the answer is Paris.", reference="paris"
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1.0


async def test_accuracy_empty_reference_is_nothing_to_produce() -> None:
    # Arrange
    metric = Accuracy(NoConfig())
    sample = GenerationSample(query="q", prediction="anything", reference="")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)
