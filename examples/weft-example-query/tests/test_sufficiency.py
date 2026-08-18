"""This pack's own tests for `ExampleSufficiency`."""

from weft_example_query.sufficiency import ExampleSufficiency

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import Sufficiency
from weft_retrieve.payload import Passage, Passages, Query
from weft_store.contract import Scored


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _labelled_passage(text: str) -> Passage:
    node = Node.synthetic(content=text, media_type=MediaType.TEXT, reason="fixture")
    return Passage(
        scored=Scored(value=node, score=1.0), rank=0, retrieved_by="fixture", label="[1]"
    )


async def test_sufficiency_is_sufficient_with_any_evidence_through_the_seam() -> None:
    # Arrange
    sufficiency = ExampleSufficiency()
    wrapped = wrap(
        sufficiency.assess,
        distribution="weft-example-query",
        contract="Sufficiency",
        plugin="example-any-evidence",
    )
    question = Query(text="what is weft")
    evidence = Passages(origin=question, passages=(_labelled_passage("weft is a rag engine"),))

    # Act
    outcome = await wrapped(question, evidence, None, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.sufficient is True
    assert outcome.value.observed is True
    assert outcome.value.missing == ()


async def test_sufficiency_is_insufficient_and_says_what_is_missing_with_no_evidence() -> None:
    # Arrange
    sufficiency = ExampleSufficiency()
    question = Query(text="what is weft")
    evidence = Passages(origin=question, passages=())

    # Act
    outcome = await sufficiency.assess(question, evidence, None, _ctx())

    # Assert — `observed=True` throughout: this plugin always genuinely looked, so an
    # insufficient verdict is never confused with "I could not tell".
    assert isinstance(outcome, Produced)
    assert outcome.value.sufficient is False
    assert outcome.value.observed is True
    assert outcome.value.missing == (question.text,)


async def test_sufficiency_satisfies_the_sufficiency_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleSufficiency(), Sufficiency)
