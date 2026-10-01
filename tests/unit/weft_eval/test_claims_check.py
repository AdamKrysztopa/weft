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
from weft_eval.fingerprint import ClaimFingerprint, LiveEvidence, Staleness
from weft_eval.verdict import ClaimStatus, EffectVerdict
from weft_kernel.errors import UnresolvedNameError

REPO = Path(__file__).resolve().parents[3]
COMMITTED = sorted((REPO / "eval" / "claims").glob("*.toml"))

_CLAIM = """\
[claim]
schema = 2
id = "{id}"
rung = "{rung}"
baseline = "{baseline}"
metric = "{metric}"
status = "{status}"
{verdict_line}basis = "records"
margin = {margin}
{extra}
[claim.population]
benchmark = "validation-en"
language = "en"
question_sets = []

[claim.source]
experiment = "eval/experiments/whole-corpus-en.toml"
invocation = "77a0ab088ccd43688bc0403932c95e6b"
"""


_VERDICT_OF_STATUS = {"helps": "worthwhile", "no-gain": "benefit-ruled-out", "harms": "harm"}


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
    extra: str = "",
    verdict: str | None = None,
) -> Claim:
    verdict = verdict or _VERDICT_OF_STATUS.get(status)
    verdict_line = f'verdict = "{verdict}"\n' if verdict else ""
    path = root / "eval" / "claims" / f"{id}.toml"
    path.write_text(
        _CLAIM.format(
            id=id,
            rung=rung,
            baseline=baseline,
            metric=metric,
            status=status,
            verdict_line=verdict_line,
            margin=margin,
            extra=extra,
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
    # the mean reads as positive-below-margin; one above the interval's top reads as benefit
    # ruled out.
    check = check_claim(_claim(copied, margin=0.09, verdict="positive-below-margin"), root=copied)

    # Assert
    assert check.derived is ClaimStatus.HELPS
    assert check.verdict is EffectVerdict.POSITIVE_BELOW_MARGIN
    assert check.stated_verdict is EffectVerdict.POSITIVE_BELOW_MARGIN
    with pytest.raises(ClaimMismatchError):
        check_claim(_claim(copied, margin=0.2), root=copied)


def test_a_positive_effect_below_the_margin_cannot_be_stated_as_worthwhile(copied: Path) -> None:
    # Arrange — both read as 'helps', so only the verdict tells them apart.
    claim = _claim(copied, margin=0.09, verdict="worthwhile")

    # Act / Assert
    with pytest.raises(ClaimMismatchError) as raised:
        check_claim(claim, root=copied)

    # Assert
    message = str(raised.value)
    assert "states 'helps' (worthwhile)" in message
    assert "positive-below-margin" in message


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


def test_a_claim_names_the_arm_that_ran_when_the_rung_is_not_a_pipeline_name(
    copied: Path,
) -> None:
    # Arrange
    claim = _claim(
        copied,
        rung="a-shipped-rung",
        baseline="another-shipped-rung",
        extra='arm = "whole-corpus"\nbaseline_arm = "baseline"\n',
    )

    # Act
    result = check_claim(claim, root=copied)

    # Assert
    assert result.derived is ClaimStatus.HELPS


def test_an_arm_name_the_experiment_does_not_have_is_refused_naming_the_arms_it_has(
    copied: Path,
) -> None:
    # Act / Assert
    with pytest.raises(UnresolvedClaimArmError) as raised:
        check_claim(_claim(copied, extra='arm = "no-such-arm"\n'), root=copied)

    # Assert
    assert isinstance(raised.value, UnresolvedNameError)
    assert set(raised.value.valid_options) == {"baseline", "whole-corpus"}


def _hyde_claim(tmp_path: Path, *, extra: str = "") -> Claim:
    # `orb-hyde-questions` runs `vector-retrieve` in two arms and `hyde-vector-retrieve` in two.
    path = tmp_path / "c.hyde.toml"
    path.write_text(
        _CLAIM.format(
            id="c.hyde",
            rung="hyde-vector-retrieve",
            baseline="vector-retrieve",
            metric="mrr@5",
            status="no-gain",
            verdict_line='verdict = "benefit-ruled-out"\n',
            margin=0.05,
            extra=extra,
        ).replace(
            'experiment = "eval/experiments/whole-corpus-en.toml"\n'
            'invocation = "77a0ab088ccd43688bc0403932c95e6b"',
            'experiment = "eval/experiments/orb-hyde-questions.toml"\n'
            'invocation = "cbd9fc318b1e4d2eb11b95d346ee4b07"',
        ),
        encoding="utf-8",
    )
    return load_claim(path)


def test_two_arms_sharing_a_pipeline_are_refused_until_the_claim_names_one(
    tmp_path: Path,
) -> None:
    # Act / Assert
    with pytest.raises(UnresolvedClaimArmError) as raised:
        check_claim(_hyde_claim(tmp_path), root=REPO)

    # Assert
    assert set(raised.value.valid_options) == {"hyde", "questions-hyde"}
    assert "Name the one it means" in str(raised.value)


def test_a_claim_naming_both_arms_of_a_shared_pipeline_is_recomputed(tmp_path: Path) -> None:
    # Arrange
    claim = _hyde_claim(tmp_path, extra='arm = "hyde"\nbaseline_arm = "plain"\n')

    # Act
    result = check_claim(claim, root=REPO)

    # Assert
    assert result.reproducible is True
    assert result.derived is ClaimStatus.NO_GAIN


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


def _fingerprint(**changes: str) -> ClaimFingerprint:
    fields = {"rung": "r", "baseline": "b", "index": "i", "baseline_index": "i", **changes}
    return ClaimFingerprint.model_validate(fields)


def _pinned(root: Path, fingerprint: ClaimFingerprint | None) -> Claim:
    claim = _claim(root)
    return claim.model_copy(update={"fingerprint": fingerprint})


def test_a_claim_pinned_to_the_live_fingerprint_is_valid_even_from_another_major(
    copied: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — recorded under 2.x/3.x, run under 99.0.0: the version moved, the pipelines did not.
    def newer(_name: str) -> str:
        return "99.0.0"

    monkeypatch.setattr("weft_eval.claims_check.metadata.version", newer)
    live = LiveEvidence(fingerprint=_fingerprint(), unresolved=None)

    # Act
    check = check_claim(_pinned(copied, _fingerprint()), root=copied, live=live)

    # Assert
    assert check.staleness is Staleness.VALID
    assert check.stale is None
    assert check.derived is ClaimStatus.HELPS


def test_a_pipeline_changed_since_the_pin_makes_the_claim_definitely_stale_not_refused(
    copied: Path,
) -> None:
    # Arrange
    live = LiveEvidence(fingerprint=_fingerprint(rung="moved"), unresolved=None)

    # Act
    check = check_claim(_pinned(copied, _fingerprint()), root=copied, live=live)

    # Assert
    assert check.staleness is Staleness.DEFINITELY_STALE
    assert check.stale is not None and "rung changed" in check.stale
    assert check.derived is ClaimStatus.HELPS


def test_an_unpinned_claim_from_another_major_is_possibly_stale_naming_the_version(
    copied: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    def newer(_name: str) -> str:
        return "99.0.0"

    monkeypatch.setattr("weft_eval.claims_check.metadata.version", newer)
    live = LiveEvidence(fingerprint=_fingerprint(), unresolved=None)

    # Act
    check = check_claim(_claim(copied), root=copied, live=live)

    # Assert
    assert check.staleness is Staleness.POSSIBLY_STALE
    assert check.stale is not None
    assert "99.0.0" in check.stale
    assert "weft eval claims pin" in check.stale


def test_a_claim_checked_with_no_live_tree_is_never_read_as_valid(copied: Path) -> None:
    # Act
    check = check_claim(_pinned(copied, _fingerprint()), root=copied)

    # Assert
    assert check.staleness is Staleness.POSSIBLY_STALE


def test_a_ledger_claim_is_reported_as_not_reproducible(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "h.one.toml"
    path.write_text(
        """\
[claim]
schema = 2
id = "h.one"
rung = "hybrid-then-generate"
baseline = "retrieve-then-generate"
metric = "answer_correctness"
status = "no-gain"
verdict = "benefit-ruled-out"
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
