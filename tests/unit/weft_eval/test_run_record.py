"""Unit tests for `weft_eval.run_record`.

Mirrors `packages/weft-rag/src/weft_eval/run_record.py`. Covers `build_run_record`'s own
derivation of `active_distributions` (happy path: only `PackStatus.ACTIVE` reports contribute;
the edge case of no reports at all), `write_run_record`/`load_run_record`'s round trip,
`load_run_record`'s refusal of a file that is not a well-formed `RunRecord` (the error case), and
`corpus_identity`'s order-independent digest over whatever entries its caller passes. Fitness
function 8(c)'s own equality-with-`plugins doctor` proof lives in
`tests/architecture/test_ff8_trust_model.py`, not here — this file is the mirroring unit-test
path for the module itself.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from weft_eval.aggregate import MetricAggregate
from weft_eval.run_record import (
    CorpusDigestBasis,
    CorpusIdentity,
    NoQueryRung,
    NotAggregated,
    NotScored,
    PerQuestionScores,
    QueryRung,
    QuestionKey,
    RunDurations,
    build_run_record,
    corpus_identity,
    load_run_record,
    write_run_record,
)
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Failed, NothingToProduce, Produced
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage


def _resolved_pipeline() -> ResolvedPipeline:
    return ResolvedPipeline(
        name="index",
        stages=(
            ResolvedStage(
                id="extract",
                contract="Extractor",
                use="pdf-text",
                distribution="weft-extract",
                provenance="index",
            ),
        ),
    )


def _corpus() -> CorpusIdentity:
    return corpus_identity("demo-corpus", ["doc-1", "doc-2"])


def test_build_run_record_active_distributions_is_only_the_active_ones() -> None:
    # Arrange — a mix of statuses, the identical vocabulary `plugins doctor` reads off.
    reports = (
        PackReport(
            pack="extract", distribution="weft-extract", status=PackStatus.ACTIVE, contributed=2
        ),
        PackReport(
            pack="canary",
            distribution="weft-canary",
            status=PackStatus.REFUSED,
            reason="not allowed",
        ),
        PackReport(pack="half", distribution="weft-half", status=PackStatus.PARTIAL, contributed=1),
    )

    # Act
    record = build_run_record(
        recorded_at="2026-08-20T00:00:00+00:00",
        resolved_pipeline=_resolved_pipeline(),
        corpus=_corpus(),
        model_versions={"embed": "openai:text-embedding-3-small"},
        reports=reports,
    )

    # Assert — refused and partial packs never contribute to the active set, only ACTIVE does.
    assert record.active_distributions == ("weft-extract",)
    assert record.model_versions == {"embed": "openai:text-embedding-3-small"}
    assert record.resolved_pipeline == _resolved_pipeline()


def test_build_run_record_with_no_reports_has_no_active_distributions() -> None:
    # Arrange / Act — a run built with nothing to say about what was installed.
    record = build_run_record(
        recorded_at="2026-08-20T00:00:00+00:00",
        resolved_pipeline=_resolved_pipeline(),
        corpus=_corpus(),
    )

    # Assert — empty, never a placeholder or an omitted field.
    assert record.active_distributions == ()
    assert record.model_versions == {}


def test_write_then_load_round_trips_exactly(tmp_path: Path) -> None:
    # Arrange
    record = build_run_record(
        recorded_at="2026-08-20T00:00:00+00:00",
        resolved_pipeline=_resolved_pipeline(),
        corpus=_corpus(),
        model_versions={"embed": "hash:hash"},
        reports=(
            PackReport(
                pack="extract", distribution="weft-extract", status=PackStatus.ACTIVE, contributed=2
            ),
        ),
    )
    path = tmp_path / "runs" / "one.json"

    # Act
    written = write_run_record(record, path)
    loaded = load_run_record(written)

    # Assert — the file two later runs can be diffed against is exactly what was built.
    assert written == path
    assert path.exists()
    assert loaded == record


def test_load_run_record_refuses_a_file_missing_a_required_field(tmp_path: Path) -> None:
    # Arrange — a file missing `corpus` entirely, the shape a hand-edited or truncated write
    # would produce.
    path = tmp_path / "malformed.json"
    path.write_text(
        '{"recorded_at": "2026-08-20T00:00:00+00:00", '
        '"resolved_pipeline": {"name": "index", "stages": []}}',
        encoding="utf-8",
    )

    # Act / Assert
    with pytest.raises(ValidationError):
        load_run_record(path)


def test_build_run_record_folds_produced_and_failed_metrics_task_4_9() -> None:
    # Arrange — task 4.9: `metrics` takes `aggregate()`'s own three-state `Outcome` and
    # narrows it to `RunRecord`'s two-state `MetricRunResult`.
    produced = Produced(
        value=MetricAggregate(
            reported_name="precision@5",
            mean=0.6,
            n=3,
            stdev=0.1,
            excluded=0,
            nothing_to_produce=0,
        )
    )
    failed = Failed(reason="all 2 observation(s) excluded (2 failed, 0 had nothing to score)")
    nothing = NothingToProduce(reason="all 1 observation(s) had nothing to score")

    # Act
    record = build_run_record(
        recorded_at="2026-08-20T00:00:00+00:00",
        resolved_pipeline=_resolved_pipeline(),
        corpus=_corpus(),
        metrics={"precision@5": produced, "recall@5": failed, "ndcg@5": nothing},
    )

    # Assert — `Produced` passes through unchanged; `Failed`/`NothingToProduce` both collapse
    # to `NotAggregated`, carrying their own reason text rather than losing it.
    assert record.metrics["precision@5"] == produced
    assert record.metrics["recall@5"] == NotAggregated(reason=failed.reason)
    assert record.metrics["ndcg@5"] == NotAggregated(reason=nothing.reason)


def test_build_run_record_with_no_metrics_has_an_empty_metrics_mapping() -> None:
    # Arrange / Act — the honest answer for a run `weft eval run` gave no `--questions`.
    record = build_run_record(
        recorded_at="2026-08-20T00:00:00+00:00",
        resolved_pipeline=_resolved_pipeline(),
        corpus=_corpus(),
    )

    # Assert
    assert record.metrics == {}


def test_corpus_identity_digest_is_order_independent_and_moves_with_its_entries() -> None:
    # Arrange / Act
    forward = corpus_identity("demo", ["doc-a", "doc-b"])
    reversed_order = corpus_identity("demo", ["doc-b", "doc-a"])
    different = corpus_identity("demo", ["doc-a", "doc-c"])

    # Assert — order never moves the digest, a changed entry always does. What those entries
    # *are* is the caller's choice and not this function's property: task 16.0 is the caller
    # choosing bytes over paths, and it needed no change here.
    assert forward.digest == reversed_order.digest
    assert forward.digest != different.digest


# --- Ledger task 10.22 — a run states how long it took, so a cost question has an answer.


def test_a_record_built_without_timing_states_no_duration_rather_than_zero() -> None:
    """`0.0` is a number a run could genuinely have produced; absence is not.

    This is task 10.20's rule one module over, and it matters more here: a duration is the field a
    cost comparison reads, so a zero that means *"nobody measured"* is indistinguishable from a
    zero that means *"this was instant"*, and the reader cannot tell an unmeasured run from a fast
    one. `None` says which.
    """
    # Arrange & Act
    record = build_run_record(
        recorded_at="2026-09-08T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
    )

    # Assert
    assert record.durations is None, (
        "a record built without timing must state no duration at all. A zero here is a claim the "
        "run took no time, which is a thing a run could genuinely do."
    )


def test_a_record_carries_ingest_and_query_apart_and_round_trips(tmp_path: Path) -> None:
    """The two halves are separate because the question they answer is a comparison.

    G15's *Remove* face turns on whether avoiding a rebuild is worth a change to a published
    contract family, and a rebuild is **ingest**. A single total would fold the cost of scoring
    the run — which `adrap` changes not at all — into the number that decides it.
    """
    # Arrange
    record = build_run_record(
        recorded_at="2026-09-08T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
        durations=RunDurations(ingest_seconds=12.5, query_seconds=0.25),
    )

    # Act
    written = write_run_record(record, tmp_path / "r.json")

    # Assert
    assert record.durations is not None
    assert record.durations.ingest_seconds == 12.5
    assert record.durations.query_seconds == 0.25
    assert load_run_record(written) == record, "durations must survive the round trip"


def test_a_negative_duration_is_refused() -> None:
    """A monotonic clock cannot run backwards, so a negative value is a bug in the caller.

    Refused at construction rather than stored and puzzled over later — the same posture every
    other numeric field on this record's neighbours takes.
    """
    # Arrange & Act & Assert
    with pytest.raises(ValidationError):
        RunDurations(ingest_seconds=-1.0, query_seconds=0.0)


# --- Task 16.0 — a record says what its corpus digest is over, or says it does not know.


def test_a_record_built_without_a_basis_does_not_claim_one() -> None:
    """*Not recorded* is what every record written before task 16.0 carries, and it is a fact.

    Until 16.0 the digest was over sorted document **paths** — `weft_extract.text.
    discover_source_docs` mints a `SourceId` as `str(path.resolve())` and the callers digested
    exactly those — so a digest from before and a digest from after answer two different
    questions and are not comparable at all. The records already committed cannot be
    retro-labelled: they were written by the code that made the mistake. So the only honest
    value for one is absence, and `weft_cli.eval_commands._incomparable_reasons` is what turns
    that absence into a sentence an operator reads.
    """
    # Arrange / Act
    record = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
    )

    # Assert
    assert record.corpus_digest_basis is None, (
        "a record built without a stated basis must not claim one. Defaulting to "
        "DOCUMENT_BYTES would label every pre-16.0 record with the property it lacks."
    )


def test_a_record_naming_its_basis_survives_the_round_trip(tmp_path: Path) -> None:
    # Arrange
    record = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
        corpus_digest_basis=CorpusDigestBasis.DOCUMENT_BYTES,
    )

    # Act
    written = write_run_record(record, tmp_path / "r.json")

    # Assert
    assert load_run_record(written) == record
    assert load_run_record(written).corpus_digest_basis is CorpusDigestBasis.DOCUMENT_BYTES


def test_a_record_from_a_file_with_no_basis_key_loads_and_reads_absent(tmp_path: Path) -> None:
    """The shape of all 31 records committed under `eval/` — the key is not there at all.

    `RunRecord` has `extra="forbid"` and validates on read, so a **required** field here would
    stop every one of them loading and take `tests/docs/test_raptor_baseline.py` with it. Task
    10.22's `durations` set the precedent this follows: a new field defaults to `None`.
    """
    # Arrange — a file written by the code that had no such field, reproduced by removing the
    # key rather than by hand-writing JSON that could drift from the model.
    record = build_run_record(
        recorded_at="2026-09-07T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
        corpus_digest_basis=CorpusDigestBasis.DOCUMENT_BYTES,
    )
    payload = record.model_dump(mode="json")
    del payload["corpus_digest_basis"]
    path = tmp_path / "older.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    # Act
    loaded = load_run_record(path)

    # Assert
    assert loaded.corpus_digest_basis is None
    assert loaded.corpus == record.corpus


# --- Task 16.1 — a record names the query rung it scored, or says which fact it lacks.


def test_a_record_built_without_a_query_rung_does_not_claim_one() -> None:
    """Three states, because two would conflate two different facts.

    `None` is *not recorded* — every record written before task 16.1, which persisted no query
    pipeline at all. `NoQueryRung` is *this run named none*, which is a measurement: retrieval
    ran against the ingest pipeline's own stages. A single nullable field would make a 2026-09-07
    record and a deliberate plain-vector run indistinguishable, and the second is exactly what a
    baseline is.
    """
    # Arrange / Act
    record = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
    )

    # Assert
    assert record.query_rung is None


def test_the_two_query_rung_states_are_distinguishable_after_a_round_trip(tmp_path: Path) -> None:
    # Arrange — one record per state, written and read back through the persisted form.
    named = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
        query_rung=QueryRung(name="hybrid-then-generate", identity="ab" * 32),
    )
    none_named = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
        query_rung=NoQueryRung(reason="no query rung was named"),
    )

    # Act
    read_named = load_run_record(write_run_record(named, tmp_path / "a.json"))
    read_none = load_run_record(write_run_record(none_named, tmp_path / "b.json"))

    # Assert — the union resolves to the member it was written as, which is what the two
    # members not sharing a field name buys (`MetricRunResult`'s own reason to be a union).
    assert isinstance(read_named.query_rung, QueryRung)
    assert read_named.query_rung.name == "hybrid-then-generate"
    assert isinstance(read_none.query_rung, NoQueryRung)
    assert read_named == named
    assert read_none == none_named


# --- Task 16.3 — a record names the version of every active distribution.


def test_a_record_built_without_distribution_versions_does_not_claim_any() -> None:
    """`None` and `{}` are different answers and both are reachable.

    `None` is *not recorded* — every record written before this task, which named distributions
    and never their versions. `{}` is *measured, and nothing had recorded metadata*, which is a
    real state: `installed_versions` omits a name whose `.dist-info` is missing, so an
    environment of editable installs can legitimately produce an empty mapping. A single falsy
    field would say the same thing about both.
    """
    # Arrange / Act
    record = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
    )

    # Assert
    assert record.distribution_versions is None


def test_a_record_carries_distribution_versions_through_a_round_trip(tmp_path: Path) -> None:
    # Arrange
    record = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
        distribution_versions={"weft-rag": "2.5.0", "weft-kernel": "0.1.0"},
    )

    # Act
    loaded = load_run_record(write_run_record(record, tmp_path / "r.json"))

    # Assert
    assert loaded.distribution_versions == {"weft-rag": "2.5.0", "weft-kernel": "0.1.0"}
    assert loaded == record


def test_a_record_that_measured_versions_and_found_none_is_not_a_record_that_did_not_look(
    tmp_path: Path,
) -> None:
    # Arrange
    measured = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
        distribution_versions={},
    )

    # Act
    loaded = load_run_record(write_run_record(measured, tmp_path / "r.json"))

    # Assert
    assert loaded.distribution_versions == {}
    assert loaded.distribution_versions is not None, (
        "an empty measurement survived the round trip as an absence, so a record that looked "
        "and found nothing reads as one that never looked — `L5.9` one field over"
    )


# --- Task 16.4 — one score per question per metric, so a pair is computable after the fact.


def test_a_record_built_without_question_scores_does_not_claim_any() -> None:
    # Arrange / Act
    record = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
    )

    # Assert
    assert record.question_scores is None


def test_a_failed_question_persists_as_a_failure_and_survives_the_round_trip(
    tmp_path: Path,
) -> None:
    """V4, `docs/09-release.md`:620, at the granularity this task adds: the union's two members
    share no field name, so `Produced[float]` and `NotScored` never round-trip into each other
    — `MetricRunResult`'s own reason to be a union, one level down.
    """
    # Arrange
    record = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
        question_scores={
            "precision@5": PerQuestionScores(
                keyed_by=QuestionKey.QUESTION_ID,
                scores={
                    "fetch-001": Produced(value=0.8),
                    "fetch-002": NotScored(reason="no relevant ids to score retrieval against"),
                },
            )
        },
    )

    # Act
    loaded = load_run_record(write_run_record(record, tmp_path / "r.json"))

    # Assert
    assert loaded == record
    scores = loaded.question_scores
    assert scores is not None
    entries = scores["precision@5"].scores
    assert isinstance(entries["fetch-001"], Produced)
    assert entries["fetch-001"].value == 0.8
    assert isinstance(entries["fetch-002"], NotScored), (
        "an unscoreable question came back as a score, which is the zero V4 forbids"
    )


def test_a_record_says_whether_its_question_keys_are_ids_or_positions() -> None:
    """A key of `"0"` and a key of `"fetch-001"` are read differently by anyone pairing two
    runs, and a questions file with no ids is the normal case for `--questions`. Saying which
    is what stops a reader treating a position as a stable identity across two files.
    """
    # Arrange / Act
    positional = PerQuestionScores(keyed_by=QuestionKey.POSITION, scores={"0": Produced(value=1.0)})

    # Assert
    assert positional.keyed_by is QuestionKey.POSITION
    assert set(positional.scores) == {"0"}


# --- Task 16.6 — a record names the question set it was scored with.


def test_a_record_built_without_a_question_set_digest_does_not_claim_one() -> None:
    # Arrange / Act
    record = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
    )

    # Assert
    assert record.question_set_digest is None


def test_a_question_set_digest_survives_the_round_trip(tmp_path: Path) -> None:
    # Arrange
    record = build_run_record(
        recorded_at="2026-09-12T00:00:00Z",
        resolved_pipeline=_resolved_pipeline(),
        corpus=CorpusIdentity(name="c", digest="d"),
        question_set_digest="f" * 64,
    )

    # Act
    loaded = load_run_record(write_run_record(record, tmp_path / "r.json"))

    # Assert
    assert loaded.question_set_digest == "f" * 64
    assert loaded == record
