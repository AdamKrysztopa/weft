"""Unit tests for `weft_eval`'s `register()`.

Mirrors `packages/weft-eval/src/weft_eval/__init__.py`. Covers the happy path (every one of the
21 task-4.2 metrics plus task 4.1's own demonstration registers, under the right one of
`GenerationMetric`/`RetrievalMetric`, and the 6 judge prompts register under `Prompt`), the count
(exactly 22 metrics — 21 plus the demonstration — and 6 prompts, so a metric silently dropped from
`register()` fails this file rather than going unnoticed the way the reference's two docstring-only
`llm_judge/__init__.py` files did), and that an unknown settings field is refused.
"""

import pytest
from pydantic import ValidationError

from weft_eval import (
    ACCURACY_NAME,
    ANSWER_COMPLETENESS_NAME,
    ANSWER_CORRECTNESS_NAME,
    ANSWER_RELEVANCE_NAME,
    BERTSCORE_NAME,
    CONTEXT_RECALL_NAME,
    CONTEXT_RELEVANCE_NAME,
    EMBEDDING_SIMILARITY_NAME,
    EXACT_MATCH_NAME,
    F1_SCORE_NAME,
    FAITHFULNESS_NAME,
    KEY_TERMS_PRECISION_NAME,
    MEAN_AVERAGE_PRECISION_NAME,
    NDCG_AT_K_NAME,
    OVERLAP_AT_THRESHOLD_NAME,
    PRECISION_AT_K_NAME,
    RECALL_AT_K_NAME,
    ROUGE_1_NAME,
    ROUGE_2_NAME,
    ROUGE_L_NAME,
    TOKENS_OVERLAP_NAME,
    TOKENS_RECALL_NAME,
    OverlapAtThreshold,
    Settings,
    register,
)
from weft_eval.contract import GenerationMetric, RetrievalMetric
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_prompts.contract import Prompt

#: The 21 reference metrics, split by which contract they register under — the count this test's own
#: floor asserts, so a metric quietly dropped from `register()` cannot pass silently.
_GENERATION_NAMES = frozenset(
    {
        ROUGE_L_NAME,
        ROUGE_1_NAME,
        ROUGE_2_NAME,
        TOKENS_OVERLAP_NAME,
        TOKENS_RECALL_NAME,
        KEY_TERMS_PRECISION_NAME,
        EXACT_MATCH_NAME,
        F1_SCORE_NAME,
        ACCURACY_NAME,
        EMBEDDING_SIMILARITY_NAME,
        BERTSCORE_NAME,
        FAITHFULNESS_NAME,
        ANSWER_RELEVANCE_NAME,
        ANSWER_CORRECTNESS_NAME,
        ANSWER_COMPLETENESS_NAME,
    }
)
_RETRIEVAL_NAMES = frozenset(
    {
        PRECISION_AT_K_NAME,
        RECALL_AT_K_NAME,
        MEAN_AVERAGE_PRECISION_NAME,
        NDCG_AT_K_NAME,
        CONTEXT_RECALL_NAME,
        CONTEXT_RELEVANCE_NAME,
    }
)


def _registry() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


def test_register_adds_overlap_at_threshold_under_generation_metric() -> None:
    # Arrange / Act
    registry = _registry()

    # Assert
    entry = registry.entry(GenerationMetric, OVERLAP_AT_THRESHOLD_NAME)
    assert entry.factory is OverlapAtThreshold
    assert entry.distribution == "weft-eval"


def test_every_one_of_the_21_reference_metrics_registers_under_the_right_contract() -> None:
    # Arrange / Act
    registry = _registry()

    # Assert — 21 = 15 generation + 6 retrieval, per `.phase4-reference-recon.md`'s own inventory.
    assert len(_GENERATION_NAMES) + len(_RETRIEVAL_NAMES) == 21
    for name in _GENERATION_NAMES:
        assert registry.entry(GenerationMetric, name).distribution == "weft-eval"
    for name in _RETRIEVAL_NAMES:
        assert registry.entry(RetrievalMetric, name).distribution == "weft-eval"


def test_the_six_judge_prompts_register_under_prompt() -> None:
    # Arrange / Act
    registry = _registry()

    # Assert — the reference's own defect was these six being unreachable at all
    # (`.phase4-reference-recon.md` §1); registered names here is the fix, held as a fact rather
    # than a claim.
    prompt_names = registry.names_for(Prompt)
    assert len(prompt_names) == 6


def test_settings_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Settings.model_validate({"bogus": "x"})
