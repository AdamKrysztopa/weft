"""Unit tests for `weft_eval.embedding_metrics`.

Mirrors `packages/weft-rag/src/weft_eval/embedding_metrics.py`. `EmbeddingSimilarity` is
exercised against `weft_embed.hash_embedder.HashEmbedder` — the real, deterministic, offline
`Embedder` every clean checkout already has, never a stub, so the `ctx.require(Embedder)` seam is
proven for real rather than assumed. `BERTScore`'s happy path cannot run in this gate (`bert-score`
is an optional extra, not installed here) — its edge case is exactly that: the derived
`BERT_SCORE_AVAILABLE` flag being `False` is asserted directly, and `evaluate` is asserted to
answer `Failed` naming the missing extra rather than raising or silently vanishing.
"""

import sys
import types

import pytest

from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_eval import embedding_metrics
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


# --- Task 16.8 — Polish is scored as Polish.


async def test_bert_score_asks_for_the_language_the_sample_declares(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`12` §3's language axis: `bert_score(lang="en")` was a constant, so a Polish answer was
    scored against an English model and the number meant nothing. It is not configurable by any
    amount of `weft.toml`, which is what makes it a defect rather than a default.

    The library is an optional extra and is not installed in the gate, so the call is watched
    through a stand-in module injected into `sys.modules` — the wire is what is under test
    (`L9.79`), not the library's arithmetic.
    """
    # Arrange
    asked: dict[str, object] = {}

    class _Result:
        def mean(self) -> float:
            return 0.5

    def _score(
        predictions: list[str], references: list[str], *, lang: str, verbose: bool
    ) -> tuple[object, object, _Result]:
        del predictions, references, verbose
        asked["lang"] = lang
        return object(), object(), _Result()

    module = types.ModuleType("bert_score")
    module.score = _score  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bert_score", module)
    monkeypatch.setattr(embedding_metrics, "BERT_SCORE_AVAILABLE", True)

    # Act
    outcome = await BERTScore(NoConfig()).evaluate(
        GenerationSample(
            query="jakie są trzy kroki?",
            prediction="trzy kroki",
            reference="trzy kroki",
            language="pl",
        ),
        _ctx(),
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert asked["lang"] == "pl", (
        "the metric asked for a language other than the one the sample declares, so a Polish "
        "answer is scored against a model for another language"
    )


async def test_a_sample_that_declares_no_language_is_scored_as_english(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default is `en` and it is on the model where a reader can see it, rather than inside
    the metric where nothing could change it. Every sample built before this task is English by
    construction, so this is the compatible reading — and it is still a *default*, which is why
    `eval/questions/*.toml` states the language on every question explicitly.
    """
    # Arrange
    asked: dict[str, object] = {}

    class _Result:
        def mean(self) -> float:
            return 0.5

    def _score(
        predictions: list[str], references: list[str], *, lang: str, verbose: bool
    ) -> tuple[object, object, _Result]:
        del predictions, references, verbose
        asked["lang"] = lang
        return object(), object(), _Result()

    module = types.ModuleType("bert_score")
    module.score = _score  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bert_score", module)
    monkeypatch.setattr(embedding_metrics, "BERT_SCORE_AVAILABLE", True)

    # Act
    await BERTScore(NoConfig()).evaluate(
        GenerationSample(query="q", prediction="a", reference="a"), _ctx()
    )

    # Assert
    assert asked["lang"] == "en"
