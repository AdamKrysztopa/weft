"""Pre-registered verdicts in `weft_eval` — task 44.8.

The five-way reading of a paired interval against a margin was `scripts/pool_verdict.py`'s, with the
margin fixed at that protocol's 0.05. It now lives in `weft_eval.verdict` with the margin as a
parameter, so an experiment document can declare its own before it runs. Every verdict the committed
pool-promotion files record is recomputed through it, so the move changed no committed reading.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from weft_eval.verdict import ClaimStatus, EffectVerdict, verdict

REPO_ROOT = Path(__file__).resolve().parents[3]
_PROTOCOL_MARGIN = 0.05

#: The scripts' own spelling of each verdict, as the committed files carry it.
_SCRIPT_LABELS: Mapping[str, EffectVerdict] = {
    "harm": EffectVerdict.HARM,
    "benefit ruled out": EffectVerdict.BENEFIT_RULED_OUT,
    "worthwhile": EffectVerdict.WORTHWHILE,
    "positive, below worthwhile": EffectVerdict.POSITIVE_BELOW_MARGIN,
    "inconclusive": EffectVerdict.INCONCLUSIVE,
    "inconclusive (underpowered)": EffectVerdict.INCONCLUSIVE,
}


@pytest.mark.parametrize(
    ("low", "high", "mean", "expected"),
    [
        (-0.10, -0.01, -0.05, EffectVerdict.HARM),
        (-0.02, 0.04, 0.01, EffectVerdict.BENEFIT_RULED_OUT),
        (0.03, 0.12, 0.07, EffectVerdict.WORTHWHILE),
        (0.01, 0.09, 0.03, EffectVerdict.POSITIVE_BELOW_MARGIN),
        (-0.03, 0.09, 0.03, EffectVerdict.INCONCLUSIVE),
    ],
)
def test_each_interval_reads_as_its_verdict(
    low: float, high: float, mean: float, expected: EffectVerdict
) -> None:
    # Act
    result = verdict(low, high, mean, margin=_PROTOCOL_MARGIN)

    # Assert
    assert result is expected


def test_the_margin_is_the_document_s_not_a_constant() -> None:
    # Arrange — one interval, read against two margins.
    low, high, mean = 0.02, 0.09, 0.06

    # Act
    loose = verdict(low, high, mean, margin=0.05)
    strict = verdict(low, high, mean, margin=0.10)

    # Assert
    assert loose is EffectVerdict.WORTHWHILE
    assert strict is EffectVerdict.BENEFIT_RULED_OUT


def test_a_margin_that_is_not_positive_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="margin"):
        verdict(0.01, 0.02, 0.015, margin=0.0)


def test_each_verdict_maps_to_the_claim_status_the_evidence_page_uses() -> None:
    # Assert
    assert {member.value for member in ClaimStatus} == {
        "helps",
        "no-gain",
        "harms",
        "wrong-questions",
        "never",
    }
    assert EffectVerdict.HARM.status is ClaimStatus.HARMS
    assert EffectVerdict.BENEFIT_RULED_OUT.status is ClaimStatus.NO_GAIN
    assert EffectVerdict.INCONCLUSIVE.status is ClaimStatus.NO_GAIN
    assert EffectVerdict.WORTHWHILE.status is ClaimStatus.HELPS
    assert EffectVerdict.POSITIVE_BELOW_MARGIN.status is ClaimStatus.HELPS


def _children(node: object) -> list[object]:
    if isinstance(node, dict):
        return list(cast("dict[str, object]", node).values())
    if isinstance(node, list):
        return list(cast("list[object]", node))
    return []


def _recorded_readings(node: object) -> Iterator[tuple[Mapping[str, Any], str]]:
    """Every `{"mrr@5": interval, "verdict": label}` pair a committed verdict file holds."""
    children = _children(node)
    if isinstance(node, dict):
        entries = cast("dict[str, object]", node)
        label = entries.get("verdict")
        interval = entries.get("mrr@5")
        if isinstance(label, str) and isinstance(interval, dict):
            yield cast("dict[str, Any]", interval), label
    for child in children:
        yield from _recorded_readings(child)


def _recorded_by_arm(node: object) -> Iterator[tuple[Mapping[str, Any], str]]:
    """`pool_verdict.py`'s shape: a slice's `verdicts` names arms whose entries hold intervals."""
    children = _children(node)
    if isinstance(node, dict):
        entries = cast("dict[str, object]", node)
        verdicts = entries.get("verdicts")
        if isinstance(verdicts, dict):
            for arm, label in cast("dict[str, str]", verdicts).items():
                arm_entry = entries.get(arm)
                if isinstance(arm_entry, dict) and "mrr@5" in arm_entry:
                    yield cast("dict[str, Any]", arm_entry)["mrr@5"], label
    for child in children:
        yield from _recorded_by_arm(child)


def test_every_committed_pool_promotion_verdict_recomputes_identically() -> None:
    # Arrange
    readings: list[tuple[Mapping[str, Any], str]] = []
    for path in sorted((REPO_ROOT / "eval" / "pool-promotion").glob("*-verdict.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        readings.extend(_recorded_readings(document))
        readings.extend(_recorded_by_arm(document))
    readable = [
        (interval, label) for interval, label in readings if interval.get("low") is not None
    ]

    # Act
    recomputed = [
        verdict(interval["low"], interval["high"], interval["mean"], margin=_PROTOCOL_MARGIN)
        for interval, _ in readable
    ]

    # Assert — the committed set is non-empty and every reading agrees.
    assert len(readable) >= 20
    assert recomputed == [_SCRIPT_LABELS[label] for _, label in readable]
