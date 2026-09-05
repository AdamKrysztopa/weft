"""Unit tests for `weft_eval.judges`.

Mirrors `packages/weft-rag/src/weft_eval/judges.py`. The `LLM` is a stub and the cascade is
real — `weft_retrieve.rerank`'s own test module states why: stubbing the cascade itself would
leave each judge's own reading of a *typed* answer untested against the shape the cascade
actually returns. `native_structured_available` is `False` on the stub, so every judge here runs
tier 2 of the cascade, exactly `test_rerank.py`'s own precedent. `Embedder` is the real,
deterministic `HashEmbedder` for the two judges (`AnswerRelevance`, `AnswerCorrectness`) that need
one — never a stub, so the `ctx.require(Embedder)` seam is proven for real.

One happy path and one edge case (an empty input that needs no model call at all) per judge, plus
two explicit failure cases: `ContextRelevance` refusing a hallucinated sentence index, and
`Faithfulness` refusing a sample with no prediction.
"""

from collections.abc import Mapping

import pytest
from pydantic import BaseModel

from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_eval.contract import GenerationSample, RetrievalSample, RetrievedPassage
from weft_eval.judges import (
    AnswerCompleteness,
    AnswerCorrectness,
    AnswerCorrectnessConfig,
    AnswerRelevance,
    ContextRecall,
    ContextRelevance,
    Faithfulness,
    JudgeConfig,
)
from weft_eval.prompts import (
    ClaimSupport,
    CompletenessJudgement,
    ContextRecallJudgement,
    ContextRelevanceJudgement,
    FactualClassification,
    FaithfulnessJudgement,
    GeneratedQuestions,
    StatementSupport,
)
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, NothingToProduce, Produced
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script of typed replies."""

    def __init__(self, replies: list[BaseModel]) -> None:
        self._replies = [reply.model_dump_json() for reply in replies]
        self.calls = 0

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> object:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(
        self, rendered: Rendered, *, role: str, ctx: Context
    ) -> Produced[Completion]:
        del rendered, role, ctx
        reply = self._replies[self.calls]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


def _ctx(llm: _StubLLM, *, embedder: HashEmbedder | None = None) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    if embedder is not None:
        services.add(Embedder, embedder)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


async def test_faithfulness_scores_the_fraction_of_supported_statements() -> None:
    # Arrange
    llm = _StubLLM(
        [
            FaithfulnessJudgement(
                statements=(
                    StatementSupport(statement="The sky is blue.", supported=True),
                    StatementSupport(statement="The sky is vast.", supported=False),
                )
            )
        ]
    )
    metric = Faithfulness(JudgeConfig())
    sample = GenerationSample(
        query="q",
        prediction="The sky is blue and vast.",
        reference="The sky is blue.",
        contexts=("The sky is blue.",),
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 0.5
    assert outcome.value.metric_name == "faithfulness"


async def test_faithfulness_no_context_is_nothing_to_produce() -> None:
    # Arrange — no model call needed: nothing was retrieved to check groundedness against.
    metric = Faithfulness(JudgeConfig())
    sample = GenerationSample(query="q", prediction="anything", reference="r")

    # Act
    outcome = await metric.evaluate(sample, _ctx(_StubLLM([])))

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_faithfulness_no_prediction_fails_rather_than_scoring_zero() -> None:
    # Arrange
    metric = Faithfulness(JudgeConfig())
    sample = GenerationSample(query="q", prediction=None, reference="r", contexts=("x",))

    # Act
    outcome = await metric.evaluate(sample, _ctx(_StubLLM([])))

    # Assert
    assert isinstance(outcome, Failed)


async def test_context_recall_scores_the_fraction_of_supported_claims() -> None:
    # Arrange
    llm = _StubLLM(
        [
            ContextRecallJudgement(
                claims=(ClaimSupport(claim="Paris is the capital of France.", supported=True),)
            )
        ]
    )
    metric = ContextRecall(JudgeConfig())
    sample = RetrievalSample(
        query="q",
        retrieved=(RetrievedPassage(id="a", text="Paris is the capital of France."),),
        reference="Paris is the capital of France.",
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1.0
    assert outcome.value.metric_name == "context_recall"


async def test_context_recall_no_reference_is_nothing_to_produce() -> None:
    # Arrange
    metric = ContextRecall(JudgeConfig())
    sample = RetrievalSample(query="q", retrieved=(RetrievedPassage(id="a", text="x"),))

    # Act
    outcome = await metric.evaluate(sample, _ctx(_StubLLM([])))

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_context_relevance_scores_the_fraction_of_relevant_sentences() -> None:
    # Arrange — two code-segmented sentences; the judge marks only the first relevant.
    llm = _StubLLM([ContextRelevanceJudgement(relevant_indices=(0,))])
    metric = ContextRelevance(JudgeConfig())
    sample = RetrievalSample(
        query="What is the capital of France?",
        retrieved=(
            RetrievedPassage(
                id="a", text="Paris is the capital of France. It has the Eiffel Tower."
            ),
        ),
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 0.5
    assert outcome.value.metric_name == "context_relevance"


async def test_context_relevance_refuses_an_index_the_judge_was_never_offered() -> None:
    # Arrange — one sentence offered (index 0); the judge marks index 5, which was never
    # offered. Scoring a partial or invented answer would mix a real judgement with a
    # hallucinated one, so this is refused by name rather than clamped or ignored.
    llm = _StubLLM([ContextRelevanceJudgement(relevant_indices=(5,))])
    metric = ContextRelevance(JudgeConfig())
    sample = RetrievalSample(
        query="q", retrieved=(RetrievedPassage(id="a", text="One sentence only."),)
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx(llm))

    # Assert
    assert isinstance(outcome, Failed)


async def test_answer_relevance_scores_generated_questions_against_the_original() -> None:
    # Arrange — the judge-generated question is character-identical to the query, so a
    # content-hashed embedder gives them the identical vector: cosine similarity 1.0.
    llm = _StubLLM([GeneratedQuestions(questions=("What is the capital of France?",))])
    metric = AnswerRelevance(JudgeConfig())
    sample = GenerationSample(
        query="What is the capital of France?",
        prediction="Paris is the capital of France.",
        reference="Paris",
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx(llm, embedder=HashEmbedder()))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == pytest.approx(1.0)
    assert outcome.value.metric_name == "answer_relevance"


async def test_answer_relevance_empty_prediction_is_nothing_to_produce() -> None:
    # Arrange
    metric = AnswerRelevance(JudgeConfig())
    sample = GenerationSample(query="q", prediction="  ", reference="r")

    # Act
    outcome = await metric.evaluate(sample, _ctx(_StubLLM([])))

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_answer_correctness_combines_factual_f1_and_semantic_similarity() -> None:
    # Arrange — a perfect factual match (F1 1.0) and identical prediction/reference text
    # (semantic similarity 1.0 under a content-hashed embedder), so the weighted value is 1.0
    # regardless of the weight.
    llm = _StubLLM(
        [
            FactualClassification(
                true_positives=("Paris is the capital of France.",),
                false_positives=(),
                false_negatives=(),
            )
        ]
    )
    metric = AnswerCorrectness(AnswerCorrectnessConfig())
    sample = GenerationSample(
        query="q",
        prediction="Paris is the capital of France.",
        reference="Paris is the capital of France.",
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx(llm, embedder=HashEmbedder()))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == pytest.approx(1.0)
    assert outcome.value.metric_name == "answer_correctness"


async def test_answer_correctness_empty_reference_is_nothing_to_produce() -> None:
    # Arrange
    metric = AnswerCorrectness(AnswerCorrectnessConfig())
    sample = GenerationSample(query="q", prediction="anything", reference="")

    # Act
    outcome = await metric.evaluate(sample, _ctx(_StubLLM([])))

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_answer_completeness_scores_the_fraction_of_covered_points() -> None:
    # Arrange
    llm = _StubLLM([CompletenessJudgement(covered=("point one",), missing=("point two",))])
    metric = AnswerCompleteness(JudgeConfig())
    sample = GenerationSample(query="q", prediction="a partial answer", reference="the full answer")

    # Act
    outcome = await metric.evaluate(sample, _ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 0.5
    assert outcome.value.metric_name == "answer_completeness"


async def test_answer_completeness_empty_reference_is_nothing_to_produce() -> None:
    # Arrange
    metric = AnswerCompleteness(JudgeConfig())
    sample = GenerationSample(query="q", prediction="anything", reference="")

    # Act
    outcome = await metric.evaluate(sample, _ctx(_StubLLM([])))

    # Assert
    assert isinstance(outcome, NothingToProduce)
