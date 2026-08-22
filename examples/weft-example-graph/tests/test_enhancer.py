from weft_example_graph.enhancer import GraphEntityEnhancer
from weft_example_graph.payload import GraphData

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Produced


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


async def test_attaches_graph_data_to_every_node() -> None:
    # Arrange
    node = Node.synthetic(
        content="Acme Corp and Globex Inc compete.", media_type=MediaType.TEXT, reason="test"
    )
    enhancer = GraphEntityEnhancer()

    # Act
    outcome = await enhancer.run([node], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    (enhanced,) = outcome.value
    data = enhanced.ext_as(GraphData)
    assert data is not None
    assert {entity.name for entity in data.entities} == {"Acme Corp", "Globex Inc"}
    assert len(data.relations) == 1
    # Identity is unaffected — an Enhancer adds a fact, never rewrites content (weft_enhance's
    # own contrast with Cleaner).
    assert enhanced.id == node.id
    assert enhanced.content == node.content


async def test_a_node_with_no_entities_still_gets_an_empty_graph_data() -> None:
    # Arrange
    node = Node.synthetic(
        content="nothing capitalised here.", media_type=MediaType.TEXT, reason="t"
    )

    # Act
    outcome = await GraphEntityEnhancer().run([node], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    data = outcome.value[0].ext_as(GraphData)
    assert data == GraphData(entities=(), relations=())


async def test_an_empty_batch_answers_nothing_to_produce() -> None:
    outcome = await GraphEntityEnhancer().run([], _ctx())
    assert isinstance(outcome, NothingToProduce)
