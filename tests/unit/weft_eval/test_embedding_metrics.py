"""Unit tests for `weft_eval.embedding_metrics`.

Mirrors `packages/weft-eval/src/weft_eval/embedding_metrics.py`. `EmbeddingSimilarity` is
exercised against `weft_embed.hash_embedder.HashEmbedder` — the real, deterministic, offline
`Embedder` every clean checkout already has, never a stub, so the `ctx.require(Embedder)` seam is
proven for real rather than assumed. `BERTScore`'s happy path cannot run in this gate (`bert-score`
is an optional extra, not installed here) — its edge case is exactly that: the derived
`BERT_SCORE_AVAILABLE` flag being `False` is asserted directly, and `evaluate` is asserted to
answer `Failed` naming the missing extra rather than raising or silently vanishing.
"""

import pytest

from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_eval.contract import GenerationSample
from weft_eval.embedding_metrics import (
    BERT_SCORE_AVAILABLE,
    BERTScore,
    EmbeddingSimilarity,
    NoConfig,
)
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, NothingToProduce, Produced


def _ctx() -> Context:
    services = ServiceRegistry()
    services.add(Embedder, HashEmbedder())
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


async def test_embedding_similarity_scores_identical_text_as_a_perfect_match() -> None:
    # Arrange — a content-hashed embedder gives identical content an identical vector, so cosine
    # similarity is exactly 1.0.
    metric = EmbeddingSimilarity(NoConfig())
    sample = GenerationSample(query="q", prediction="the sky is blue", reference="the sky is blue")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == pytest.approx(1.0)
    assert outcome.value.metric_name == "embedding_similarity"


async def test_embedding_similarity_empty_prediction_is_nothing_to_produce() -> None:
    # Arrange
    metric = EmbeddingSimilarity(NoConfig())
    sample = GenerationSample(query="q", prediction="   ", reference="sky blue")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_embedding_similarity_no_prediction_fails_rather_than_scoring_zero() -> None:
    # Arrange
    metric = EmbeddingSimilarity(NoConfig())
    sample = GenerationSample(query="q", prediction=None, reference="sky blue")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Failed)


def test_bert_score_availability_is_derived_not_hand_maintained() -> None:
    # Arrange / Act / Assert — the optional `bertscore` extra is not installed in this gate,
    # which is the whole point of it being optional (`pyproject.toml`'s own reasoning).
    assert BERT_SCORE_AVAILABLE is False


async def test_bert_score_answers_failed_naming_the_missing_extra_when_unavailable() -> None:
    # Arrange
    metric = BERTScore(NoConfig())
    sample = GenerationSample(query="q", prediction="a summary", reference="a summary")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "bertscore" in outcome.reason


async def test_bert_score_empty_reference_is_nothing_to_produce_even_when_unavailable() -> None:
    # Arrange — the empty-reference check runs before the availability check, so this stays
    # `NothingToProduce` regardless of whether the optional extra is installed.
    metric = BERTScore(NoConfig())
    sample = GenerationSample(query="q", prediction="anything", reference="")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)
