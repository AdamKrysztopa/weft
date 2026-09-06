"""The shipped chunker declares what it splits — ledger task `9.2`'s product half.

Task `1.6` ticked *"an atomic node passes the chunker unsplit"* against a fixture
(`tests/unit/weft_kernel/test_runner.py:822`, `_NaiveSplitter`), and on 2026-09-06 that
property was measured against the *product* and did not hold: `FixedSizeChunker`
(`packages/weft-rag/src/weft_chunk/fixed_size.py`) declared no `applies_to` at all and split a
`MediaType.TABLE` node into two chunks. `L9.6` is that lesson — *a ticked ledger property held
only for the fixture that demonstrated it* — and this file is the test that would have caught it.

**Why the real chunker and the real runner, and not a stand-in for either.** A stand-in splitter
is what `test_runner.py` already owns, and it proves the *seam* routes. What it cannot prove is
that the one chunker this project ships has made the declaration the seam needs, which is the
only reason a `TABLE` node reaching the store whole is a fact about Weft rather than about a
fixture. So the subject here is `FixedSizeChunker` itself, registered under the real `Chunker`
contract and driven by the real `Runner`.

**The declaration is asserted as a fact about a set, not as a literal tuple.** `02` §3 →
*Applicability* states what a stage claims, never how many `Applies` objects it spells that with,
so a test pinning `applies_to == (Applies(media_type=MediaType.TEXT),)` would hand a shape to the
implementation instead of a property. What is asserted is the fact: every `MediaType` member the
chunker does not claim is left whole, and the one it claims is split — read off `MediaType` itself,
so a member added later is covered by construction rather than by someone remembering this file.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from weft_chunk.contract import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_kernel import runner
from weft_kernel.context import Context
from weft_kernel.payload import Applies, MediaType, Node, Outcome, Produced
from weft_kernel.registry import Registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(*, media_type: MediaType, content: str) -> Node:
    return Node.synthetic(content=content, media_type=media_type, reason="task 9.2's subject")


class _NodeStage(runner.Stage[Sequence[Node], Sequence[Node]], Protocol):
    """A contract for the capture stage below, so it is not a second `Chunker`.

    `Chunker.publishes_property_vocabulary` is `True`, so registering an inspection double under
    it would oblige the double to declare `destroys` — a statement about property vocabulary that
    has nothing to do with what this file is measuring. Composition still holds: both contracts
    are `Stage[Sequence[Node], Sequence[Node]]`, which is what the runner type-checks.
    """

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


class _CapturesWhatItReceives:
    """An identity stage recording the batch handed to it — `Runner.run` answers counts only."""

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[object], ...] = ()
    provides: tuple[type[object], ...] = ()

    def __init__(self, captured: list[Sequence[Node]]) -> None:
        self._captured = captured

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        self._captured.append(payload)
        return Produced(value=payload)


async def _through_the_chunker(batch: Sequence[Node]) -> Sequence[Node]:
    """`batch` run through the shipped `FixedSizeChunker` on a real `Runner`, as indexed."""
    captured: list[Sequence[Node]] = []

    def capture_factory(config: object) -> _CapturesWhatItReceives:
        del config
        return _CapturesWhatItReceives(captured)

    registry = Registry()
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-rag")
    registry.add(_NodeStage, "capture", capture_factory, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="chunk", contract=Chunker, name="fixed-size"),
            runner.StageSpec(id="capture", contract=_NodeStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield batch

    await engine.run(pipeline, batches(), _ctx())
    assert len(captured) == 1, "the capture stage saw a number of batches it was not handed"
    return captured[0]


async def test_a_table_node_reaches_the_next_stage_whole_and_in_position() -> None:
    """9.2's property, on the product: a `TABLE` node between two long text nodes is the same
    object on the other side of the shipped chunker, while the text around it is split.
    """
    # Arrange — the text is long enough that the chunker's default window splits it, so the
    # table surviving is a statement about routing rather than about a batch nothing touched.
    before = _node(media_type=MediaType.TEXT, content="a" * 4000)
    table = _node(media_type=MediaType.TABLE, content="col | col\n1 | 2")
    after = _node(media_type=MediaType.TEXT, content="b" * 4000)

    # Act
    result = list(await _through_the_chunker([before, table, after]))

    # Assert
    assert table in result, "the table node did not survive the chunker"
    assert result[result.index(table)] is table, "the table was rebuilt rather than routed past"
    assert [node.content for node in result].count(before.content) == 0, (
        "the surrounding text was not split, so the table surviving proves nothing"
    )


async def test_a_batch_of_only_non_text_nodes_passes_through_untouched() -> None:
    """The edge case the seam has to survive: nothing in the batch matches, so the chunker is
    never called at all and the run neither fails nor empties the batch.
    """
    # Arrange
    table = _node(media_type=MediaType.TABLE, content="col | col\n1 | 2")
    image = _node(media_type=MediaType.IMAGE, content="Figure 1. A caption.")

    # Act
    result = list(await _through_the_chunker([table, image]))

    # Assert
    assert result == [table, image]


async def test_the_shipped_chunker_claims_text_and_no_other_media_type() -> None:
    """The declaration read as a fact about `MediaType`'s whole membership, not as a tuple.

    Read off the enum so a member added after this file was written is covered without an edit
    here — `L6.4`: a marker means what its live instances say.
    """
    # Arrange
    declared: tuple[Applies, ...] = FixedSizeChunker.applies_to

    def claims(media_type: MediaType) -> bool:
        node = _node(media_type=media_type, content="x")
        return all(constraint.matches(node) for constraint in declared)

    # Act
    claimed = {media_type for media_type in MediaType if claims(media_type)}

    # Assert
    assert claimed == {MediaType.TEXT}


async def test_a_chunker_that_declares_nothing_still_splits_everything() -> None:
    """The contrast that makes the three tests above properties of the declaration.

    Without it, a chunker that had simply stopped splitting would pass every assertion here.
    """

    # Arrange
    class _DeclaresNothing(FixedSizeChunker):
        applies_to: tuple[Applies, ...] = ()

    registry = Registry()
    registry.add(_NodeStage, "declares-nothing", _DeclaresNothing, distribution="weft-test-pack")
    engine = runner.Runner(registry)
    captured: list[Sequence[Node]] = []

    def capture_factory(config: object) -> _CapturesWhatItReceives:
        del config
        return _CapturesWhatItReceives(captured)

    registry.add(_NodeStage, "capture", capture_factory, distribution="weft-test-pack")
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="chunk", contract=_NodeStage, name="declares-nothing"),
            runner.StageSpec(id="capture", contract=_NodeStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )
    table = _node(media_type=MediaType.TABLE, content="x" * 4000)

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield [table]

    # Act
    await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert len(captured) == 1
    assert table not in list(captured[0])
