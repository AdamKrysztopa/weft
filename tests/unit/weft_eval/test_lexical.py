"""Unit tests for `weft_eval.lexical`.

Mirrors `packages/weft-rag/src/weft_eval/lexical.py`. One happy path, the empty-reference edge
case (`NothingToProduce`, uniformly, per the module's own rule) and one failure case per metric
family — token metrics and ROUGE.
"""

from weft_eval.contract import GenerationSample
from weft_eval.lexical import KeyTermsPrecision, NoConfig, Rouge1, RougeL, TokenOverlap, TokenRecall
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_token_overlap_is_the_jaccard_similarity_of_the_two_token_sets() -> None:
    # Arrange — {sky, is, blue} vs {sky, blue, sea}: intersection 2, union 4.
    metric = TokenOverlap(NoConfig())
    sample = GenerationSample(query="q", prediction="sky is blue", reference="sky blue sea")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 0.5
    assert outcome.value.metric_name == "token_overlap"


async def test_token_recall_empty_reference_is_nothing_to_produce() -> None:
    # Arrange
    metric = TokenRecall(NoConfig())
    sample = GenerationSample(query="q", prediction="anything", reference="")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_token_recall_no_prediction_fails_rather_than_scoring_zero() -> None:
    # Arrange
    metric = TokenRecall(NoConfig())
    sample = GenerationSample(query="q", prediction=None, reference="sky blue")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Failed)


async def test_key_terms_precision_scores_predicted_content_words_against_reference() -> None:
    # Arrange — reference key terms (stopwords dropped): {paris, capital, france}.
    metric = KeyTermsPrecision(NoConfig())
    sample = GenerationSample(
        query="q", prediction="paris is nice", reference="the capital of france is paris"
    )

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert — 1 of 3 predicted tokens ("paris") is a key term.
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1 / 3


async def test_rouge_l_scores_an_identical_prediction_as_a_perfect_match() -> None:
    # Arrange
    metric = RougeL()
    sample = GenerationSample(query="q", prediction="the cat sat", reference="the cat sat")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.value == 1.0
    assert outcome.value.metric_name == "rouge_l"


async def test_rouge_1_empty_reference_is_nothing_to_produce() -> None:
    # Arrange
    metric = Rouge1()
    sample = GenerationSample(query="q", prediction="anything", reference="   ")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)
