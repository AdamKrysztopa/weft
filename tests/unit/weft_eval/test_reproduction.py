"""`weft_eval.baseline.judge_reproduction` — ledger repair **R22.4b**.

`09` §4.3's V3 decides reproduction by the published intervals and nothing else, and refuses a
comparison against *"a baseline from a different corpus, pipeline or model version"*. What counts
as the same *pipeline* was answered by `ResolvedPipeline ==`, which includes the distribution that
registered each plugin and the contract version it declared — so after G19 renamed every
distribution, a re-run reproducing all twelve published metrics exactly was refused as a different
pipeline (`L22.11`). The fixture is that re-run: `v2.6.0`'s published baseline re-taken on
2026-09-14 against a fresh Qdrant, with the tree at `b5e34c9`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_eval.baseline import (
    BaselineReport,
    IncomparableBaselinesError,
    MetricRecord,
    ProvenanceField,
    judge_reproduction,
    load_baseline_report,
)
from weft_eval.run_record import CorpusIdentity

_PUBLISHED = (
    Path(__file__).resolve().parents[3] / "eval" / "baselines" / "8854c33f71ea-2026-08-25.json"
)
_RERUN = Path(__file__).resolve().parent / "fixtures" / "baseline-rerun-2026-09-14.json"


def _with_stage(report: BaselineReport, stage_id: str, **changes: object) -> BaselineReport:
    pipeline = report.record.resolved_pipeline
    stages = tuple(
        stage.model_copy(update=changes) if stage.id == stage_id else stage
        for stage in pipeline.stages
    )
    record = report.record.model_copy(
        update={"resolved_pipeline": pipeline.model_copy(update={"stages": stages})}
    )
    return report.model_copy(update={"record": record})


def _with_metric(report: BaselineReport, name: str, values: tuple[float, ...]) -> BaselineReport:
    metrics = tuple(
        record
        if record.metric != name
        else MetricRecord(
            metric=name,
            depth=record.depth,
            values=values,
            mean=sum(values) / len(values),
            low=min(values),
            high=max(values),
            n_scored=record.n_scored,
            n_excluded=record.n_excluded,
        )
        for record in report.metrics
    )
    return report.model_copy(update={"metrics": metrics})


def _without_metric(report: BaselineReport, name: str) -> BaselineReport:
    kept = tuple(record for record in report.metrics if record.metric != name)
    return report.model_copy(update={"metrics": kept})


@pytest.fixture(scope="module")
def published() -> BaselineReport:
    return load_baseline_report(_PUBLISHED)


@pytest.fixture(scope="module")
def rerun() -> BaselineReport:
    return load_baseline_report(_RERUN)


def test_a_rerun_on_a_renamed_installation_reproduces_and_says_what_moved(
    published: BaselineReport, rerun: BaselineReport
) -> None:
    # Act
    reproduction = judge_reproduction(published, rerun)

    # Assert
    assert published.record.resolved_pipeline != rerun.record.resolved_pipeline
    assert reproduction.reproduced
    assert {verdict.metric for verdict in reproduction.verdicts} == {
        record.metric for record in published.metrics
    }
    assert all(verdict.inside for verdict in reproduction.verdicts)
    assert {(difference.stage, difference.field) for difference in reproduction.provenance} == {
        ("extract", ProvenanceField.DISTRIBUTION),
        ("chunk", ProvenanceField.DISTRIBUTION),
        ("embed", ProvenanceField.DISTRIBUTION),
        ("store", ProvenanceField.DISTRIBUTION),
        ("store", ProvenanceField.CONTRACT_VERSION),
        ("chunk", ProvenanceField.APPLIES_TO),
    }


def test_a_provenance_difference_carries_both_values(
    published: BaselineReport, rerun: BaselineReport
) -> None:
    # Act
    reproduction = judge_reproduction(published, rerun)

    # Assert
    store = {
        difference.field: (difference.published, difference.later)
        for difference in reproduction.provenance
        if difference.stage == "store"
    }
    assert store[ProvenanceField.DISTRIBUTION] == ("weft-qdrant", "weft-rag")
    assert store[ProvenanceField.CONTRACT_VERSION] == ("2.0.0", "2.6.0")
    assert reproduction.published_distributions == tuple(published.record.active_distributions)
    assert reproduction.later_distributions == tuple(rerun.record.active_distributions)


@pytest.mark.parametrize(
    ("stage_id", "field", "value"),
    [
        ("extract", "use", "pdf-text"),
        ("chunk", "config", {"size": 256, "overlap": 50}),
        ("chunk", "contract", "Enhancer"),
        ("embed", "fallback", ("ocr",)),
        ("store", "provenance", "derived-baseline"),
    ],
)
def test_a_stage_the_document_states_differently_is_refused(
    published: BaselineReport, stage_id: str, field: str, value: object
) -> None:
    # Arrange
    later = _with_stage(published, stage_id, **{field: value})

    # Act
    with pytest.raises(IncomparableBaselinesError) as caught:
        judge_reproduction(published, later)

    # Assert
    before = next(s for s in published.record.resolved_pipeline.stages if s.id == stage_id)
    assert getattr(before, field) != value
    assert f"'{stage_id}'" in str(caught.value)
    assert field in str(caught.value)


def test_a_stage_the_later_run_does_not_have_is_refused(published: BaselineReport) -> None:
    # Arrange
    pipeline = published.record.resolved_pipeline
    kept = tuple(stage for stage in pipeline.stages if stage.id != "embed")
    record = published.record.model_copy(
        update={"resolved_pipeline": pipeline.model_copy(update={"stages": kept})}
    )
    later = published.model_copy(update={"record": record})

    # Act
    with pytest.raises(IncomparableBaselinesError) as caught:
        judge_reproduction(published, later)

    # Assert
    assert "'embed'" in str(caught.value)


@pytest.mark.parametrize(
    ("field", "update"),
    [
        ("retrieval_depth", {"retrieval_depth": 5}),
        ("questions", {"questions": ("polish-001",)}),
    ],
)
def test_a_different_depth_or_question_set_is_refused(
    published: BaselineReport, field: str, update: dict[str, object]
) -> None:
    # Arrange
    later = published.model_copy(update=update)

    # Act
    with pytest.raises(IncomparableBaselinesError) as caught:
        judge_reproduction(published, later)

    # Assert
    assert getattr(later, field) != getattr(published, field)
    assert field in str(caught.value)


@pytest.mark.parametrize(
    ("field", "update"),
    [
        ("corpus", {"corpus": CorpusIdentity(name="mrmr-v1", digest="0" * 64)}),
        ("model_versions", {"model_versions": {"embed": "hash:v2"}}),
    ],
)
def test_a_different_corpus_or_model_is_refused(
    published: BaselineReport, field: str, update: dict[str, object]
) -> None:
    # Arrange
    record = published.record.model_copy(update=update)
    later = published.model_copy(update={"record": record})

    # Act
    with pytest.raises(IncomparableBaselinesError) as caught:
        judge_reproduction(published, later)

    # Assert
    assert field in str(caught.value)


def test_a_metric_outside_its_interval_does_not_reproduce(
    published: BaselineReport, rerun: BaselineReport
) -> None:
    # Arrange
    later = _with_metric(rerun, "document-recall@10", (0.5, 0.5, 0.5))

    # Act
    reproduction = judge_reproduction(published, later)

    # Assert
    outside = [verdict for verdict in reproduction.verdicts if not verdict.inside]
    assert not reproduction.reproduced
    assert [(verdict.metric, verdict.later) for verdict in outside] == [("document-recall@10", 0.5)]


def test_a_metric_the_later_run_did_not_measure_does_not_reproduce(
    published: BaselineReport, rerun: BaselineReport
) -> None:
    # Arrange
    later = _without_metric(rerun, "quote-mrr@5")

    # Act
    reproduction = judge_reproduction(published, later)

    # Assert
    missing = [verdict for verdict in reproduction.verdicts if verdict.later is None]
    assert not reproduction.reproduced
    assert [(verdict.metric, verdict.inside) for verdict in missing] == [("quote-mrr@5", False)]
