"""This pack's own tests — the fourth canonical file `docs/07-extension-cost.md` names.

Exercises `ExactMatch` directly, the same way `weft-example-chunker`'s own suite exercises
`WordChunker`: against real `GenerationSample` inputs, no double standing in for the kernel it
depends on.
**Collected by weft's own gate since its ledger task 6.23**, through the `examples-tests` step —
a suite no task runs is prose, and two tests in this tree were quietly red for exactly that
reason. Still runnable on its own with `uv run pytest` from inside this directory, which is how
a stranger runs it.
"""

from weft_example_metric.exact_match import ExactMatch, ExactMatchConfig

from weft_eval.contract import GenerationMetric, GenerationSample
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_exact_match_scores_one_on_an_identical_prediction() -> None:
    # Arrange
    metric = ExactMatch()
    sample = GenerationSample(query="q", prediction="Paris", reference="Paris")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1.0


async def test_case_insensitive_config_matches_regardless_of_case() -> None:
    # Arrange — the typed configuration model, exercised from entirely outside the workspace.
    metric = ExactMatch(ExactMatchConfig(case_sensitive=False))
    sample = GenerationSample(query="q", prediction="paris", reference="Paris")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1.0


async def test_empty_reference_is_nothing_to_produce() -> None:
    # Arrange
    metric = ExactMatch()
    sample = GenerationSample(query="q", prediction="anything", reference="")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_no_prediction_fails_rather_than_scoring_zero() -> None:
    # Arrange
    metric = ExactMatch()
    sample = GenerationSample(query="q", prediction=None, reference="Paris")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Failed)


def test_exact_match_satisfies_the_metric_contract_structurally() -> None:
    # Act / Assert — no import of GenerationMetric in exact_match.py itself; this is the
    # caller's check.
    assert isinstance(ExactMatch(), GenerationMetric)
