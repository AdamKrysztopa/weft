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

from weft_eval import Settings, register
from weft_eval.contract import RetrievalSample, RetrievedPassage
from weft_eval.harness import score_retrieval_gate_subset
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Failed, Produced
from weft_kernel.registry import Registry


def _registry() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


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
    assert "precision@2" in report
    outcome = report["precision@2"]
    assert isinstance(outcome, Produced)
    assert outcome.value.mean == 0.5
    assert outcome.value.n == 1
    assert outcome.value.stdev is None  # a single observation has no real spread to report
    # Gate-unsafe `RetrievalMetric`s never appear — they are judges, not this function's concern.
    assert "context-recall" not in report
    assert "context-relevance" not in report


async def test_score_retrieval_gate_subset_over_no_samples_reports_failed_not_silence() -> None:
    # Arrange / Act — no observations at all, for any metric.
    report = await score_retrieval_gate_subset(_registry(), [], top_k=5, ctx=_ctx())

    # Assert — every gate-safe RetrievalMetric still gets an entry, honestly `Failed`, never an
    # empty report a caller could mistake for "nothing gate-safe is registered."
    assert report
    for outcome in report.values():
        assert isinstance(outcome, Failed)
