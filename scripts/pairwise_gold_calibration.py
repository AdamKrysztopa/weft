"""Gold-referee calibration of the pairwise judge — task 44.43b, owner's choice 2026-09-29.

On a question set with gold answers, two arms' answers whose gold-based `answer_correctness`
differ clearly have a known better answer. The pairwise judge's verdict on those pairs is scored
against it: agreement over the pairs the judge decided, with a Wilson interval, and ties counted
apart. Only judging calls a model.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence

from pydantic import BaseModel


class CalibrationRow(BaseModel):
    """A single judged pair and its correctness against gold."""

    model_config = {"frozen": True}

    question: str
    gold: str
    judge: str
    arm_a: str = ""
    arm_b: str = ""
    delta: float = 0.0


class Agreement(BaseModel):
    """Summary statistics over decided pairs."""

    model_config = {"frozen": True}

    agree: int
    decided: int
    ties: int
    rate: float | None
    low: float | None
    high: float | None


def clear_pairs(
    scores: Mapping[str, Mapping[str, float]], *, threshold: float
) -> list[tuple[str, str, str]]:
    """Find arm pairs whose gold-based scores differ by >= threshold on each question.

    Args:
        scores: Mapping from arm name to mapping from question id to score.
        threshold: Minimum score difference to include a pair.

    Returns:
        List of (arm_a, arm_b, question) tuples, ordered by arm pair then question id.
        Both arm names appear in sorted order as they were presented to combinations.
    """
    pairs: list[tuple[str, str, str]] = []
    for arm_a, arm_b in itertools.combinations(sorted(scores), 2):
        for q in sorted(scores[arm_a]):
            if q in scores[arm_b] and abs(scores[arm_a][q] - scores[arm_b][q]) >= threshold:
                pairs.append((arm_a, arm_b, q))
    return pairs


def agreement(rows: Sequence[CalibrationRow]) -> Agreement:
    """Compute agreement statistics and Wilson interval.

    Args:
        rows: Judged pairs with gold verdicts.

    Returns:
        Agreement with rate and Wilson 95% CI (None when no decided pairs).
    """
    ties = sum(1 for r in rows if r.judge == "tie")
    decided = len(rows) - ties
    agree = sum(1 for r in rows if r.judge == r.gold and r.judge != "tie")

    rate: float | None = None
    low: float | None = None
    high: float | None = None

    if decided > 0:
        rate = agree / decided
        z = 1.96
        p = rate
        n = decided
        den = 1 + z * z / n
        numerator = p + z * z / (2 * n)
        margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        low = (numerator - margin) / den
        high = (numerator + margin) / den

    return Agreement(agree=agree, decided=decided, ties=ties, rate=rate, low=low, high=high)
