"""This pack's own tests for `ExampleQueryScorer`."""

from weft_example_query.scorer import ExampleQueryScorer

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import QueryScorer
from weft_retrieve.payload import Query


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_scorer_reports_higher_complexity_for_a_longer_query_through_the_seam() -> None:
    # Arrange
    scorer = ExampleQueryScorer()
    wrapped = wrap(
        scorer.run,
        distribution="weft-example-query",
        contract="QueryScorer",
        plugin="example-length-heuristic",
    )
    short = Query(text="weft")
    long = Query(text=" ".join(["word"] * 30))

    # Act
    short_outcome = await wrapped(short, _ctx())
    long_outcome = await scorer.run(long, _ctx())

    # Assert — every score is a fraction, and `Scorecard`'s own validator would have refused
    # anything outside 0.0–1.0.
    assert isinstance(short_outcome, Produced)
    assert isinstance(long_outcome, Produced)
    assert short_outcome.value.scores["complexity"] < long_outcome.value.scores["complexity"]
    assert long_outcome.value.scores["complexity"] == 1.0


async def test_scorer_satisfies_the_queryscorer_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleQueryScorer(), QueryScorer)
