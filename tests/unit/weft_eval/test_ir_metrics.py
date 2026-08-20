"""Unit tests for `weft_eval.ir_metrics`.

Mirrors `packages/weft-eval/src/weft_eval/ir_metrics.py`. One happy path, one empty-relevance
edge case and one `k`-in-the-name check per metric, plus `MeanAveragePrecision`'s own multi-hit
happy path since averaging is where its formula differs from the other three.
"""

from weft_eval.contract import RetrievalSample, RetrievedPassage
from weft_eval.ir_metrics import (
    MeanAveragePrecision,
    NDCGAtK,
    NoConfig,
    PrecisionAtK,
    RecallAtK,
    TopKConfig,
)
from weft_kernel.context import Context
from weft_kernel.payload import NothingToProduce, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _sample(ids: tuple[str, ...], relevant: frozenset[str]) -> RetrievalSample:
    return RetrievalSample(
        query="q",
        retrieved=tuple(RetrievedPassage(id=doc_id) for doc_id in ids),
        relevant_ids=relevant,
    )


async def test_precision_at_k_counts_relevant_hits_among_the_top_k() -> None:
    # Arrange — 2 of the top 3 are relevant.
    metric = PrecisionAtK(TopKConfig(k=3))
    sample = _sample(("a", "b", "c", "d"), frozenset({"a", "c", "z"}))

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 2 / 3
    assert outcome.value.metric_name == "precision@3"


async def test_recall_at_k_with_no_relevant_ids_is_nothing_to_produce() -> None:
    # Arrange
    metric = RecallAtK(TopKConfig(k=2))
    sample = _sample(("a", "b"), frozenset())

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_recall_at_k_finds_every_relevant_id_within_the_window() -> None:
    # Arrange — both relevant ids sit inside the top 3.
    metric = RecallAtK(TopKConfig(k=3))
    sample = _sample(("a", "b", "c", "d"), frozenset({"b", "d"}))

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert — "d" is outside the top 3, so only 1 of 2 relevant ids is found.
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 0.5
    assert outcome.value.metric_name == "recall@3"


async def test_mean_average_precision_averages_precision_at_every_relevant_rank() -> None:
    # Arrange — relevant at rank 1 and rank 3: AP = (1/1 + 2/3) / 2.
    metric = MeanAveragePrecision(NoConfig())
    sample = _sample(("a", "b", "c"), frozenset({"a", "c"}))

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == (1.0 + 2 / 3) / 2
    assert outcome.value.metric_name == "mean_average_precision"


async def test_ndcg_at_k_scores_one_when_every_relevant_id_leads() -> None:
    # Arrange — every relevant id in the top `k` and in the ideal order: NDCG = 1.0.
    metric = NDCGAtK(TopKConfig(k=2))
    sample = _sample(("a", "b", "c"), frozenset({"a", "b"}))

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1.0
    assert outcome.value.metric_name == "ndcg@2"


async def test_ndcg_at_k_with_no_relevant_ids_is_nothing_to_produce() -> None:
    # Arrange
    metric = NDCGAtK(TopKConfig(k=2))
    sample = _sample(("a", "b"), frozenset())

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)
