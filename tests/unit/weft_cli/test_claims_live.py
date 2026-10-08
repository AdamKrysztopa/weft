"""Task 44.62 — the running tree's side of an evidence fingerprint, resolved the way a run resolves.

The rung and baseline are resolved against the shipped pipelines and the experiment's own beside it
(`eval/experiments/pipelines`), the index pipeline each arm read the same way, and nothing is read
from a machine's own `weft.toml`: a claim must not look stale because of whose laptop checked it.
"""

from pathlib import Path

import pytest

from weft_cli.claims_live import live_evidence
from weft_cli.route_ask import resolve_named_pipeline
from weft_engine import registry_bootstrap
from weft_eval.claims import load_claim, load_claims
from weft_eval.fingerprint import stage_identity
from weft_retrieve.profile import PROFILER_VERSION

REPO = Path(__file__).resolve().parents[3]
CLAIMS = REPO / "eval" / "claims"


@pytest.fixture(scope="module")
def deps() -> registry_bootstrap.Dependencies:
    return registry_bootstrap.resolution_dependencies()


def test_the_whole_corpus_claim_is_fingerprinted_from_the_pipelines_it_names(
    deps: registry_bootstrap.Dependencies,
) -> None:
    # Arrange
    claim = load_claim(CLAIMS / "whole-corpus.fetch-operator.answer-correctness.toml")

    # Act
    live = live_evidence(claim, root=REPO, deps=deps)

    # Assert
    assert live.fingerprint is not None, live.unresolved
    rung = resolve_named_pipeline(
        "whole-corpus-wide-then-generate",
        registry=deps.registry,
        reports=deps.reports,
        contributions=deps.contributions,
    )
    assert live.fingerprint.rung == stage_identity(rung)
    assert live.fingerprint.rung != live.fingerprint.baseline
    assert live.fingerprint.judge is not None
    assert live.fingerprint.profiler == PROFILER_VERSION


def test_a_retrieval_metric_pins_no_judge_and_a_claim_with_no_regime_pins_no_profiler(
    deps: registry_bootstrap.Dependencies,
) -> None:
    # Arrange — the control that must differ from the claim above.
    claim = load_claim(CLAIMS / "dedupe-then-generate.fetch-en.recall-at-5.toml")

    # Act
    live = live_evidence(claim, root=REPO, deps=deps)

    # Assert
    assert live.fingerprint is not None, live.unresolved
    assert live.fingerprint.judge is None
    assert live.fingerprint.profiler is None


def test_a_router_claim_pins_the_profiler_because_the_router_reads_a_profile(
    deps: registry_bootstrap.Dependencies,
) -> None:
    # Arrange
    claim = load_claim(CLAIMS / "route.fetch-operator.answer-correctness.toml")

    # Act
    live = live_evidence(claim, root=REPO, deps=deps)

    # Assert
    assert live.fingerprint is not None, live.unresolved
    assert live.fingerprint.profiler == PROFILER_VERSION


def test_a_claim_naming_a_pipeline_that_does_not_resolve_says_which_rather_than_guessing(
    deps: registry_bootstrap.Dependencies, tmp_path: Path
) -> None:
    # Arrange — the real experiment, with the one document it needs removed from beside it.
    claim = load_claim(CLAIMS / "whole-corpus.fetch-operator.answer-correctness.toml")
    experiments = tmp_path / "eval" / "experiments"
    experiments.mkdir(parents=True)
    source = (REPO / "eval/experiments/whole-corpus-en.toml").read_text(encoding="utf-8")
    (experiments / "whole-corpus-en.toml").write_text(
        source.replace("whole-corpus-wide-then-generate", "no-such-rung"), encoding="utf-8"
    )

    # Act
    live = live_evidence(claim, root=tmp_path, deps=deps)

    # Assert
    assert live.fingerprint is None
    assert live.unresolved is not None
    assert "no-such-rung" in live.unresolved


def test_every_committed_records_claim_resolves_or_says_why_not(
    deps: registry_bootstrap.Dependencies,
) -> None:
    # Arrange
    claims = [claim for claim in load_claims(CLAIMS) if claim.source is not None]

    # Act
    lives = {claim.id: live_evidence(claim, root=REPO, deps=deps) for claim in claims}

    # Assert — the floor: the claims a rule can cite are among those that resolve.
    unresolved = {cid: live.unresolved for cid, live in lives.items() if live.fingerprint is None}
    assert lives["whole-corpus.fetch-operator.answer-correctness"].fingerprint is not None
    assert lives["whole-corpus.global.answer-correctness"].fingerprint is not None
    assert all(reason for reason in unresolved.values())
