"""This pack's own tests for `ExampleQueryTransform`."""

from weft_example_query.transform import NAME, ExampleQueryTransform

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import QueryTransform
from weft_retrieve.payload import Query, QuerySet


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_transform_adds_a_shouted_variant_through_the_seam() -> None:
    # Arrange
    transform = ExampleQueryTransform()
    wrapped = wrap(
        transform.run, distribution="weft-example-query", contract="QueryTransform", plugin=NAME
    )
    original = Query(text="what is weft")
    payload = QuerySet(origin=original, queries=(original,))

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [q.text for q in outcome.value.queries] == ["what is weft", "WHAT IS WEFT"]
    assert outcome.value.queries[-1].produced_by == NAME


async def test_transform_never_rewrites_origin() -> None:
    # Arrange — the query-path obligation `weft_retrieve.payload.QuerySet` states and
    # nothing checks structurally: every first-party plugin's own test carries it.
    transform = ExampleQueryTransform()
    original = Query(text="what is weft")
    payload = QuerySet(origin=original, queries=(original,))

    # Act
    outcome = await transform.run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.origin == payload.origin


async def test_transform_satisfies_the_querytransform_contract_structurally() -> None:
    # Act / Assert — no import of QueryTransform in transform.py itself.
    assert isinstance(ExampleQueryTransform(), QueryTransform)
