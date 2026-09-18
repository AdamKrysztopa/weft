"""The lexical answer metrics compare words — repair **R32.1**.

`token-recall` split on whitespace, so `two.` was not `two`; `rouge-l` used `rouge_score`'s default
tokenizer, which keeps only `[a-z0-9]`, so `Zażółć gęślą jaźń.` became `['za', 'g', 'l', 'ja']` and
`jaźń` matched `ja ń` perfectly. `32.10` reads both metrics in English and Polish; each case below
is one a whitespace or ASCII tokenizer gets wrong.
"""

import pytest

from weft_eval.contract import GenerationSample
from weft_eval.lexical import NoConfig, RougeL, TokenRecall
from weft_kernel.context import Context
from weft_kernel.payload import Produced


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en")


async def _score(metric: TokenRecall | RougeL, reference: str, prediction: str) -> float:
    outcome = await metric.evaluate(
        GenerationSample(query="q", prediction=prediction, reference=reference), _ctx()
    )
    assert isinstance(outcome, Produced)
    return outcome.value.value


async def test_a_word_is_recalled_whatever_punctuation_follows_it() -> None:
    # Act / Assert
    assert await _score(TokenRecall(NoConfig()), "forty two", "It is forty two.") == 1.0


async def test_a_polish_answer_is_recalled_word_for_word() -> None:
    # Act / Assert
    assert await _score(TokenRecall(NoConfig()), "gęślą jaźń", "Gęślą jaźń!") == 1.0


async def test_rouge_does_not_split_a_polish_word_at_its_diacritics() -> None:
    # Act — ASCII-only tokenization makes `jaźń` into `ja` and scores this 1.0.
    score = await _score(RougeL(), "jaźń", "ja ń")

    # Assert
    assert score == 0.0


@pytest.mark.parametrize(
    ("reference", "prediction"),
    [("Zażółć gęślą jaźń", "zażółć gęślą jaźń!"), ("forty two", "Forty two.")],
)
async def test_rouge_scores_the_same_words_as_a_perfect_match(
    reference: str, prediction: str
) -> None:
    # Act / Assert
    assert await _score(RougeL(), reference, prediction) == 1.0
