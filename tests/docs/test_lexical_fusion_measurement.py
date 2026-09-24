"""`eval/lexical-fusion/measurement.json` is held to the records it claims — ledger **21.9**.

The shape and the argument are `tests/docs/test_text_normalization_measurement.py`'s, one task
later and one factor wider. `12-roadmap.md`'s standing rule is that a shipped default moves on a
measurement over Weft's own corpus; this file is the other half of that rule, because a *statement*
about a measurement is a claim like any other and what makes it checkable is the run records
sitting beside it.

**It does not re-run the sweep.** That needs two containers, the materialised corpus, two index
builds and several minutes. What it asserts is the half that actually rots: that the numbers
written in the statement are the numbers in the records.

**And it asserts the statement's own sharp claim**, which is not a number but an *equality*:
`precision@5` and `recall@5` are identical between the two reciprocal-rank arms, so replacing
Postgres full-text search with real BM25 moved the retrieved set by nothing at all. A check that
only compared each arm against its own record would pass while that claim rotted — the claim is
about a relationship *between* two records, and `L5.6`'s one-source shape is avoided here because
the two sides are two different runs of two different rankings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, cast

import pytest

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_MEASUREMENT: Final[Path] = _REPO_ROOT / "eval" / "lexical-fusion" / "measurement.json"
_RUNS: Final[Path] = _REPO_ROOT / "eval" / "lexical-fusion" / "runs"

#: How close a recorded mean must be to the statement's. The statement rounds for a reader and the
#: records carry full precision, so an exact comparison would fail on the rounding rather than on
#: the drift this check is for — the same tolerance the `21.2` sibling uses, for its reason.
_TOLERANCE: Final[float] = 5e-4

#: The metrics the statement quotes per arm. Named rather than derived from the statement's own
#: keys, so a statement that quietly stopped quoting one would fail here rather than be checked
#: against a shorter list of its own choosing.
_QUOTED: Final[tuple[str, ...]] = (
    "mean_average_precision",
    "mrr@5",
    "ndcg@5",
    "precision@5",
    "recall@5",
)


def _statement() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_MEASUREMENT.read_text(encoding="utf-8")))


def _recorded(run_id: str) -> dict[str, float]:
    """Every metric mean in one persisted `RunRecord`, by its reported name."""
    record = json.loads((_RUNS / f"{run_id}.json").read_text(encoding="utf-8"))
    metrics = cast(dict[str, Any], record["metrics"])
    return {
        name: float(body["value"]["mean"])
        for name, body in metrics.items()
        if "mean" in body.get("value", {})
    }


def test_every_number_the_statement_quotes_is_in_the_record_it_names() -> None:
    # Arrange
    arms = cast(dict[str, Any], _statement()["arms"])

    # Act
    drift: list[str] = []
    for arm, body in arms.items():
        recorded = _recorded(cast(str, body["run"]))
        for metric in _QUOTED:
            claimed = float(body[metric])
            actual = recorded[metric]
            if abs(claimed - actual) > _TOLERANCE:
                drift.append(f"{arm} {metric}: statement {claimed}, record {actual}")

    # Assert
    assert not drift, (
        "the measurement statement and its own run records disagree:\n  " + "\n  ".join(drift)
    )


def test_the_sharp_claim_holds_between_the_two_reciprocal_rank_arms() -> None:
    """The statement's finding, asserted as the relationship it actually is.

    *"Swapping Postgres full-text search for real BM25 under reciprocal-rank fusion moves
    `precision@5` and `recall@5` by exactly nothing."* Two runs, two rankings, one number each —
    and if a future change to either arm moved one of them, the statement would become false while
    every per-arm assertion above still passed.
    """
    # Arrange
    arms = cast(dict[str, Any], _statement()["arms"])
    fts = _recorded(cast(str, arms["fts + reciprocal-rank-fusion"]["run"]))
    bm25 = _recorded(cast(str, arms["bm25 + reciprocal-rank-fusion"]["run"]))

    # Assert
    assert fts["precision@5"] == pytest.approx(bm25["precision@5"], abs=_TOLERANCE)
    assert fts["recall@5"] == pytest.approx(bm25["recall@5"], abs=_TOLERANCE)


def test_the_cross_is_actually_crossed() -> None:
    """Non-vacuity for the design rather than for the numbers.

    A sweep that ran three arms, or four arms that were not the four cells, would still satisfy
    every assertion above. What makes the interaction readable is that both factors appear at both
    levels of the other, and that is a property of the statement's own key set.
    """
    # Arrange
    arms = cast(dict[str, Any], _statement()["arms"])

    # Assert
    assert set(arms) == {
        "fts + reciprocal-rank-fusion",
        "bm25 + reciprocal-rank-fusion",
        "fts + normalized-score-fusion",
        "bm25 + normalized-score-fusion",
    }
    assert len({body["run"] for body in arms.values()}) == 4, "four cells, four distinct runs"


def test_every_record_the_statement_names_is_tracked_beside_it() -> None:
    """Stops a lexical-fusion measurement resting on a question set that lives nowhere.

    Phase 10's exit was measured on a question set that lived nowhere and could not be
    reconstructed. This is what stops that here.
    """
    # Arrange
    arms = cast(dict[str, Any], _statement()["arms"])

    # Act
    missing = [
        cast(str, body["run"])
        for body in arms.values()
        if not (_RUNS / f"{body['run']}.json").is_file()
    ]

    # Assert
    assert not missing, f"the statement names run records that are not beside it: {missing}"


def test_the_statement_still_says_no_default_moved() -> None:
    """**The claim most likely to rot silently**, because it is prose rather than a number.

    Both of this phase's new capabilities won their arm of the cross, and the temptation a reader
    of those numbers will feel is to make one of them the default. The statement refuses, on one
    stated ground: the dense arm was Weft's hash embedder, whose vectors carry no semantic meaning,
    so `normalized-score-fusion`'s advantage may be its ability to see that one arm is noise rather
    than any general property of score fusion. If that paragraph is ever deleted, the numbers above
    become an argument for a change nobody measured.
    """
    # Arrange
    statement = _statement()

    # Assert
    caveat = cast(str, statement["what_this_does_not_say"])
    assert "hash embedder" in caveat
    assert "No default moves" in caveat
    assert cast(str, statement["what_would_change_it"]).strip(), (
        "a refusal names what would lift it"
    )
