"""`eval/text-normalization/measurement.json` is held to the records it claims — ledger **21.2**.

`12-roadmap.md`'s standing rule is that a shipped default moves on a measurement over Weft's own
corpus and not on a plausible argument. This file is the other half of that rule: a *statement*
about a measurement is a claim like any other, and the thing that makes it checkable is the run
records sitting beside it.

**The shape is `tests/docs/test_raptor_baseline.py`'s, and for its reason.** Phase 10's exit was
measured on a question set that lived nowhere — built by hand in a scratch directory and thrown
away — so its own subject could not be reconstructed. What stops that here is that the statement
names its run ids, the records are tracked, and this check reads the numbers back out of them.

It does **not** re-run the sweep. That needs the container, the materialised corpus and two
minutes, and a check that slow would either be skipped or would make the gate something people
work around. What it asserts is the cheap half and the half that actually rots: that the numbers
written in the statement are the numbers in the records.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, cast

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_MEASUREMENT: Final[Path] = _REPO_ROOT / "eval" / "text-normalization" / "measurement.json"
_RUNS: Final[Path] = _REPO_ROOT / "eval" / "text-normalization" / "runs"

#: How close a recorded mean must be to the statement's. The statement rounds for a reader; the
#: records carry full precision, so an exact comparison would fail on the rounding rather than on
#: a drift.
_TOLERANCE: Final[float] = 5e-7


def _statement() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(_MEASUREMENT.read_text(encoding="utf-8")))


def _record(run_id: str) -> dict[str, Any]:
    return cast(
        "dict[str, Any]", json.loads((_RUNS / f"{run_id}.json").read_text(encoding="utf-8"))
    )


def test_every_arm_the_statement_names_has_its_record_on_disk() -> None:
    """A statement citing a run nobody can open is the defect this whole file exists to refuse."""
    # Arrange
    statement = _statement()

    # Act / Assert
    for arm, described in statement["arms"].items():
        path = _RUNS / f"{described['run']}.json"
        assert path.is_file(), (
            f"arm {arm} names run {described['run']} and {path} does not exist — the statement "
            f"cites a measurement that cannot be checked."
        )


def test_the_absolute_numbers_are_the_ones_the_default_arms_record_holds() -> None:
    """The statement's headline figures, read back out of the record they came from."""
    # Arrange
    statement = _statement()
    default_run = statement["arms"]["0"]["run"]
    metrics = _record(default_run)["metrics"]

    # Act / Assert
    for name, claimed in statement["absolute_at_the_default"].items():
        recorded = metrics[name]["value"]["mean"]
        assert abs(recorded - claimed) < _TOLERANCE, (
            f"the statement says {name} is {claimed} at the default arm and run {default_run} "
            f"records {recorded}."
        )


def test_the_headroom_claim_is_true_so_the_null_result_is_not_a_ceiling() -> None:
    """`L10.3` — the trap this measurement was checked against and the reason it is believable.

    A metric already at its ceiling cannot move, so an arm that changes nothing and an arm that
    changes everything both read as zero. The statement claims recall@5 has ample headroom; this
    is that claim, asserted rather than asserted-in-prose.
    """
    # Arrange
    statement = _statement()
    recall = statement["absolute_at_the_default"]["recall@5"]

    # Assert
    assert 0.0 < recall < 0.9, (
        f"recall@5 at the default arm is {recall}. The statement's 'this is not a ceiling' "
        f"reasoning rests on it having room to move in both directions; at or near 1.0 the zero "
        f"differences would mean nothing at all."
    )


def test_the_set_metrics_really_are_identical_across_every_arm() -> None:
    """The sharp part of the finding: the top-5 *set* does not move, only the order within it.

    Asserted across all three records rather than taken from the paired differences, because the
    paired difference is a derived number and this is the fact underneath it. If a future arm ever
    does move `recall@5`, this fails and the statement's mechanism paragraph — `hybrid` fusing by
    rank, so the text arm's scale is discarded — needs re-deriving rather than re-reading.
    """
    # Arrange
    statement = _statement()
    runs = [described["run"] for described in statement["arms"].values()]

    # Act
    observed = {
        name: {_record(run)["metrics"][name]["value"]["mean"] for run in runs}
        for name in ("recall@5", "precision@5")
    }

    # Assert
    for name, values in observed.items():
        assert len(values) == 1, (
            f"{name} differs across the arms ({sorted(values)}), and the statement says the "
            f"retrieved set is identical and only its order moves."
        )
