"""Unit tests for `weft_clean.artifact_remover`.

Mirrors `packages/weft-rag/src/weft_clean/artifact_remover.py`. Covers the happy path (a
standalone "Page N" line removed, per `reference/study/08-salvage.md` §T1.1's constants table),
the edge case of a separator line (more than half non-alphanumeric) dropped while ordinary
prose survives, the error case of an empty batch answering `NothingToProduce`, task 2.35's
own worked example (`ArtifactRemover` declares `intact = (Newlines,)` and
`destroys = (Verbatim,)`, truthfully), and a drive through `weft_kernel.seam.wrap` — FF7(b).
"""

from collections.abc import Sequence

from weft_clean.artifact_remover import ArtifactRemover, ArtifactRemoverConfig
from weft_clean.property import Newlines, Verbatim
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.seam import wrap


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_run_removes_a_standalone_page_number_line() -> None:
    # Arrange
    remover = ArtifactRemover()
    parent = _node("Intro text.\nPage 3\nMore body text.")

    # Act
    outcome: Outcome[Sequence[Node]] = await remover.run([parent], _ctx())

    # Assert — the "Page 3" line is gone; its surrounding lines and their break survive.
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "Intro text.\n\nMore body text."
    assert outcome.value[0].lineage.parents == (parent.id,)


async def test_run_drops_a_separator_line_but_keeps_ordinary_prose() -> None:
    # Arrange — a dashed rule is more than half non-alphanumeric; the prose lines are not.
    remover = ArtifactRemover()
    parent = _node("Body text here.\n----------------\nMore body text.")

    # Act
    outcome = await remover.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "Body text here.\nMore body text."


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    remover = ArtifactRemover()

    # Act
    outcome = await remover.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to remove artifacts from")


def test_config_takes_no_fields() -> None:
    # Act / Assert — an empty `with:` model is still the required shape.
    assert ArtifactRemoverConfig().model_dump() == {}


def test_needs_newlines_intact_and_destroys_verbatim() -> None:
    # Act / Assert — declared on the class, readable with no instance, per `02` §3.
    assert ArtifactRemover.intact == (Newlines,)
    assert ArtifactRemover.destroys == (Verbatim,)


async def test_artifact_remover_runs_through_the_seam() -> None:
    """FF7(b) shape: driven through `weft_kernel.seam.wrap`, not around it."""
    # Arrange
    remover = ArtifactRemover()
    sealed = wrap(
        remover.run,
        distribution="weft-clean",
        contract="Cleaner",
        plugin="artifact-remove",
        stage="clean",
    )
    node = _node("Body.\nPage 1\nMore body.")

    # Act
    outcome = await sealed([node], _ctx())

    # Assert — the seam adds spans and a guard, never behaviour.
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "Body.\n\nMore body."
