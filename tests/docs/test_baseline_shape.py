"""Prerequisite **V3** (`docs/09-release.md` §4.3) — the committed baseline, checked as a fact.

V3 wants *"the numbers produced before any technique"*, repeated, with *"each metric carrying
the interval its own repetitions produced"*, and it fails when *"the baseline was run once, in
which case it records no interval and no later run can be judged against it."* `eval/metrics.py`
refuses to build a record that breaks those rules; this file checks the **files that are
actually committed**, because the artefact is what Phase 4 inherits and Phase 6 republishes.

**No live run, no credential, no container.** The runs under `eval/baselines/` are read off
disk, so a contaminated interval is caught by the ordinary gate on a laptop rather than by
whoever next spends money on a measurement.

**The one thing this file guards that nothing else can.** A baseline says which corpus it was
measured over; whether that claim is true is a comparison against the manifest, and it is made
here by recomputing the corpus identity from `corpus/manifest.toml` rather than by trusting the
digest the run wrote about itself. `.phase2-findings.md` §15 is why: a figure over the operator
tier reported as though it were reproducible would be the reference's `gold_node_id_map` defect in a
new costume — *"a benchmark whose headline figure cannot be recomputed by the person reading
it"*.
"""

from pathlib import Path
from typing import Final

import pytest
from check_questions import load_questions, reproducible_questions
from fetch_corpus import Document, Tier, load_manifest
from metrics import MetricRecord
from run_baseline import BASELINES_DIR, BaselineRun, corpus_id, load_run

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANIFEST: Final[Path] = REPO_ROOT / "corpus" / "manifest.toml"


@pytest.fixture(scope="module")
def runs() -> tuple[tuple[Path, BaselineRun], ...]:
    """Every committed baseline, refused at load if anything in it disagrees with itself."""
    return tuple((path, load_run(path)) for path in sorted(BASELINES_DIR.glob("*.json")))


@pytest.fixture(scope="module")
def documents() -> tuple[Document, ...]:
    """Every document the tracked manifest declares."""
    _, entries = load_manifest(MANIFEST)
    return tuple(entries)


def test_a_baseline_exists_and_one_of_them_may_be_published(
    runs: tuple[tuple[Path, BaselineRun], ...],
) -> None:
    # Floor, and the one that stops this file passing on an empty directory. V3 is a *file*, not
    # an intention, and Phase 6's exit is a stranger reproducing it — which needs a run measured
    # over tiers that stranger can obtain.
    # Act
    publishable = [path.name for path, run in runs if run.reproducible]

    # Assert
    assert runs, (
        f"no baseline under {BASELINES_DIR}. V3 is an artefact that must exist as a file: "
        f"`uv run python eval/run_baseline.py --tiers fetch --repeats 3`"
    )
    assert publishable, (
        "every committed baseline rests on the operator tier, so none of them may be published: "
        "those documents are held under publisher copyright and cannot be obtained at any price"
    )


def test_every_baseline_was_run_more_than_once_and_records_what_it_spanned(
    runs: tuple[tuple[Path, BaselineRun], ...],
) -> None:
    # V3's failure clause, checked on the file rather than on the model that wrote it — the file
    # is what a later run is judged against, and hand-editing it is the way a derived tolerance
    # becomes a chosen one.
    # Act / Assert
    for path, run in runs:
        assert run.repeats > 1, f"{path.name}: run once, so it records no interval"
        for record in run.metrics:
            assert len(record.values) == run.repeats, (
                f"{path.name}: {record.metric} carries {len(record.values)} values for "
                f"{run.repeats} repetitions"
            )
            assert record.low <= record.mean <= record.high, (
                f"{path.name}: {record.metric} reports {record.mean} outside its own "
                f"[{record.low}, {record.high}]"
            )


def test_every_metric_names_the_depth_it_was_computed_at(
    runs: tuple[tuple[Path, BaselineRun], ...],
) -> None:
    # V4: "the `k` in a metric's name equals the `k` it computed". The reference reported
    # `ndcg_at_10` over four candidates, which is the same defect one directory over.
    # Act / Assert
    for path, run in runs:
        for record in run.metrics:
            name, _, depth = record.metric.rpartition("@")
            assert name and depth.isdigit(), (
                f"{path.name}: metric {record.metric!r} does not state a depth, so nothing can "
                f"check that it computed the one it is named for"
            )
            assert int(depth) == record.depth <= run.retrieval_depth, (
                f"{path.name}: {record.metric} was computed at depth {record.depth} over a "
                f"retrieval of {run.retrieval_depth}"
            )


def test_the_corpus_a_baseline_names_is_the_corpus_the_manifest_declares(
    runs: tuple[tuple[Path, BaselineRun], ...], documents: tuple[Document, ...]
) -> None:
    # Recomputed rather than trusted. A run states its own `corpus_id`, and a run whose id came
    # from somewhere other than the documents it lists is exactly the claim V3 cannot verify —
    # "a baseline from a different corpus".
    # Arrange
    by_tier = {tier: [entry for entry in documents if entry.tier is tier] for tier in Tier}

    # Act / Assert
    for path, run in runs:
        declared = [entry for tier in run.corpus.tiers for entry in by_tier[Tier(tier)]]
        assert run.corpus.documents == tuple(sorted(entry.id for entry in declared)), (
            f"{path.name}: names tiers {run.corpus.tiers} and lists "
            f"{len(run.corpus.documents)} documents; the manifest puts {len(declared)} there"
        )
        assert run.corpus.corpus_id == corpus_id(declared), (
            f"{path.name}: its corpus id is not the digest of the documents it names. Either "
            f"the corpus moved under it or the id was not computed from the manifest"
        )


def test_a_run_resting_on_the_operator_tier_says_it_cannot_be_reproduced(
    runs: tuple[tuple[Path, BaselineRun], ...],
) -> None:
    # `.phase2-findings.md` §15: two artefacts, never one. The label is derived from the tiers
    # here, exactly as `eval/run_baseline.py` derives it when it writes the file — so a run that
    # said `reproducible: true` over papers under publisher copyright is caught by the same rule
    # that should have set it, rather than by a reader noticing.
    # Act / Assert
    for path, run in runs:
        expected = all(Tier(tier).reproducible for tier in run.corpus.tiers)
        assert run.reproducible is expected, (
            f"{path.name}: says reproducible={run.reproducible} over tiers "
            f"{sorted(run.corpus.tiers)}. A number measured over documents a stranger cannot "
            f"obtain must be labelled unreproducible wherever it appears"
        )


def test_every_baseline_scored_the_questions_its_tiers_actually_allow(
    runs: tuple[tuple[Path, BaselineRun], ...], documents: tuple[Document, ...]
) -> None:
    # The subset is derived from the manifest's tiers and from nothing else (task 2.2). A run
    # that measured *fewer* questions than its tiers allow reports a number over a set nobody
    # can reconstruct; one that measured more rests on documents it did not index.
    # Arrange
    tiers = {entry.id: entry.tier.value for entry in documents}
    questions = load_questions()

    # Act / Assert
    for path, run in runs:
        allowed = reproducible_questions(
            questions, tiers=tiers, reproducible=frozenset(run.corpus.tiers)
        )
        assert run.questions == tuple(sorted(question.id for question in allowed)), (
            f"{path.name}: scored {len(run.questions)} questions where its tiers "
            f"{sorted(run.corpus.tiers)} allow {len(allowed)}"
        )


def test_no_aggregate_averaged_a_measurement_that_did_not_happen(
    runs: tuple[tuple[Path, BaselineRun], ...],
) -> None:
    # V4: "aggregates exclude errored metrics and report how many were excluded". Every
    # exclusion names a question the run actually asked and a repetition it actually ran, so the
    # count is auditable rather than a number in a field.
    # Act / Assert
    for path, run in runs:
        for excluded in run.excluded:
            assert excluded.question_id in run.questions, (
                f"{path.name}: excludes {excluded.question_id}, which this run never scored"
            )
            assert 1 <= excluded.repetition <= run.repeats, (
                f"{path.name}: excludes {excluded.question_id} in repetition "
                f"{excluded.repetition} of {run.repeats}"
            )
        for record in run.metrics:
            assert record.n_scored + record.n_excluded == len(run.questions) * run.repeats, (
                f"{path.name}: {record.metric} accounts for "
                f"{record.n_scored + record.n_excluded} measurements; the run made "
                f"{len(run.questions) * run.repeats}"
            )


def test_a_widened_interval_would_be_refused(
    runs: tuple[tuple[Path, BaselineRun], ...],
) -> None:
    # The self-test the checks above need to be worth running: they read a file that a model
    # validated on the way in, so "the committed baselines are fine" is only evidence if a
    # tampered one would not load. Widening a bound is the specific tamper that matters —
    # it makes every later run reproduce the baseline.
    # Arrange
    _, run = runs[0]
    record = run.metrics[0]

    # Act / Assert
    with pytest.raises(ValueError, match="low/high"):
        MetricRecord(
            metric=record.metric,
            depth=record.depth,
            values=record.values,
            mean=record.mean,
            low=record.low - 0.1,
            high=record.high + 0.1,
            n_scored=record.n_scored,
            n_excluded=record.n_excluded,
        )
