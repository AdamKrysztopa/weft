"""This pack's own tests for `ExampleGenerator`."""

from weft_example_query.generator import NAME, ExampleGenerator

from weft_generate.contract import Generator
from weft_generate.payload import AnswerStance
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_kernel.seam import wrap
from weft_retrieve.payload import Passage, Passages, Query
from weft_store.contract import Scored


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _labelled_passage(text: str, label: str) -> Passage:
    node = Node.synthetic(
        content=text,
        media_type=MediaType.TEXT,
        reason="fixture",
        sources=frozenset({SourceId("src-1")}),
    )
    return Passage(
        scored=Scored(value=node, score=1.0), rank=0, retrieved_by="fixture", label=label
    )


async def test_generator_cites_each_passages_first_sentence_through_the_seam() -> None:
    # Arrange
    generator = ExampleGenerator()
    wrapped = wrap(
        generator.run, distribution="weft-example-query", contract="Generator", plugin=NAME
    )
    passage = _labelled_passage("Weft is a microkernel. It has plugins too.", "[1]")
    query = Query(text="what is weft")
    payload = Passages(origin=query, passages=(passage,))

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert — `Answer._citations_resolve` would have refused a marker or a node_id this
    # plugin got wrong; it not raising is itself part of the proof.
    assert isinstance(outcome, Produced)
    assert outcome.value.stance is AnswerStance.ANSWERED
    assert outcome.value.citations[0].marker == "[1]"
    assert outcome.value.citations[0].node_id == passage.node.id
    assert outcome.value.citations[0].source_id == "src-1"
    assert outcome.value.citations[0].quote == "Weft is a microkernel."
    assert outcome.value.used == (passage,)


async def test_generator_on_no_passages_answers_not_in_corpus() -> None:
    # Arrange
    generator = ExampleGenerator()
    query = Query(text="what is weft")

    # Act
    outcome = await generator.run(Passages(origin=query, passages=()), _ctx())

    # Assert — `Produced`, never `NothingToProduce`: the emptiness rule every query-path
    # contract in `weft_retrieve.contract` states.
    assert isinstance(outcome, Produced)
    assert outcome.value.stance is AnswerStance.NOT_IN_CORPUS
    assert outcome.value.citations == ()


async def test_generator_satisfies_the_generator_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleGenerator(), Generator)
