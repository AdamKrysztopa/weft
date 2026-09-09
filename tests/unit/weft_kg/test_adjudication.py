"""The three-valued band and the chain that reads it. Ledger task **11.9**.

Mirrors `packages/weft-rag/src/weft_kg/adjudication.py`. No container and no model: everything
here is a function of its arguments, which is the same split `test_resolution.py` draws for
`11.8` — the database scores, this decides, and `weft_kg.store` is the only thing that does I/O.

**Why three values rather than two, asserted rather than described.** A boolean adjudicator can
only say *same* or *different*, so a cheap rule that has no opinion has to invent one, and the
invention is invisible: two entities that are one look exactly like two entities that are two.
The third value is *"I do not know, ask the next one"*, and the band is where it lives — above the
band the cheap blend already merged the pair (`weft_kg.resolution.DEFAULT_SIMILARITY_THRESHOLD` is
the same number, not a second one that can drift), below it the pair is plainly two things, and
between them is the only region where spending a model call buys anything.

**The chain is first-non-`None`-wins, and the trap it is not built on.**
`weft_kernel.fallback.try_in_order` is the tree's existing chain helper and it is the wrong one
here: its `NothingToProduce` *stops* a chain rather than deferring within it, so an adjudicator
with no opinion would end the sequence instead of handing on to the next. The ledger line names
that trap directly, and `test_a_chain_asks_the_next_adjudicator_when_the_first_abstains` is what
proves this module did not fall into it.
"""

from __future__ import annotations

import pytest

from weft_kg.adjudication import (
    DEFAULT_ADJUDICATION_FLOOR,
    Adjudicator,
    first_verdict,
    threshold_adjudicator,
)
from weft_kg.resolution import DEFAULT_SIMILARITY_THRESHOLD


def _always(verdict: bool | None) -> Adjudicator:
    """An adjudicator with a fixed opinion, recording whether it was asked."""

    async def _adjudicate(left: str, right: str, score: float) -> bool | None:
        del left, right, score
        return verdict

    return _adjudicate


async def test_a_score_at_or_above_the_ceiling_is_the_same_thing() -> None:
    """The ceiling is the cheap pass's own merge threshold, so a pair that reaches it has
    already been merged and needs no judgement — the adjudicator agreeing is what makes the
    band's upper edge one number rather than two that can drift apart.
    """
    # Arrange
    adjudicate = threshold_adjudicator()

    # Act
    verdict = await adjudicate("Chucri", "Chucri.", DEFAULT_SIMILARITY_THRESHOLD)

    # Assert
    assert verdict is True


async def test_a_score_below_the_floor_is_two_different_things() -> None:
    """Below the floor the pair is refused outright — no model call, and the refusal is a
    decision rather than an abstention, which is what keeps it out of the abstained count.
    """
    # Arrange
    adjudicate = threshold_adjudicator()

    # Act
    verdict = await adjudicate("Chucri", "Azouz", DEFAULT_ADJUDICATION_FLOOR - 0.01)

    # Assert
    assert verdict is False


async def test_a_score_inside_the_band_abstains_rather_than_guessing() -> None:
    """The property this module exists for. Neither `True` nor `False`: a rule with no evidence
    either way says so, and something with more evidence gets asked next.
    """
    # Arrange
    adjudicate = threshold_adjudicator()
    inside = (DEFAULT_ADJUDICATION_FLOOR + DEFAULT_SIMILARITY_THRESHOLD) / 2

    # Act
    verdict = await adjudicate("RRF", "Rapid Response Force", inside)

    # Assert
    assert verdict is None


async def test_the_floor_itself_is_inside_the_band_not_below_it() -> None:
    """The band is closed at the bottom and open at the top — `[floor, ceiling)`. Asserted
    because the two edges are the only places the three regions can be off by one, and an
    off-by-one here silently moves a pair from *asked* to *refused* with no symptom.
    """
    # Arrange
    adjudicate = threshold_adjudicator()

    # Act
    at_floor = await adjudicate("a", "b", DEFAULT_ADJUDICATION_FLOOR)

    # Assert
    assert at_floor is None


async def test_a_chain_asks_the_next_adjudicator_when_the_first_abstains() -> None:
    """First-non-`None`-wins, and the reason `weft_kernel.fallback.try_in_order` is not reused:
    an abstention must hand on, where a `NothingToProduce` would end the chain.
    """
    # Arrange
    asked: list[str] = []

    async def _abstains(left: str, right: str, score: float) -> bool | None:
        del left, right, score
        asked.append("first")
        return None

    async def _decides(left: str, right: str, score: float) -> bool | None:
        del left, right, score
        asked.append("second")
        return True

    # Act
    verdict = await first_verdict("Chucri", "Azouz", 0.7, adjudicators=(_abstains, _decides))

    # Assert
    assert verdict is True
    assert asked == ["first", "second"]


async def test_a_chain_stops_at_the_first_adjudicator_with_an_opinion() -> None:
    """The expensive half must not be reached when a cheap rule already decided — this is the
    assertion that makes `model_calls` a number an operator can trust rather than a ceiling.
    """
    # Arrange
    asked: list[str] = []

    async def _expensive(left: str, right: str, score: float) -> bool | None:
        del left, right, score
        asked.append("expensive")
        return True

    # Act
    verdict = await first_verdict(
        "Chucri", "Azouz", 0.1, adjudicators=(threshold_adjudicator(), _expensive)
    )

    # Assert
    assert verdict is False
    assert asked == []


async def test_a_chain_whose_every_member_abstains_abstains() -> None:
    """Nobody decided, so the pass leaves the two entities alone and counts an abstention. The
    alternative — defaulting to *different* — would report a decision nobody made.
    """
    # Act
    verdict = await first_verdict("a", "b", 0.7, adjudicators=(_always(None), _always(None)))

    # Assert
    assert verdict is None


async def test_an_empty_chain_abstains_rather_than_deciding() -> None:
    """An empty collection means *I did not find it*, never *it is not there* — `L5.9`'s rule
    applied to a chain nobody configured.
    """
    # Act
    verdict = await first_verdict("a", "b", 0.7, adjudicators=())

    # Assert
    assert verdict is None


def test_a_band_whose_floor_is_above_its_ceiling_is_refused() -> None:
    """A band with no interior would make every pair either merged or refused and never asked,
    silently turning the expensive pass off. Refused where it is configured, not discovered as
    a `model_calls` of zero on a corpus full of ambiguity.
    """
    # Act / Assert
    with pytest.raises(ValueError, match="floor"):
        threshold_adjudicator(floor=0.9, ceiling=0.8)
