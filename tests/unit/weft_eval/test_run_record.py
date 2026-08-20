"""Unit tests for `weft_eval.run_record`.

Mirrors `packages/weft-eval/src/weft_eval/run_record.py`. Covers `build_run_record`'s own
derivation of `active_distributions` (happy path: only `PackStatus.ACTIVE` reports contribute;
the edge case of no reports at all), `write_run_record`/`load_run_record`'s round trip,
`load_run_record`'s refusal of a file that is not a well-formed `RunRecord` (the error case), and
`corpus_identity`'s content-derived, order-independent digest. Fitness function 8(c)'s own
equality-with-`plugins doctor` proof lives in `tests/architecture/test_ff8_trust_model.py`, not
here — this file is the mirroring unit-test path for the module itself.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from weft_eval.aggregate import MetricAggregate
from weft_eval.run_record import (
    CorpusIdentity,
    NotAggregated,
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
        PackReport(distribution="weft-extract", status=PackStatus.ACTIVE, contributed=2),
        PackReport(distribution="weft-canary", status=PackStatus.REFUSED, reason="not allowed"),
        PackReport(distribution="weft-half", status=PackStatus.PARTIAL, contributed=1),
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
        reports=(PackReport(distribution="weft-extract", status=PackStatus.ACTIVE, contributed=2),),
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


def test_corpus_identity_digest_is_order_independent_and_content_derived() -> None:
    # Arrange / Act
    forward = corpus_identity("demo", ["doc-a", "doc-b"])
    reversed_order = corpus_identity("demo", ["doc-b", "doc-a"])
    different = corpus_identity("demo", ["doc-a", "doc-c"])

    # Assert — layout never moves the digest, content always does.
    assert forward.digest == reversed_order.digest
    assert forward.digest != different.digest
