"""Unit tests for `weft_clean.whitespace`.

Mirrors `packages/weft-clean/src/weft_clean/whitespace.py`. Covers the
happy path (runs of spaces collapsed, three-or-more blank lines folded to a
paragraph break, edges trimmed), the edge case of already-clean text passing
through unchanged, and the error case of an empty batch answering
`NothingToProduce`. Also covers task 1.7's own worked example:
`WhitespaceNormalizer` declares `destroys = (Newlines, WhitespaceGaps)`,
truthfully — the one stage in this pack that collapses whitespace at all.
"""

from collections.abc import Sequence

from weft_clean.property import Newlines, WhitespaceGaps
from weft_clean.whitespace import WhitespaceNormalizer, WhitespaceNormalizerConfig
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_run_collapses_wide_gaps_and_excess_blank_lines() -> None:
    # Arrange
    normalizer = WhitespaceNormalizer()
    parent = _node("  Column One    Column Two  \n\n\n\nNext paragraph.  ")

    # Act
    outcome: Outcome[Sequence[Node]] = await normalizer.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "Column One Column Two\n\nNext paragraph."


async def test_run_leaves_already_clean_text_unchanged() -> None:
    # Arrange
    normalizer = WhitespaceNormalizer()
    parent = _node("One clean sentence.\n\nAnother paragraph.")

    # Act
    outcome = await normalizer.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "One clean sentence.\n\nAnother paragraph."


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    normalizer = WhitespaceNormalizer()

    # Act
    outcome = await normalizer.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to normalize")


def test_config_takes_no_fields() -> None:
    # Act / Assert — an empty `with:` model is still the required shape.
    assert WhitespaceNormalizerConfig().model_dump() == {}


def test_destroys_newlines_and_whitespace_gaps() -> None:
    # Act / Assert — declared on the class, readable with no instance, per `02` §3. Both
    # properties, not one: see `weft_clean.property`'s module docstring for why one stage
    # destroying two facts is what makes "must run last" fall out rather than needing to
    # be stated twice.
    assert WhitespaceNormalizer.destroys == (Newlines, WhitespaceGaps)
    assert WhitespaceNormalizer.intact == ()
