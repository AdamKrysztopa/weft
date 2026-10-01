"""Task 44.31 — a claim is recomputed from the committed records it names, never trusted.

The fixtures copy one real experiment (`whole-corpus-en`, two repetitions, 107 questions) and its
run records, so what is recomputed is a real paired interval. A claim file is then written against
the copy with a stated status, and the check must agree with the records or refuse by name.
"""

import shutil
from pathlib import Path

import pytest

from weft_eval.claims import Claim, ClaimBasis, load_claim, load_claims
from weft_eval.claims_check import (
    ClaimMismatchError,
    UnresolvedClaimArmError,
    check_claim,
)
from weft_eval.verdict import ClaimStatus
from weft_kernel.errors import UnresolvedNameError

REPO = Path(__file__).resolve().parents[3]
COMMITTED = sorted((REPO / "eval" / "claims").glob("*.toml"))

_CLAIM = """\
[claim]
schema = 1
id = "{id}"
rung = "{rung}"
baseline = "{baseline}"
metric = "{metric}"
status = "{status}"
basis = "records"
margin = {margin}

[claim.population]
benchmark = "validation-en"
language = "en"
question_sets = []

[claim.source]
experiment = "eval/experiments/whole-corpus-en.toml"
invocation = "77a0ab088ccd43688bc0403932c95e6b"
"""


@pytest.fixture
def copied(tmp_path: Path) -> Path:
    experiments = tmp_path / "eval" / "experiments"
    experiments.mkdir(parents=True)
    shutil.copy(REPO / "eval/experiments/whole-corpus-en.toml", experiments)
    shutil.copytree(
        REPO / "eval/experiments/whole-corpus-en/runs", experiments / "whole-corpus-en/runs"
    )
    (tmp_path / "eval" / "claims").mkdir()
    return tmp_path


def _claim(
    root: Path,
    *,
    status: str = "helps",
    rung: str = "whole-corpus-wide-then-generate",
    baseline: str = "retrieve-then-generate",
    metric: str = "answer_correctness",
    margin: float = 0.05,
    id: str = "c.one",  # noqa: A002
) -> Claim:
    path = root / "eval" / "claims" / f"{id}.toml"
    path.write_text(
        _CLAIM.format(
            id=id, rung=rung, baseline=baseline, metric=metric, status=status, margin=margin
        ),
        encoding="utf-8",
    )
    return load_claim(path)


def test_a_claim_the_records_support_reports_the_recomputed_interval(copied: Path) -> None:
    # Act
    check = check_claim(_claim(copied), root=copied)

    # Assert — the interval the evidence page publishes for this experiment.
    assert check.reproducible
    assert check.derived is ClaimStatus.HELPS
    assert check.mean == pytest.approx(0.0751, abs=5e-4)
    assert check.low == pytest.approx(0.0389, abs=5e-4)
    assert check.high == pytest.approx(0.1165, abs=5e-4)
    assert check.n == 210
    assert check.margin == 0.05


@pytest.mark.parametrize("stated", ["no-gain", "harms"])
def test_a_status_the_records_do_not_support_is_refused_with_the_numbers(
    copied: Path, stated: str
) -> None:
    # Act / Assert
    with pytest.raises(ClaimMismatchError) as raised:
        check_claim(_claim(copied, status=stated), root=copied)

    # Assert
    message = str(raised.value)
    assert f"states '{stated}'" in message
    assert "+0.075" in message
    assert "'helps'" in message


def test_a_tighter_margin_changes_what_the_same_records_support(copied: Path) -> None:
    # Arrange — the mean is 0.075 and its interval's low end is above zero, so a margin above
    # the mean reads as positive-below-margin, which is still 'helps'; one above the interval's
    # top reads as benefit ruled out.
    check = check_claim(_claim(copied, margin=0.09), root=copied)

    # Assert
    assert check.derived is ClaimStatus.HELPS
    with pytest.raises(ClaimMismatchError):
        check_claim(_claim(copied, margin=0.2), root=copied)


def test_an_arm_the_experiment_does_not_run_is_refused_naming_the_rungs_it_does(
    copied: Path,
) -> None:
    # Act / Assert
    with pytest.raises(UnresolvedClaimArmError) as raised:
        check_claim(_claim(copied, rung="hyde-then-generate"), root=copied)

    # Assert
    assert isinstance(raised.value, UnresolvedNameError)
    assert "whole-corpus-wide-then-generate" in raised.value.valid_options
    assert "retrieve-then-generate" in raised.value.valid_options


def test_a_metric_no_record_scored_is_refused_naming_the_ones_that_were(copied: Path) -> None:
    # Act / Assert
    with pytest.raises(
        ClaimMismatchError, match="no record scored 'faithfulness'.*answer_correctness"
    ):
        check_claim(_claim(copied, metric="faithfulness"), root=copied)


@pytest.mark.parametrize("stated", ["wrong-questions", "never"])
def test_a_status_no_interval_can_give_is_asserted_not_checked(copied: Path, stated: str) -> None:
    # Act
    check = check_claim(_claim(copied, status=stated), root=copied)

    # Assert
    assert check.derived is None
    assert check.reproducible
    assert check.stated.value == stated


def test_records_that_are_missing_are_refused(copied: Path) -> None:
    # Arrange
    shutil.rmtree(copied / "eval/experiments/whole-corpus-en/runs")

    # Act / Assert
    with pytest.raises(ClaimMismatchError, match="no run records"):
        check_claim(_claim(copied), root=copied)


def test_a_claim_from_another_major_version_is_marked_stale_not_refused(
    copied: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange

    def newer(_name: str) -> str:
        return "99.0.0"

    monkeypatch.setattr("weft_eval.claims_check.metadata.version", newer)

    # Act
    check = check_claim(_claim(copied), root=copied)

    # Assert
    assert check.stale is not None
    assert "99.0.0" in check.stale
    assert check.derived is ClaimStatus.HELPS


def test_a_ledger_claim_is_reported_as_not_reproducible(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "h.one.toml"
    path.write_text(
        """\
[claim]
schema = 1
id = "h.one"
rung = "hybrid-then-generate"
baseline = "retrieve-then-generate"
metric = "answer_correctness"
status = "no-gain"
basis = "ledger"
ledger = "Phase 39"

[claim.population]
benchmark = "validation-en"
language = "en"
question_sets = []
""",
        encoding="utf-8",
    )
    claim = load_claim(path)

    # Act
    check = check_claim(claim, root=tmp_path)

    # Assert
    assert claim.basis is ClaimBasis.LEDGER
    assert not check.reproducible
    assert check.mean is None


@pytest.mark.parametrize("path", COMMITTED, ids=[path.stem for path in COMMITTED])
def test_every_committed_claim_still_holds_against_its_committed_records(path: Path) -> None:
    # Arrange
    claim = load_claim(path)

    # Act
    check = check_claim(claim, root=REPO)

    # Assert
    assert check.stated is claim.status


def test_the_committed_claims_directory_loads_and_is_not_empty() -> None:
    # Act
    claims = load_claims(REPO / "eval" / "claims")

    # Assert
    assert len(claims) >= 2
