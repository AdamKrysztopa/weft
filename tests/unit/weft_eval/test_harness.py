"""Unit tests for `weft_eval.harness`.

Mirrors `packages/weft-rag/src/weft_eval/harness.py`. Exercised against the real, registered
`weft-eval` suite (`weft_eval.register`), the same pattern `test_offline.py` already uses,
because the property under test is that this module derives the gate-safe `RetrievalMetric`
subset from the real registry rather than a fixed list of four names.

Covers: the happy path (a known `RetrievalSample` scores `precision-at-k`'s own reported name,
`precision@<k>`, to the hand-computed value), the edge case (an empty sample sequence still
produces one `Failed` entry per gate-safe metric, never a silent empty report), and that
gate-unsafe `RetrievalMetric`s (`context-recall`, `context-relevance`) never appear at all.
"""

from typing import ClassVar

import pytest
from pydantic import BaseModel

from weft_eval import Settings, register
from weft_eval.contract import MetricScore, RetrievalMetric, RetrievalSample, RetrievedPassage
from weft_eval.harness import (
    CollidingMetricNameError,
    score_retrieval_gate_subset,
)
from weft_eval.run_record import NotScored
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Failed, Outcome, Produced
from weft_kernel.registry import Registry


def _registry() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


class _ShadowPrecision:
    """A third party's metric that happens to report the name a built-in already reports."""

    config_model: ClassVar[type[BaseModel] | None] = None
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: object = None) -> None:
        del config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del payload, ctx
        return Produced(value=MetricScore(metric_name="precision@1", value=1.0))


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_score_retrieval_gate_subset_scores_a_known_sample_to_the_hand_computed_value() -> (
    None
):
    # Arrange — top 2 retrieved, one of them relevant: precision@2 = 1/2.
    sample = RetrievalSample(
        query="q",
        retrieved=(
            RetrievedPassage(id="doc-a", text="a"),
            RetrievedPassage(id="doc-b", text="b"),
        ),
        relevant_ids=frozenset({"doc-a"}),
    )

    # Act
    report = await score_retrieval_gate_subset(_registry(), [sample], top_k=2, ctx=_ctx())

    # Assert
    assert "precision@2" in report.metrics
    outcome = report.metrics["precision@2"]
    assert isinstance(outcome, Produced)
    assert outcome.value.mean == 0.5
    assert outcome.value.n == 1
    assert outcome.value.stdev is None  # a single observation has no real spread to report
    # Gate-unsafe `RetrievalMetric`s never appear — they are judges, not this function's concern.
    assert "context-recall" not in report.metrics
    assert "context-relevance" not in report.metrics


async def test_score_retrieval_gate_subset_over_no_samples_reports_failed_not_silence() -> None:
    # Arrange / Act — no observations at all, for any metric.
    report = await score_retrieval_gate_subset(_registry(), [], top_k=5, ctx=_ctx())

    # Assert — every gate-safe RetrievalMetric still gets an entry, honestly `Failed`, never an
    # empty report a caller could mistake for "nothing gate-safe is registered."
    assert report.metrics
    for outcome in report.metrics.values():
        assert isinstance(outcome, Failed)


# --- Task 16.4 — the per-question outcomes stop being discarded.


async def test_the_subset_returns_one_outcome_per_question_per_metric() -> None:
    """`aggregate()` folded the per-sample outcomes away and nothing else ever saw them, so a
    paired comparison between two runs needed both runs re-run. They are carried out now.

    Keyed by the sample's own `question_key`, never by position inside this function: the
    caller knows whether its questions have ids and this function must not invent an answer.
    """
    # Arrange — two questions, one scoring 1.0 and one 0.0 at precision@1.
    samples = [
        RetrievalSample(
            query="hit",
            question_key="q-hit",
            retrieved=(RetrievedPassage(id="doc-a", text="a"),),
            relevant_ids=frozenset({"doc-a"}),
        ),
        RetrievalSample(
            query="miss",
            question_key="q-miss",
            retrieved=(RetrievedPassage(id="doc-b", text="b"),),
            relevant_ids=frozenset({"doc-a"}),
        ),
    ]

    # Act
    report = await score_retrieval_gate_subset(_registry(), samples, top_k=1, ctx=_ctx())

    # Assert — the mean is the mean of two questions, and both questions are individually
    # readable, which is what makes the pair computable without re-running either run.
    aggregate_outcome = report.metrics["precision@1"]
    assert isinstance(aggregate_outcome, Produced)
    assert aggregate_outcome.value.mean == 0.5
    per_question = report.per_question["precision@1"]
    assert set(per_question) == {"q-hit", "q-miss"}
    hit = per_question["q-hit"]
    miss = per_question["q-miss"]
    assert isinstance(hit, Produced)
    assert isinstance(miss, Produced)
    assert (hit.value, miss.value) == (1.0, 0.0)


async def test_a_question_a_metric_could_not_score_is_a_failure_and_never_a_zero() -> None:
    """V4 (`docs/09-release.md`:620) at per-question granularity. A question with no relevant
    ids is `NothingToProduce` — `PrecisionAtK` says so itself — and a `0.0` in its place would
    be indistinguishable from a question the rung genuinely got wrong, which is the single most
    misleading number an evaluation can persist.
    """
    # Arrange — one scoreable question and one with no ground truth at all.
    samples = [
        RetrievalSample(
            query="hit",
            question_key="q-hit",
            retrieved=(RetrievedPassage(id="doc-a", text="a"),),
            relevant_ids=frozenset({"doc-a"}),
        ),
        RetrievalSample(
            query="unjudged",
            question_key="q-unjudged",
            retrieved=(RetrievedPassage(id="doc-b", text="b"),),
            relevant_ids=frozenset(),
        ),
    ]

    # Act
    report = await score_retrieval_gate_subset(_registry(), samples, top_k=1, ctx=_ctx())

    # Assert
    per_question = report.per_question["precision@1"]
    unjudged = per_question["q-unjudged"]
    assert isinstance(unjudged, NotScored)
    assert unjudged.reason, "a question that was not scored must say why"
    # And the aggregate excludes it rather than averaging it in as a zero.
    aggregate_outcome = report.metrics["precision@1"]
    assert isinstance(aggregate_outcome, Produced)
    assert aggregate_outcome.value.mean == 1.0
    assert aggregate_outcome.value.n == 1


async def test_every_metric_keys_its_questions_under_the_name_the_aggregate_reports() -> None:
    """One key space, so a reader pairing an aggregate with its questions never has to guess.

    `score_retrieval_gate_subset` keys its aggregates by `reported_name` — what the metric
    itself computed, `precision@1`, never the registered plugin name. The per-question mapping
    must use the identical key, or `record.metrics` and `record.question_scores` describe the
    same run under two vocabularies.
    """
    # Arrange
    samples = [
        RetrievalSample(
            query="q",
            question_key="q-1",
            retrieved=(RetrievedPassage(id="doc-a", text="a"),),
            relevant_ids=frozenset({"doc-a"}),
        )
    ]

    # Act
    report = await score_retrieval_gate_subset(_registry(), samples, top_k=1, ctx=_ctx())

    # Assert
    assert set(report.per_question) == set(report.metrics)


# --- Found at Phase 16a's close review: one key space, and nothing refused a collision.


async def test_two_metrics_reporting_one_name_are_refused_rather_than_overwriting() -> None:
    """`metrics` and `question_scores` are both keyed by `reported_name`, and the loop assigned
    into a dict — so a second metric computing a name the first already reported replaced it,
    silently, taking a whole question set with it since task 16.4.

    Invisible while the cardinality is 1: every metric this tree ships reports a distinct name.
    A third-party pack registering something that computes `precision@5` beside the built-in is
    all it takes, and the requirement is that an unknown or colliding name fails loudly naming
    what collided (`01` requirement 5).
    """
    # Arrange — two registered plugins, one reported name.
    registry = _registry()
    registry.add(RetrievalMetric, "shadow-precision", _ShadowPrecision, distribution="acme")
    sample = RetrievalSample(
        query="q",
        question_key="q-1",
        retrieved=(RetrievedPassage(id="doc-a", text="a"),),
        relevant_ids=frozenset({"doc-a"}),
    )

    # Act / Assert
    with pytest.raises(CollidingMetricNameError) as excinfo:
        await score_retrieval_gate_subset(registry, [sample], top_k=1, ctx=_ctx())
    message = str(excinfo.value)
    assert "precision@1" in message, "the refusal does not name the reported name that collided"
    assert "shadow-precision" in message, "the refusal does not name the plugin that collided"
