"""A three-valued vote on whether two surface forms name one entity. Ledger task **11.9**.

`weft_kg.resolution.resolve_clusters` blends a lexical and a vector score and merges everything
that clears `DEFAULT_SIMILARITY_THRESHOLD` — cheap, deterministic, and wrong exactly where the
blend is ambiguous. A **boolean** adjudicator asked about a pair in that ambiguous band could only
answer *same* or *different*, and a rule with no real evidence either way would have to invent one
of the two — the invention is invisible downstream: two entities that are one look exactly like two
entities that are two, and nothing in the graph says which case just happened. The third value is
*"I do not know, ask something with more evidence"*, and it is what lets a cheap rule abstain
honestly instead of guessing, and a caller chain that abstention on to a model that can actually
look at the two names.

**The band's own edges, not a second pair of numbers.** `threshold_adjudicator`'s `ceiling`
defaults to `weft_kg.resolution.DEFAULT_SIMILARITY_THRESHOLD` — imported, never re-spelled — because
it is the exact score at which the cheap pass already merged the pair. A pair that reaches it needs
no judgement; a second constant carrying "the same number" would drift the first time either one
was tuned without the other, and a reader would have no way to tell whether the drift was
deliberate. `DEFAULT_ADJUDICATION_FLOOR` is this module's own number: below it there is so little
lexical or vector agreement that the pair is plainly two things, and spending a model call there
buys nothing a cheaper rule did not already know.

**Why `weft_kernel.fallback.try_in_order` is not reused.** That combinator's whole point is the
opposite of this one's: its `NothingToProduce` *stops* a chain and returns it to the caller, because
a backend that legitimately extracted nothing has already answered the question — "I looked, and
there is nothing here" is a claim a second backend cannot improve on. An adjudicator that abstains
has not answered anything; it has *no opinion*, and the whole point of a chain of them is that an
abstention hands the question on rather than ending it. Reusing `try_in_order` here would read every
`None` as a terminal "nothing to produce" and stop before the adjudicator actually holding an
opinion — typically the model — ever ran.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Final

from weft_kg.resolution import DEFAULT_SIMILARITY_THRESHOLD

#: Below this score a pair is refused outright — plainly two different things, and no model call
#: is worth spending on it. This project's own choice, not carried: the donor asks no such
#: question of its own chain, because it has no floor separate from its ceiling.
DEFAULT_ADJUDICATION_FLOOR: Final[float] = 0.60

# weft-prior-work begin: graph-study
#
# The three-valued band and the first-non-`None` chain that reads it are the project owner's own
# `graph-study`, carried under `NOTICE` case 2. Three things inside this span are Weft's own
# reshaping rather than the donor's text, each commented at the line it changes: the pair-wise
# `(left, right, score)` signature below — the donor asks about one candidate name against a
# ranked list of others, never a single pair with its own score in hand — the plain `bool | None`
# return — the donor answers with a `MatchResult` dataclass carrying `bridged_ids`, which here is
# the store's own `UPDATE` and never a value handed back up the chain — and the `ValueError` this
# module raises on an inverted band, which the donor does not validate at all.

type Verdict = bool | None
#: An adjudicator asks about one pair and the score the cheap pass already computed for it — the
#: reshaped signature noted above, rather than the donor's "one name against a ranked candidate
#: list". Returns `True` (same entity), `False` (different), or `None` (no opinion, ask the next).
type Adjudicator = Callable[[str, str, float], Awaitable[bool | None]]


def threshold_adjudicator(
    *,
    floor: float = DEFAULT_ADJUDICATION_FLOOR,
    ceiling: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> Adjudicator:
    """The cheapest possible adjudicator: no model call, just where the score already sits.

    The band is `[floor, ceiling)` — closed at the bottom, open at the top. A score reaching the
    ceiling has already cleared the cheap pass's own merge threshold and needs no second opinion;
    a score below the floor is refused outright; anything between abstains, because the letters and
    the vectors alone did not settle it and the next adjudicator in the chain — typically a model —
    might.
    """
    if floor > ceiling:
        raise ValueError(
            f"floor ({floor}) is above ceiling ({ceiling}), which leaves the band with no "
            f"interior: every score would be either merged or refused and none would ever be "
            f"asked about. That would silently turn the expensive pass off rather than tune it, "
            f"and the only symptom an operator would see is a model_calls of zero on a corpus "
            f"full of ambiguity — so the inverted band is refused here, at construction, instead."
        )

    async def _adjudicate(left: str, right: str, score: float) -> bool | None:
        del left, right  # the plain `bool | None` return noted above: nothing to bridge, decide.
        if score >= ceiling:
            return True
        if score < floor:
            return False
        return None

    return _adjudicate


async def first_verdict(
    left: str, right: str, score: float, *, adjudicators: Sequence[Adjudicator]
) -> bool | None:
    """The first non-`None` answer from `adjudicators`, asked in order; `None` if none has one.

    Every candidate before the one that answers is asked and every candidate after it is not, so an
    expensive adjudicator placed last in the chain is only ever reached when nothing cheaper already
    decided — which is what makes a count of how often it ran a number an operator can trust rather
    than a ceiling. An empty chain, or a chain where every member abstains, abstains too: it means
    *nobody decided*, never *the answer is no* — `docs/internal/lessons.md` L5.9's rule for an empty
    collection, applied here to a chain that produced no opinion.
    """
    for adjudicate in adjudicators:
        verdict = await adjudicate(left, right, score)
        if verdict is not None:
            return verdict
    return None


# weft-prior-work end


__all__ = [
    "DEFAULT_ADJUDICATION_FLOOR",
    "Adjudicator",
    "Verdict",
    "first_verdict",
    "threshold_adjudicator",
]
