"""A wrapped call leaves a stage record — ledger task **33.1**.

The seam already applies spans, attribution, stripping and the blocking guard to every call without
the author asking; timing is the concern that was missing, and it attaches at the same place for
the same reason (`CLAUDE.md` → *Cross-cutting concerns live at the registration seam*). Inside a
recording scope a caller opens, every `wrap` call leaves exactly one frozen `StageRecord`; outside
one, nothing is recorded and `wrap` behaves as it always has.

The assertions are on the records a real `wrap` call leaves, through `seam.recording()` — never on
a private recorder — so the arrangement inside the seam stays free to change (`L9.39`).
"""

import asyncio
from collections.abc import Sequence

import pytest

from weft_kernel import seam
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced


async def _halve(payload: Sequence[int]) -> Outcome[tuple[int, ...]]:
    await asyncio.sleep(0.01)
    return Produced(value=tuple(payload[: len(payload) // 2]))


async def test_a_wrapped_call_in_a_scope_leaves_one_record_of_what_ran() -> None:
    # Arrange
    run = seam.wrap(
        _halve,
        distribution="weft-test",
        contract="Halver",
        plugin="halve",
        stage="halve-stage",
        position="halve-stage",
    )

    # Act
    with seam.recording() as recording:
        await run([1, 2, 3, 4])

    # Assert
    (record,) = recording.records
    assert record.label == "halve-stage"
    assert record.position == "halve-stage"
    assert (record.pack, record.contract, record.plugin) == ("weft-test", "Halver", "halve")
    assert record.outcome is seam.OutcomeKind.PRODUCED
    assert (record.items_in, record.items_out) == (4, 2)
    assert record.seconds >= 0.009
    assert record.parent is None


def test_a_record_is_a_frozen_model() -> None:
    # Act / Assert
    assert seam.StageRecord.model_config.get("frozen") is True


async def test_a_call_that_raises_is_still_recorded_as_raised() -> None:
    """The slow call is often the one that fails, so the trace must keep it.

    The slow call is often the one that fails, so a trace that dropped it would be missing
    exactly the stage an operator is looking for.
    """

    # Arrange
    async def _explode(payload: Sequence[int]) -> Outcome[int]:
        raise ValueError("boom")

    run = seam.wrap(_explode, distribution="weft-test", contract="Halver", plugin="explode")

    # Act
    with seam.recording() as recording, pytest.raises(WeftError):
        await run([1, 2, 3])

    # Assert
    (record,) = recording.records
    assert record.outcome is seam.OutcomeKind.RAISED
    assert record.items_in == 3
    assert record.items_out is None


async def test_outcome_kinds_that_are_not_produced_are_named_and_carry_no_output_count() -> None:
    # Arrange
    async def _nothing(payload: object) -> Outcome[int]:
        return NothingToProduce(reason="empty")

    async def _failed(payload: object) -> Outcome[int]:
        return Failed(reason="refused")

    nothing = seam.wrap(_nothing, distribution="weft-test", contract="C", plugin="nothing")
    failed = seam.wrap(_failed, distribution="weft-test", contract="C", plugin="failed")

    # Act
    with seam.recording() as recording:
        await nothing("not a sequence")
        await failed(["a"])

    # Assert
    by_plugin = {record.plugin: record for record in recording.records}
    assert by_plugin["nothing"].outcome is seam.OutcomeKind.NOTHING_TO_PRODUCE
    assert by_plugin["nothing"].items_in is None
    assert by_plugin["failed"].outcome is seam.OutcomeKind.FAILED
    assert by_plugin["failed"].items_in == 1
    assert by_plugin["failed"].items_out is None


async def test_a_call_inside_another_names_it_as_its_parent() -> None:
    """Two records, so the parent link is a fact the fixture can get wrong (`L12.6`).

    A stage that asks an LLM is one record containing another, not two siblings.
    """
    # Arrange
    inner = seam.wrap(_halve, distribution="weft-test", contract="Halver", plugin="inner")

    async def _outer(payload: Sequence[int]) -> Outcome[tuple[int, ...]]:
        return await inner(payload)

    outer = seam.wrap(_outer, distribution="weft-test", contract="Halver", plugin="outer")

    # Act
    with seam.recording() as recording:
        await outer([1, 2, 3, 4])

    # Assert
    by_plugin = {record.plugin: record for record in recording.records}
    assert by_plugin["outer"].parent is None
    assert by_plugin["inner"].parent == by_plugin["outer"].id
    assert by_plugin["inner"].id != by_plugin["outer"].id


async def test_outside_a_scope_nothing_is_recorded_and_the_outcome_is_unchanged() -> None:
    # Arrange
    run = seam.wrap(_halve, distribution="weft-test", contract="Halver", plugin="halve")

    # Act
    unrecorded = await run([1, 2, 3, 4])
    with seam.recording() as recording:
        pass

    # Assert
    assert unrecorded == Produced(value=(1, 2))
    assert recording.records == ()


async def test_concurrent_calls_in_one_scope_are_each_recorded() -> None:
    """A stage fanning out with `gather` records into the scope that encloses it.

    The children copy the context, and the scope is what they share.
    """
    # Arrange
    run = seam.wrap(_halve, distribution="weft-test", contract="Halver", plugin="halve")

    # Act
    with seam.recording() as recording:
        await asyncio.gather(run([1, 2]), run([1, 2, 3, 4]), run([1, 2, 3, 4, 5, 6]))

    # Assert
    assert len(recording.records) == 3
    assert {record.items_in for record in recording.records} == {2, 4, 6}


# --- Repair R32.3: a payload that is a model with a length is counted too ---------------------


class _Batch:
    """A payload the kernel knows nothing about except that it has a length.

    The shape a pack's own model takes when it answers `len()`.
    """

    def __init__(self, items: Sequence[int]) -> None:
        self._items = tuple(items)

    def __len__(self) -> int:
        return len(self._items)


async def _halve_batch(payload: _Batch) -> Outcome[_Batch]:
    return Produced(value=_Batch(range(len(payload) // 2)))


async def _echo_text(payload: str) -> Outcome[str]:
    return Produced(value=payload)


async def test_a_payload_with_a_length_is_counted_in_and_out() -> None:
    # Arrange
    run = seam.wrap(_halve_batch, distribution="weft-test", contract="Halver", plugin="halve")

    # Act
    with seam.recording() as recording:
        await run(_Batch([1, 2, 3, 4, 5, 6]))

    # Assert
    (record,) = recording.records
    assert (record.items_in, record.items_out) == (6, 3)


async def test_text_is_not_counted_as_items() -> None:
    """A string has a length in characters, which is not a number of items."""
    # Arrange
    run = seam.wrap(_echo_text, distribution="weft-test", contract="Echo", plugin="echo")

    # Act
    with seam.recording() as recording:
        await run("a question")

    # Assert
    (record,) = recording.records
    assert (record.items_in, record.items_out) == (None, None)
