"""Pre-registered verdicts — task **44.8**: `scripts/pool_verdict.py`'s reading, with a margin.

`scripts/pool_verdict.py` (ledger task **40.8**) reads a paired 95% interval `[low, high]` and its
point estimate `mean` off `eval/pool-promotion/protocol.toml`'s five outcomes, first match wins,
against that protocol's own fixed 0.05 margin. This module is the same reading, moved here with
the margin as a parameter, so any experiment can pre-register its own before it runs — the promotion
protocol's script now delegates to it (see `scripts/pool_verdict.py`'s own `verdict`).

`EffectVerdict.status` maps each of the five outcomes onto `ClaimStatus`, `manual/evidence.md`
§3's own five statuses — used by later claim work, not by anything in this task.
"""

from __future__ import annotations

from enum import StrEnum


class ClaimStatus(StrEnum):
    """The five statuses `manual/evidence.md` §3 reads a claim as."""

    HELPS = "helps"
    NO_GAIN = "no-gain"
    HARMS = "harms"
    WRONG_QUESTIONS = "wrong-questions"
    NEVER = "never"


class EffectVerdict(StrEnum):
    """A paired interval's reading against a margin — see the module docstring."""

    HARM = "harm"
    BENEFIT_RULED_OUT = "benefit-ruled-out"
    WORTHWHILE = "worthwhile"
    POSITIVE_BELOW_MARGIN = "positive-below-margin"
    INCONCLUSIVE = "inconclusive"

    @property
    def status(self) -> ClaimStatus:
        """The `ClaimStatus` this verdict carries — see the module docstring."""
        match self:
            case EffectVerdict.HARM:
                return ClaimStatus.HARMS
            case EffectVerdict.BENEFIT_RULED_OUT | EffectVerdict.INCONCLUSIVE:
                return ClaimStatus.NO_GAIN
            case EffectVerdict.WORTHWHILE | EffectVerdict.POSITIVE_BELOW_MARGIN:
                return ClaimStatus.HELPS


def verdict(low: float, high: float, mean: float, *, margin: float) -> EffectVerdict:
    """Read `[low, high]` and `mean` against `margin` — see the module docstring.

    First match wins: `high < 0` is `HARM`; `high < margin` is `BENEFIT_RULED_OUT`; `low > 0 and
    mean >= margin` is `WORTHWHILE`; `low > 0` is `POSITIVE_BELOW_MARGIN`; anything else is
    `INCONCLUSIVE`.

    Raises `ValueError` naming `margin` when it is not strictly positive — a non-positive margin
    reads every positive difference as `WORTHWHILE`, which is not a margin at all.
    """
    if margin <= 0:
        raise ValueError(f"margin must be positive, got {margin!r}.")
    if high < 0:
        return EffectVerdict.HARM
    if high < margin:
        return EffectVerdict.BENEFIT_RULED_OUT
    if low > 0 and mean >= margin:
        return EffectVerdict.WORTHWHILE
    if low > 0:
        return EffectVerdict.POSITIVE_BELOW_MARGIN
    return EffectVerdict.INCONCLUSIVE


__all__ = ["ClaimStatus", "EffectVerdict", "verdict"]
