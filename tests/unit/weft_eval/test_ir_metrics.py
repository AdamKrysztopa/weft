"""Unit tests for `weft_eval.ir_metrics`.

Mirrors `packages/weft-rag/src/weft_eval/ir_metrics.py`. One happy path, one empty-relevance
edge case and one `k`-in-the-name check per metric, plus `MeanAveragePrecision`'s own multi-hit
happy path since averaging is where its formula differs from the other three.
"""

from weft_eval.contract import RetrievalSample, RetrievedPassage
from weft_eval.ir_metrics import (
    MeanAveragePrecision,
    MRRAtK,
    NDCGAtK,
    NoConfig,
    PrecisionAtK,
    RecallAtK,
    TopKConfig,
)
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Produced


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


# --- Task 16.7 — a metric named `@k` that cannot compute over `k` refuses.


def _n_retrieved(count: int, *, relevant: str = "doc-0") -> RetrievalSample:
    """`count` passages, `doc-0` first, and `relevant` as the one relevant id — the existing
    `_sample` above takes explicit ids, which these `@k` cases do not need.
    """
    return _sample(tuple(f"doc-{index}" for index in range(count)), frozenset({relevant}))


async def test_precision_at_k_refuses_when_fewer_than_k_candidates_came_back() -> None:
    """`12` §3: *"`recall@10` is computed over at most 8 candidates"* — every shipped rung ends
    in `repack: {top_n: 8}` and the named path does not oversample, so a metric named `@10`
    reported a number over 8. V4's clause is that the `k` in a metric's name equals the `k` it
    computed, and this enforces it with a refusal rather than a comment.

    A `Failed` rather than a `NothingToProduce`: there was something to score and the metric
    could not score *what its name claims*, which is an error about the run's configuration.
    `aggregate()` already excludes failures and counts them, so a run half of whose questions
    returned fewer than `k` reports the exclusion instead of a quietly depressed mean.
    """
    # Arrange
    metric = PrecisionAtK(TopKConfig(k=5))

    # Act
    outcome = await metric.evaluate(_n_retrieved(3), _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "5" in outcome.reason and "3" in outcome.reason, (
        f"the refusal names neither the k it claims nor the candidates it got: {outcome.reason}"
    )


async def test_precision_at_k_scores_when_exactly_k_candidates_came_back() -> None:
    # Arrange — the boundary, which is the case a `<` and a `<=` disagree about.
    metric = PrecisionAtK(TopKConfig(k=3))

    # Act
    outcome = await metric.evaluate(_n_retrieved(3), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1 / 3


async def test_recall_and_ndcg_refuse_on_the_same_condition() -> None:
    """All three `TopKConfig` metrics carry a `k` in the name they report, so all three owe the
    same refusal — one of them keeping the old behaviour would be the inconsistency a reader
    could not see.
    """
    # Arrange / Act / Assert
    for metric in (RecallAtK(TopKConfig(k=5)), NDCGAtK(TopKConfig(k=5))):
        outcome = await metric.evaluate(_n_retrieved(3), _ctx())
        assert isinstance(outcome, Failed), f"{type(metric).__name__} reported a number over 3"


async def test_mrr_at_k_is_one_over_the_rank_of_the_first_relevant_result() -> None:
    """Task 16.7's third defect: `mrr@k` existed only in the repo-level `eval/metrics.py`, which
    `eval/run_baseline.py` uses and no shipped pipeline can reach. A registered metric is what
    makes it available to `weft eval run`.
    """
    # Arrange — the relevant document is third of five.
    metric = MRRAtK(TopKConfig(k=5))
    sample = _n_retrieved(5, relevant="doc-2")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1 / 3
    assert outcome.value.metric_name == "mrr@5"


async def test_mrr_at_k_is_zero_when_nothing_relevant_came_back_within_k() -> None:
    """A zero here is a measurement — nothing relevant was retrieved — not a failure, and the
    two are kept apart the way `eval/metrics.py`'s own `reciprocal_rank_at_k` docstring already
    states for the identical arithmetic.
    """
    # Arrange
    metric = MRRAtK(TopKConfig(k=3))
    sample = _n_retrieved(3, relevant="doc-9")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 0.0


async def test_mrr_at_k_has_nothing_to_produce_without_ground_truth() -> None:
    # Arrange — the same edge every sibling metric already answers this way.
    metric = MRRAtK(TopKConfig(k=3))
    sample = RetrievalSample(
        query="q",
        retrieved=(RetrievedPassage(id="doc-0", text="t"),),
        relevant_ids=frozenset(),
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)
