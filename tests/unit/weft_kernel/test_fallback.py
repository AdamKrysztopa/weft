"""Unit tests for `weft_kernel.fallback`.

Mirrors `packages/weft-kernel/src/weft_kernel/fallback.py`. The three outcomes
the combinator has to keep apart are the whole subject: `Produced` stops the
chain with a success, `NothingToProduce` stops it with a *fact*, and only
`Failed` — or a `WeftError` the seam already wrapped — moves to the next
candidate.

**Why the `NothingToProduce` test is the load-bearing one.** A chain built on
only two states for a three-state problem cannot tell "I looked, and there is
nothing here" apart from "I could not see it": a genuinely blank document
walks the whole chain and is reported as a chain-wide failure, while a
scanned page is reported as an empty success.
Both directions are asserted here, on the same chain, so neither can be fixed
by breaking the other.
"""

import asyncio
from collections.abc import Sequence

import pytest

from weft_kernel.blocking import BlockingCallError
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.fallback import Attempt, try_in_order
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


class _Recorder:
    """A candidate that records that it was reached, and answers what it was told to."""

    def __init__(self, answer: Outcome[str] | BaseException) -> None:
        self._answer = answer
        self.calls = 0

    async def __call__(self, payload: str, ctx: Context) -> Outcome[str]:
        del payload, ctx
        self.calls += 1
        if isinstance(self._answer, BaseException):
            raise self._answer
        return self._answer


def _chain(*named: tuple[str, _Recorder]) -> Sequence[Attempt[str, str]]:
    return [Attempt(name=name, run=recorder) for name, recorder in named]


async def test_the_first_candidate_that_produces_stops_the_chain() -> None:
    # Arrange
    first = _Recorder(Produced(value="read by pdf-text"))
    second = _Recorder(Produced(value="read by pdf-layout"))

    # Act
    outcome = await try_in_order(
        "doc", _ctx(), stage="extract", attempts=_chain(("pdf-text", first), ("pdf-layout", second))
    )

    # Assert
    assert outcome == Produced(value="read by pdf-text")
    assert second.calls == 0, "a candidate after a successful one must never be reached"


async def test_a_failed_candidate_moves_on_and_a_later_one_answers() -> None:
    # Arrange — the exit demonstration's shape: the first backend could not read it.
    first = _Recorder(Failed(reason="pdf-text could not read 'paper.pdf'"))
    second = _Recorder(Produced(value="read by pdf-layout"))

    # Act
    outcome = await try_in_order(
        "doc", _ctx(), stage="extract", attempts=_chain(("pdf-text", first), ("pdf-layout", second))
    )

    # Assert
    assert outcome == Produced(value="read by pdf-layout")
    assert (first.calls, second.calls) == (1, 1)


async def test_nothing_to_produce_stops_the_chain_and_is_returned_unchanged() -> None:
    # Arrange — `02` §1:172: a backend that legitimately extracted nothing had no way to
    # say so. It now does, *and it stops the chain* — a second backend adds nothing to the
    # claim "I looked, and there is nothing here."
    first = _Recorder(NothingToProduce(reason="4 page(s), and no text on any of them"))
    second = _Recorder(Produced(value="read by pdf-layout"))

    # Act
    outcome = await try_in_order(
        "doc", _ctx(), stage="extract", attempts=_chain(("pdf-text", first), ("pdf-layout", second))
    )

    # Assert
    assert outcome == NothingToProduce(reason="4 page(s), and no text on any of them")
    assert second.calls == 0, "an empty document must not be handed to a second backend"


async def test_a_weft_error_is_recorded_and_the_next_candidate_is_tried() -> None:
    # Arrange — the seam has already turned every undocumented third-party exception into
    # a `WeftError`, so catching that one class is the broad tolerance a format library
    # needs, declared at the combinator rather than smuggled into a backend.
    first = _Recorder(WeftError("'extract:pdf-text' failed: PdfReadError"))
    second = _Recorder(Produced(value="read by pdf-layout"))

    # Act
    outcome = await try_in_order(
        "doc", _ctx(), stage="extract", attempts=_chain(("pdf-text", first), ("pdf-layout", second))
    )

    # Assert
    assert outcome == Produced(value="read by pdf-layout")
    assert second.calls == 1


async def test_a_blocking_call_stops_the_chain_instead_of_being_recorded_as_a_refusal() -> None:
    # Arrange — `BlockingCallError` *is* a `WeftError`, so the broad clause the test above
    # exercises would file fitness function 7(b)'s own diagnostic as "this backend could
    # not do its job" and let the next candidate bury it. It is the kernel's report of a
    # violated runtime contract, not a backend's report of a document it could not read.
    first = _Recorder(BlockingCallError("stage 'extract:pdf-text' made a blocking call (open())"))
    second = _Recorder(Produced(value="read by pdf-layout"))

    # Act / Assert — a `fallback:` line must not be a way to opt a stage out of the guard.
    with pytest.raises(BlockingCallError):
        await try_in_order(
            "doc",
            _ctx(),
            stage="extract",
            attempts=_chain(("pdf-text", first), ("pdf-layout", second)),
        )
    assert second.calls == 0


async def test_an_exhausted_chain_names_every_candidate_and_what_each_said() -> None:
    # Arrange
    first = _Recorder(Failed(reason="no text layer, 1 image present"))
    second = _Recorder(WeftError("PdfminerException: no /Root object"))

    # Act
    outcome = await try_in_order(
        "doc", _ctx(), stage="extract", attempts=_chain(("pdf-text", first), ("pdf-layout", second))
    )

    # Assert — errors accumulate and are reported together, never last-one-wins.
    assert isinstance(outcome, Failed)
    assert "extract" in outcome.reason
    assert "pdf-text" in outcome.reason
    assert "no text layer, 1 image present" in outcome.reason
    assert "pdf-layout" in outcome.reason
    assert "no /Root object" in outcome.reason
    assert outcome.reason.index("pdf-text") < outcome.reason.index("pdf-layout")


async def test_cancellation_passes_through_untouched() -> None:
    # Arrange — `CancelledError` is a `BaseException`, so it is never at risk of being
    # recorded as a refusal and walked past. Asserted rather than assumed: a cancelled run
    # that quietly continued to a second backend would be the loudest possible version of
    # the swallowing `01` → *Colour* forbids.
    first = _Recorder(asyncio.CancelledError())
    second = _Recorder(Produced(value="read by pdf-layout"))

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await try_in_order(
            "doc",
            _ctx(),
            stage="extract",
            attempts=_chain(("pdf-text", first), ("pdf-layout", second)),
        )
    assert second.calls == 0


async def test_an_empty_chain_is_refused_rather_than_answered() -> None:
    # Arrange / Act / Assert — a chain is `[primary, *fallbacks]`, so it is never empty
    # for any caller that has a stage to run at all. Returning `Failed` here would put a
    # caller's own bug into a pipeline's outcome, where it reads as a backend's refusal.
    with pytest.raises(ValueError, match="extract"):
        await try_in_order("doc", _ctx(), stage="extract", attempts=())
