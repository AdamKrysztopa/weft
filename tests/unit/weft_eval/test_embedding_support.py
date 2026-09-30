"""`weft_eval.embedding_support.embed_texts` — the one place a metric's text meets the embedder.

R44.21: the configured embedder may refuse an empty input by raising, and that raise escaped a
judging pass and aborted an arm that had already answered every question.
"""

from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_eval.embedding_support import embed_texts
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, Node, Produced


class _RefusesEveryCall:
    """An `Embedder` that must never be reached."""

    async def run(self, nodes: tuple[Node, ...], ctx: Context) -> object:
        raise AssertionError("a blank text must be refused before the embedder is called")


def _ctx() -> Context:
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=ServiceRegistry(),
    )


async def test_a_blank_text_fails_naming_its_position_without_calling_the_embedder() -> None:
    # Arrange
    embedder: Embedder = _RefusesEveryCall()  # type: ignore[assignment]

    # Act
    outcome = await embed_texts(embedder, ("a real text", "   "), _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "text 1 is empty" in outcome.reason


async def test_non_blank_texts_are_still_embedded_in_order() -> None:
    # Arrange
    services = ServiceRegistry()
    services.add(Embedder, HashEmbedder())
    ctx = Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )

    # Act
    outcome = await embed_texts(ctx.require(Embedder), ("first", "second"), ctx)

    # Assert
    assert isinstance(outcome, Produced)
    assert len(outcome.value) == 2
