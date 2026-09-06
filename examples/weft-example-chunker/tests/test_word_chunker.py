"""This pack's own tests — the fourth canonical file `docs/07-extension-cost.md` names.

Exercises `WordChunker` directly, the same way `weft-chunk`'s own test suite
exercises `FixedSizeChunker`: against real `Node` inputs, no double standing
in for the kernel it depends on.
**Collected by weft's own gate since its ledger task 6.23**, through the `examples-tests` step —
a suite no task runs is prose, and two tests in this tree were quietly red for exactly that
reason. Still runnable on its own with `uv run pytest` from inside this directory, which is how
a stranger runs it.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from weft_example_chunker.word_chunker import WordChunker

from weft_kernel import runner
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_word_chunker_splits_content_into_one_node_per_word() -> None:
    # Arrange
    node = Node.synthetic(
        content="alpha beta gamma",
        media_type=MediaType.TEXT,
        reason="test fixture",
    )
    chunker = WordChunker()

    # Act
    outcome = await chunker.run([node], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [child.content for child in outcome.value] == ["alpha", "beta", "gamma"]
    assert all(node.id in child.lineage.parents for child in outcome.value)


async def test_word_chunker_on_blank_content_produces_nothing() -> None:
    # Arrange
    node = Node.synthetic(content="   ", media_type=MediaType.TEXT, reason="test fixture")
    chunker = WordChunker()

    # Act
    outcome = await chunker.run([node], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_word_chunker_satisfies_the_chunker_contract_structurally() -> None:
    # Arrange
    from weft_chunk.contract import Chunker

    # Act / Assert — no import of Chunker in word_chunker.py itself; this is the caller's check.
    assert isinstance(WordChunker(), Chunker)


def test_word_chunker_destroys_nothing_truthfully() -> None:
    # Act / Assert — `Chunker` publishes a property vocabulary
    # (docs/02-extension-model.md §3), so `destroys` must be stated, not omitted; splitting
    # strictly on whitespace never breaks a word, so the truthful answer is the empty tuple.
    assert WordChunker.destroys == ()


async def test_an_atomic_node_passes_this_chunker_unsplit_through_a_real_runner() -> None:
    """The property `applies_to` exists for, exercised rather than asserted as an attribute.

    Added 2026-09-06 at a review of weft's ledger task 9.2, which gave this chunker its
    `applies_to` and pinned only that the declaration is non-empty (weft's own fitness function
    23). A declaration nothing drives is a declaration nobody has watched work — and the defect
    that task existed to repair was found by running the *shipped* chunker through the *real*
    runner with a `TABLE` node, not by reading either one.

    `_NodeStage` rather than weft's `Chunker`: `Chunker` publishes a property vocabulary, so
    registering the inspection double under it would oblige the double to declare `destroys`,
    which says nothing about what is being measured here. Both contracts are
    `Stage[Sequence[Node], Sequence[Node]]`, which is what the runner type-checks.
    """
    # Arrange — the table sits between two prose nodes, so a correct recombine has to preserve
    # position and not merely membership.
    before = Node.synthetic(content="alpha beta", media_type=MediaType.TEXT, reason="fixture")
    table = Node.synthetic(content="col | col", media_type=MediaType.TABLE, reason="fixture")
    after = Node.synthetic(content="gamma delta", media_type=MediaType.TEXT, reason="fixture")
    captured: list[Sequence[Node]] = []

    class _NodeStage(runner.Stage[Sequence[Node], Sequence[Node]], Protocol):
        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...

    class _Capture:
        lifetime = runner.Lifetime.RUN

        def __init__(self, config: object = None) -> None:
            del config

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            del ctx
            captured.append(payload)
            return Produced(value=payload)

    registry = Registry()
    registry.add(_NodeStage, "example-chunker", WordChunker, distribution="weft-example-chunker")
    registry.add(_NodeStage, "capture", _Capture, distribution="weft-example-chunker")
    engine = runner.Runner(registry)
    pipeline = engine.resolve(
        (
            runner.StageSpec(id="chunk", contract=_NodeStage, name="example-chunker"),
            runner.StageSpec(id="capture", contract=_NodeStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield [before, table, after]

    # Act
    await engine.run(pipeline, batches(), _ctx())

    # Assert
    result = list(captured[0])
    assert [node.content for node in result] == [
        "alpha",
        "beta",
        "col | col",
        "gamma",
        "delta",
    ]
    assert result[2] is table  # the exact object — the seam never called `run` on it
