"""Prerequisite **V3** and **V6** (`docs/09-release.md` §4.3) — the committed baseline, checked
as a fact.

V3 wants *"the numbers produced before any technique"*, repeated, with *"each metric carrying
the interval its own repetitions produced"*, and it fails when *"the baseline was run once, in
which case it records no interval and no later run can be judged against it."* Since task **4.8**,
V6 also applies: *"the baseline is one of Phase 4's persisted runs... The baseline exists only as
terminal output"* is its failure condition, so every committed baseline's `record` field must be
a real `weft_eval.run_record.RunRecord`. `eval/run_baseline.py` refuses to build a report that
breaks either rule; this file checks the **files that are actually committed**, because the
artefact is what Phase 4 inherits and Phase 6 republishes.

**No live run, no credential, no container.** The runs under `eval/baselines/` are read off
disk, so a contaminated interval is caught by the ordinary gate on a laptop rather than by
whoever next spends money on a measurement.

**The one thing this file guards that nothing else can.** A baseline says which corpus it was
measured over; whether that claim is true is a comparison against the manifest, and it is made
here by recomputing the corpus identity from `corpus/manifest.toml` — through the identical
`weft_eval.run_record.corpus_identity` convention `eval/run_baseline.py` itself calls — rather
than by trusting the digest the run wrote about itself. `.phase2-findings.md` §15 is why: a
figure over the operator tier reported as though it were reproducible would be the reference's
`gold_node_id_map` defect in a new costume — *"a benchmark whose headline figure cannot be
recomputed by the person reading it."*
"""

from pathlib import Path
from typing import Final

import pytest
from check_questions import load_questions, reproducible_questions
from fetch_corpus import Document, Tier, load_manifest
from metrics import MetricRecord
from run_baseline import BASELINES_DIR, EXTRACTOR_SUFFIXES, BaselineReport, load_run

from weft_eval.run_record import corpus_identity

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
MANIFEST: Final[Path] = REPO_ROOT / "corpus" / "manifest.toml"


@pytest.fixture(scope="module")
def runs() -> tuple[tuple[Path, BaselineReport], ...]:
    """Every committed baseline, refused at load if anything in it disagrees with itself."""
    return tuple((path, load_run(path)) for path in sorted(BASELINES_DIR.glob("*.json")))


@pytest.fixture(scope="module")
def documents() -> tuple[Document, ...]:
    """Every document the tracked manifest declares."""
    _, entries = load_manifest(MANIFEST)
    return tuple(entries)


def test_a_baseline_exists_and_one_of_them_may_be_published(
    runs: tuple[tuple[Path, BaselineReport], ...],
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


def test_every_baseline_carries_a_real_persisted_run_record(
    runs: tuple[tuple[Path, BaselineReport], ...],
) -> None:
    # V6's own floor: the baseline is one of Phase 4's persisted runs, not a hand-rolled shape
    # that merely looks like one. `RunRecord` is frozen and `extra="forbid"`, so a `record` that
    # loaded at all already satisfies its own field set; what is worth asserting here is that the
    # four fields V6 names are non-trivially populated by a real run rather than left at a type's
    # bare defaults.
    # Act / Assert
    for path, run in runs:
        assert run.record.resolved_pipeline.stages, (
            f"{path.name}: record.resolved_pipeline has no stages — this did not go through a "
            f"named pipeline (task 4.0), so it is not a run V6 recognises"
        )
        assert run.record.active_distributions, (
            f"{path.name}: record.active_distributions is empty — fitness function 8(c)'s own "
            f"subject was not recorded"
        )


def test_every_baseline_was_run_more_than_once_and_records_what_it_spanned(
    runs: tuple[tuple[Path, BaselineReport], ...],
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
    runs: tuple[tuple[Path, BaselineReport], ...],
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
    runs: tuple[tuple[Path, BaselineReport], ...], documents: tuple[Document, ...]
) -> None:
    # Recomputed rather than trusted. A run states its own `documents`/`tiers`/`extractor`, and a
    # run whose digest came from somewhere other than the documents it lists is exactly the claim
    # V3 cannot verify — "a baseline from a different corpus".
    # Arrange
    by_tier = {tier: [entry for entry in documents if entry.tier is tier] for tier in Tier}

    # Act / Assert
    for path, run in runs:
        suffixes = EXTRACTOR_SUFFIXES[run.extractor]
        declared = [
            entry
            for tier in run.tiers
            for entry in by_tier[Tier(tier)]
            if entry.path.suffix in suffixes
        ]
        assert run.documents == tuple(sorted(entry.id for entry in declared)), (
            f"{path.name}: names tiers {run.tiers} and extractor {run.extractor!r}, and lists "
            f"{len(run.documents)} documents; the manifest puts {len(declared)} there"
        )
        expected = corpus_identity(
            run.corpus_name, (f"{entry.id}\t{entry.sha256}" for entry in declared)
        )
        assert run.record.corpus == expected, (
            f"{path.name}: its record.corpus is not the digest of the documents it names. "
            f"Either the corpus moved under it or the digest was not computed from the manifest"
        )


def test_a_run_resting_on_the_operator_tier_says_it_cannot_be_reproduced(
    runs: tuple[tuple[Path, BaselineReport], ...],
) -> None:
    # `.phase2-findings.md` §15: two artefacts, never one. The label is derived from the tiers
    # here, exactly as `eval/run_baseline.py` derives it when it writes the file — so a run that
    # said `reproducible: true` over papers under publisher copyright is caught by the same rule
    # that should have set it, rather than by a reader noticing.
    # Act / Assert
    for path, run in runs:
        expected = all(Tier(tier).reproducible for tier in run.tiers)
        assert run.reproducible is expected, (
            f"{path.name}: says reproducible={run.reproducible} over tiers "
            f"{sorted(run.tiers)}. A number measured over documents a stranger cannot obtain "
            f"must be labelled unreproducible wherever it appears"
        )


def test_every_baseline_scored_the_questions_its_tiers_actually_allow(
    runs: tuple[tuple[Path, BaselineReport], ...], documents: tuple[Document, ...]
) -> None:
    # The subset is derived from the manifest's tiers and *the documents this run actually
    # indexed* — task 2.2's tier rule, narrowed further by `run_baseline._run`'s own
    # `indexed_ids` filter (task 4.8): a run over one extractor's documents must not be scored
    # against a question resting on a document a different extractor would have staged. A run
    # that measured *fewer* questions than this allows reports a number over a set nobody can
    # reconstruct; one that measured more rests on documents it did not index.
    # Arrange
    tiers = {entry.id: entry.tier.value for entry in documents}
    questions = load_questions()

    # Act / Assert
    for path, run in runs:
        indexed = frozenset(run.documents)
        allowed = tuple(
            question
            for question in reproducible_questions(
                questions, tiers=tiers, reproducible=frozenset(run.tiers)
            )
            if set(question.relevant_documents) <= indexed
        )
        assert run.questions == tuple(sorted(question.id for question in allowed)), (
            f"{path.name}: scored {len(run.questions)} questions where its tiers "
            f"{sorted(run.tiers)} and its own {len(run.documents)} indexed document(s) allow "
            f"{len(allowed)}"
        )


def test_no_aggregate_averaged_a_measurement_that_did_not_happen(
    runs: tuple[tuple[Path, BaselineReport], ...],
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
    runs: tuple[tuple[Path, BaselineReport], ...],
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
