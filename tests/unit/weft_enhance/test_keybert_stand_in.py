"""Unit tests for `weft_enhance.keybert_stand_in`.

Mirrors `packages/weft-enhance/src/weft_enhance/keybert_stand_in.py`. Covers the happy
path (a repeated, meaningful word outranks a one-off, stopwords are excluded, and the
same content always ranks the same way — deterministic by construction, no model, no
network), the edge case of an empty batch (`NothingToProduce`, never an empty
`Produced([])`), and the error case of a non-positive configured `top_n`.
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_enhance.keybert_stand_in import KeyBertConfig, KeyBertKeywordExtractor
from weft_enhance.keywords import Keywords
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


async def test_run_ranks_a_repeated_word_above_a_one_off_and_drops_stopwords() -> None:
    # Arrange
    extractor = KeyBertKeywordExtractor(config=KeyBertConfig(top_n=2))
    node = _node("weft is a weft engine. the weft engine is a microkernel.")

    # Act
    outcome: Outcome[Sequence[Node]] = await extractor.run([node], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    enhanced = outcome.value[0]
    keywords = enhanced.ext_as(Keywords)
    assert keywords is not None
    assert keywords.terms == ("weft", "engine")  # "weft" (3x) outranks "engine" (2x)
    assert "is" not in keywords.terms  # a stopword, however often it repeats
    assert "a" not in keywords.terms  # shorter than the minimum word length too
    # Identity is unaffected — an Enhancer attaches a fact, it never rewrites content.
    assert enhanced.id == node.id
    assert enhanced.content == node.content

    # Same content, same ranking — required for the pipeline's re-index-is-idempotent
    # property to hold through this stage exactly as it does through `weft-embed`'s.
    again = await extractor.run([_node(node.content)], _ctx())
    assert isinstance(again, Produced)
    assert again.value[0].ext_as(Keywords) == keywords


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    extractor = KeyBertKeywordExtractor()

    # Act
    outcome = await extractor.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to extract keywords from")


def test_config_refuses_a_non_positive_top_n() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        KeyBertConfig(top_n=0)
