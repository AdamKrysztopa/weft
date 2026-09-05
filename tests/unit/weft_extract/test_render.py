"""Unit tests for `weft_extract.render`.

Mirrors `packages/weft-rag/src/weft_extract/render.py`. Binding constraint
10's second half (`.phase2-findings.md`, and `.phase2-design.md` A.2, assigned
to ledger 2.27 by A.4's consequences table) is that export formats are **one
contract with several registrations**, never a `format:` field with a branch
behind it. What that buys is only real if the two shipped registrations
actually differ, so the central test here is that `markdown` carries a
distinction `plain` cannot.

`dropped` carries the rest of the weight. A.2: "`dropped` is the honest half,
and it is the whole reason this is not a `str` return... A renderer returning a
partial document with an empty `dropped` is a defect the reviewer must catch."
So every test that renders a node with something a format cannot hold asserts
the loss is reported, not merely that the text came out.
"""

from weft_extract.contract import Renderer
from weft_extract.payload import DroppedKind, Rendition
from weft_extract.render import MarkdownRenderer, PlainRenderer, PlainRendererConfig
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Produced, SourceId, Vector


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str, media_type: MediaType = MediaType.TEXT) -> Node:
    return Node.synthetic(
        content=content,
        media_type=media_type,
        reason="written by a test",
        sources=frozenset({SourceId("paper")}),
    )


async def test_plain_joins_every_node_and_says_so() -> None:
    # Arrange
    renderer = PlainRenderer()
    nodes = [_node("first passage"), _node("second passage")]

    # Act
    outcome = await renderer.run(nodes, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    rendition = outcome.value
    assert rendition.text == "first passage\n\nsecond passage"
    assert rendition.media_type == "text/plain"
    assert rendition.nodes_rendered == 2


async def test_markdown_carries_a_media_distinction_plain_cannot() -> None:
    # Arrange — the reason two registrations rather than one with a `format:` field:
    # they are genuinely different formats, and a table is where that first shows.
    table = _node("year | recall\n2023 | 0.81", MediaType.TABLE)

    # Act
    as_markdown = await MarkdownRenderer().run([table], _ctx())
    as_plain = await PlainRenderer().run([table], _ctx())

    # Assert
    assert isinstance(as_markdown, Produced)
    assert isinstance(as_plain, Produced)
    assert "```table" in as_markdown.value.text
    assert not [drop for drop in as_markdown.value.dropped if drop.kind is DroppedKind.MEDIA]
    assert [drop for drop in as_plain.value.dropped if drop.kind is DroppedKind.MEDIA]


async def test_an_embedding_and_an_extension_are_reported_as_dropped() -> None:
    # Arrange — neither format carries a vector, and neither carries the extension data
    # a parser attached. A `Rendition` that reported the text and stayed silent about
    # both would be the partial-document defect A.2 names.
    node = _node("a passage").with_embedding(Vector(values=(0.5, 0.5)))

    # Act
    outcome = await MarkdownRenderer().run([node], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    kinds = {drop.kind for drop in outcome.value.dropped}
    assert DroppedKind.EMBEDDING in kinds
    # Every root node carries `SyntheticOrigin`, which markdown has no way to hold either.
    assert DroppedKind.EXTENSION in kinds


async def test_the_node_separator_is_configuration_rather_than_a_compiled_in_choice() -> None:
    # Arrange
    renderer = PlainRenderer(PlainRendererConfig(node_separator="\n---\n"))

    # Act
    outcome = await renderer.run([_node("one"), _node("two")], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.text == "one\n---\ntwo"


async def test_nothing_to_render_is_not_a_failure() -> None:
    # Act
    outcome = await PlainRenderer().run([], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)
    assert "no nodes" in outcome.reason


def test_both_renderers_satisfy_the_contract_without_importing_it() -> None:
    # Act / Assert — the same structural path a third-party `docx` renderer takes.
    assert isinstance(PlainRenderer(), Renderer)
    assert isinstance(MarkdownRenderer(), Renderer)
    assert Rendition.model_config.get("frozen") is True
