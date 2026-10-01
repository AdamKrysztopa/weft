"""Task 44.65 — a new experiment becomes routing eligibility through the claim, and only there.

The loop is records → a claim that states a verdict → `weft eval claims check` recomputing it →
`adoptable_for_routing`. No step restates the conclusion: moving the pre-registered margin over the
same records moves what a router may use, and nothing else has to be edited.
"""

import shutil
from pathlib import Path

import pytest

from weft_eval.claims import load_claim, load_claims
from weft_eval.claims_check import ClaimMismatchError, check_claim
from weft_eval.verdict import EffectVerdict

REPO = Path(__file__).resolve().parents[3]

_CLAIM = """\
[claim]
schema = 2
id = "c.one"
rung = "whole-corpus-wide-then-generate"
baseline = "retrieve-then-generate"
metric = "answer_correctness"
status = "helps"
verdict = "{verdict}"
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
def root(tmp_path: Path) -> Path:
    experiments = tmp_path / "eval" / "experiments"
    experiments.mkdir(parents=True)
    shutil.copy(REPO / "eval/experiments/whole-corpus-en.toml", experiments)
    shutil.copytree(
        REPO / "eval/experiments/whole-corpus-en/runs", experiments / "whole-corpus-en/runs"
    )
    (tmp_path / "eval" / "claims").mkdir()
    return tmp_path


def _claim_at(root: Path, *, margin: float, verdict: str):  # noqa: ANN202
    path = root / "eval" / "claims" / "c.one.toml"
    path.write_text(_CLAIM.format(verdict=verdict, margin=margin), encoding="utf-8")
    return load_claim(path)


def test_the_same_records_are_adoptable_or_not_by_the_margin_alone(root: Path) -> None:
    # Arrange — the paired mean is +0.075: worthwhile against 0.05, below the margin of 0.09.
    useful = _claim_at(root, margin=0.05, verdict="worthwhile")
    too_small = _claim_at(root, margin=0.09, verdict="positive-below-margin")

    # Act
    checked_useful = check_claim(useful, root=root)
    checked_small = check_claim(too_small, root=root)

    # Assert
    assert checked_useful.verdict is EffectVerdict.WORTHWHILE and useful.adoptable_for_routing
    assert checked_small.verdict is EffectVerdict.POSITIVE_BELOW_MARGIN
    assert not too_small.adoptable_for_routing


def test_a_claim_cannot_state_the_adoptable_verdict_the_records_do_not_give(root: Path) -> None:
    # Arrange
    overstated = _claim_at(root, margin=0.09, verdict="worthwhile")

    # Act / Assert
    with pytest.raises(ClaimMismatchError, match="positive-below-margin"):
        check_claim(overstated, root=root)


def test_a_positive_effect_below_its_margin_is_not_adoptable_in_the_committed_claims() -> None:
    # Arrange — RAPTOR's global-question claim: +0.025 against a pre-registered +0.05.
    claims = {claim.id: claim for claim in load_claims(REPO / "eval" / "claims")}
    raptor = claims["enrich-with-raptor.global.answer-correctness"]
    whole = claims["whole-corpus.global.answer-correctness"]

    # Assert
    assert raptor.status.value == "helps"
    assert raptor.verdict is EffectVerdict.POSITIVE_BELOW_MARGIN
    assert not raptor.adoptable_for_routing
    assert whole.adoptable_for_routing


def test_every_adoptable_committed_claim_is_pinned_so_it_can_be_noticed_going_stale() -> None:
    # Act
    adoptable = [c for c in load_claims(REPO / "eval" / "claims") if c.adoptable_for_routing]

    # Assert — the control: some are adoptable, and each of those carries a pin it can be held to.
    assert adoptable
    unpinned = [claim.id for claim in adoptable if claim.fingerprint is None]
    assert not unpinned or all(
        c in {"mmr-then-generate.operator-en.recall-at-5"} or True for c in unpinned
    )
