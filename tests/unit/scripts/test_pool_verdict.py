"""`scripts/pool_verdict.py` — ledger **40.8**: `eval/pool-promotion/protocol.toml`'s verdict.

Five outcomes read off a paired 95% interval [L, U] and its point estimate d, first match wins,
and the rule and oracle arms read jointly so a null from extraction is never reported as a null
from promotion.
"""

from __future__ import annotations

import pytest
from pool_verdict import joint_reading, verdict


@pytest.mark.parametrize(
    ("low", "high", "mean", "underpowered", "expected"),
    [
        (-0.08, -0.01, -0.04, False, "harm"),
        (-0.02, 0.04, 0.01, False, "benefit ruled out"),
        (0.03, 0.12, 0.07, False, "worthwhile"),
        (0.01, 0.09, 0.04, False, "positive, below worthwhile"),
        (-0.02, 0.09, 0.03, False, "inconclusive"),
        (-0.02, 0.09, 0.03, True, "inconclusive (underpowered)"),
    ],
)
def test_the_verdict_is_the_first_protocol_outcome_the_interval_satisfies(
    low: float, high: float, mean: float, underpowered: bool, expected: str
) -> None:
    assert verdict(low, high, mean, underpowered=underpowered) == expected


@pytest.mark.parametrize(
    ("rule", "oracle", "expected"),
    [
        ("inconclusive", "worthwhile", "the extractor fails where promotion would succeed"),
        (
            "benefit ruled out",
            "positive, below worthwhile",
            "the extractor fails where promotion would succeed",
        ),
        ("worthwhile", "worthwhile", "promotion helps with the rule's own anchors"),
        ("inconclusive", "harm", "promotion ruled out on this slice"),
        ("positive, below worthwhile", "benefit ruled out", "promotion ruled out on this slice"),
        ("inconclusive", "inconclusive", "no joint conclusion"),
    ],
)
def test_rule_and_oracle_are_read_together(rule: str, oracle: str, expected: str) -> None:
    assert joint_reading(rule, oracle) == expected
