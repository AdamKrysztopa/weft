"""This pack's own tests — the fourth canonical file `docs/07-extension-cost.md` names.

Exercises `WordChunker` directly, the same way `weft-chunk`'s own test suite
exercises `FixedSizeChunker`: against real `Node` inputs, no double standing
in for the kernel it depends on.
**Collected by weft's own gate since its ledger task 6.23**, through the `examples-tests` step —
a suite no task runs is prose, and two tests in this tree were quietly red for exactly that
reason. Still runnable on its own with `uv run pytest` from inside this directory, which is how
a stranger runs it.
"""

from weft_example_chunker.word_chunker import WordChunker

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Produced


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
