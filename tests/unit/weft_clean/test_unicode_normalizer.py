"""Unit tests for `weft_clean.unicode_normalizer`.

Mirrors `packages/weft-clean/src/weft_clean/unicode_normalizer.py`. Covers the happy path
(the reference's own example, `Ã³` -> `ó`, repaired), the edge case of text with no mojibake at
all (passed through unchanged, still a new derived node), the error case of an empty batch
answering `NothingToProduce` rather than a silent `Produced([])`, task 2.35's own worked
example (`UnicodeNormalizer` declares `intact = (Verbatim,)` and `destroys = (Verbatim,)`,
truthfully), and a drive through `weft_kernel.seam.wrap` — FF7(b).
"""

from collections.abc import Sequence

from weft_clean.property import Verbatim
from weft_clean.unicode_normalizer import UnicodeNormalizer, UnicodeNormalizerConfig
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.seam import wrap


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_run_repairs_a_mis_decoded_byte_sequence() -> None:
    # Arrange — the reference's own example, restated: UTF-8 bytes for "ó" decoded as Latin-1.
    normalizer = UnicodeNormalizer()
    parent = _node("kompuÃ³ter")

    # Act
    outcome: Outcome[Sequence[Node]] = await normalizer.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "kompuóter"
    assert outcome.value[0].lineage.parents == (parent.id,)


async def test_run_leaves_text_with_no_mojibake_unchanged() -> None:
    # Arrange
    normalizer = UnicodeNormalizer()
    parent = _node("Plain ASCII text on one line.")

    # Act
    outcome = await normalizer.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "Plain ASCII text on one line."


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    normalizer = UnicodeNormalizer()

    # Act
    outcome = await normalizer.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to normalize")


def test_config_takes_no_fields() -> None:
    # Act / Assert — an empty `with:` model is still the required shape.
    assert UnicodeNormalizerConfig().model_dump() == {}


def test_needs_verbatim_intact_and_destroys_it() -> None:
    # Act / Assert — declared on the class, readable with no instance, per `02` §3.
    # This stage both needs and ends `Verbatim` — see `weft_clean.property`'s module
    # docstring for why that is honest rather than contradictory.
    assert UnicodeNormalizer.intact == (Verbatim,)
    assert UnicodeNormalizer.destroys == (Verbatim,)


async def test_unicode_normalizer_runs_through_the_seam() -> None:
    """FF7(b) shape: driven through `weft_kernel.seam.wrap`, not around it."""
    # Arrange
    normalizer = UnicodeNormalizer()
    sealed = wrap(
        normalizer.run,
        distribution="weft-clean",
        contract="Cleaner",
        plugin="unicode-normalize",
        stage="clean",
    )
    node = _node("kompuÃ³ter")

    # Act
    outcome = await sealed([node], _ctx())

    # Assert — the seam adds spans and a guard, never behaviour.
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "kompuóter"
