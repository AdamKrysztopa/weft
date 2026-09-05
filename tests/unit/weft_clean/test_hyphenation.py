"""Unit tests for `weft_clean.hyphenation`.

Mirrors `packages/weft-rag/src/weft_clean/hyphenation.py`. Covers the
happy path (a word broken across a line by a trailing hyphen is rejoined,
lineage carried), the edge case of text with no broken word at all (passed
through unchanged, still a new derived node), and the error case of an empty
batch answering `NothingToProduce` rather than a silent `Produced([])`. Also
covers task 1.7's own worked example: `HyphenationRepair` declares `intact =
(Newlines,)`, truthfully.
"""

from collections.abc import Sequence

from weft_clean.hyphenation import HyphenationRepair, HyphenationRepairConfig
from weft_clean.property import Newlines, Verbatim
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_run_rejoins_a_word_broken_by_a_trailing_hyphen() -> None:
    # Arrange — the canonical example: `kompu-\nter` -> `komputer`.
    repair = HyphenationRepair()
    parent = _node("This is a kompu-\nter on the desk.")

    # Act
    outcome: Outcome[Sequence[Node]] = await repair.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "This is a komputer on the desk."
    assert outcome.value[0].lineage.parents == (parent.id,)


async def test_run_leaves_text_with_no_broken_word_unchanged() -> None:
    # Arrange
    repair = HyphenationRepair()
    parent = _node("A well-known fact, on one line.")

    # Act
    outcome = await repair.run([parent], _ctx())

    # Assert — "well-known" has no newline after its hyphen, so it is not a break.
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "A well-known fact, on one line."


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    repair = HyphenationRepair()

    # Act
    outcome = await repair.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to repair")


def test_config_takes_no_fields() -> None:
    # Act / Assert — an empty `with:` model is still the required shape.
    assert HyphenationRepairConfig().model_dump() == {}


def test_needs_newlines_intact_and_destroys_verbatim() -> None:
    # Act / Assert — declared on the class, readable with no instance, per `02` §3.
    assert HyphenationRepair.intact == (Newlines,)
    assert HyphenationRepair.destroys == (Verbatim,)
