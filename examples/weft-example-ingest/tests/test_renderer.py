"""This pack's own tests for `ExamplePlainRenderer`."""

from weft_example_ingest.renderer import ExamplePlainRenderer

from weft_extract.contract import Renderer
from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, MediaType, Node, NothingToProduce, Produced, Vector
from weft_kernel.seam import wrap


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


class _Marker(ExtModel):
    __namespace__ = "test-only"


async def test_renderer_joins_nodes_and_records_what_it_dropped_through_the_seam() -> None:
    # Arrange
    renderer = ExamplePlainRenderer()
    wrapped = wrap(
        renderer.run,
        distribution="weft-example-ingest",
        contract="Renderer",
        plugin="example-renderer",
    )
    # `.derive()` carries no `ext` forward, unlike `Node.synthetic` (which always stamps
    # `SyntheticOrigin`) — this is the one way to get a node this renderer drops nothing for.
    root = Node.synthetic(content="root", media_type=MediaType.TEXT, reason="test fixture")
    plain = root.derive(content="alpha")
    with_extras = Node.synthetic(
        content="beta", media_type=MediaType.TEXT, reason="test fixture"
    ).with_embedding(Vector(values=(0.1,)))
    with_extras = with_extras.with_ext(_Marker())

    # Act
    outcome = await wrapped([plain, with_extras], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.text == "alpha\n\nbeta"
    assert outcome.value.nodes_rendered == 2
    kinds = {(item.node_id, item.kind) for item in outcome.value.dropped}
    assert (with_extras.id, "embedding") in kinds
    assert (with_extras.id, "extension") in kinds
    assert plain.id not in {item.node_id for item in outcome.value.dropped}


async def test_renderer_on_no_nodes_produces_nothing() -> None:
    # Arrange
    renderer = ExamplePlainRenderer()

    # Act
    outcome = await renderer.run([], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_renderer_satisfies_the_renderer_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExamplePlainRenderer(), Renderer)
