"""`scripts/pool_ceilings.py` — ledger **40.4**: the free bound, read off a frozen pool.

A reorderer only moves what the pool already holds, so how much it could gain is a property of the
pool and of dense's own reciprocal rank, computed before any reorderer runs. Two ceilings, both
means over every question in the corpus (`eval/pool-promotion/protocol.toml` → `[ceilings]`):

- oracle gain = 1[a relevant document has a chunk in the pool] − RR@5(dense);
- promotion gain = 1[the rule fires and a pool chunk of a relevant document holds one of its
  anchors] × (1 − RR@5(dense)), containment judged by `anchor-promote`'s own matcher over the
  pool's chunks only.
"""

from __future__ import annotations

import hashlib

import pytest
from pool_ceilings import QuestionCeiling, question_ceiling, relevant_by_question, slice_summary

from weft_eval.pool import PoolChunk, PoolQuestion, relevant_set_sha256, text_sha256


def _chunk(node: str, document: str, content: str, score: float) -> tuple[PoolChunk, str]:
    return (
        PoolChunk(
            node_id=node,
            document_id=f"/corpus/{document}",
            content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            score=score,
        ),
        content,
    )


def _question(text: str, *chunks: tuple[PoolChunk, str]) -> tuple[PoolQuestion, dict[str, str]]:
    question = PoolQuestion(
        id="q-1",
        text_sha256=text_sha256(text),
        relevant_sha256=relevant_set_sha256([]),
        rule_fires=False,
        chunks=tuple(chunk for chunk, _ in chunks),
    )
    return question, {chunk.node_id: content for chunk, content in chunks}


def test_the_oracle_gain_is_what_a_perfect_reorder_of_the_pool_would_add() -> None:
    # Arrange — the relevant document's chunk sits third, so dense scored RR 1/3.
    question, contents = _question(
        "what is weft",
        _chunk("n1", "a.txt", "alpha", 0.9),
        _chunk("n2", "b.txt", "beta", 0.8),
        _chunk("n3", "c.txt", "gamma", 0.7),
    )

    # Act
    ceiling = question_ceiling(
        question,
        text="what is weft",
        relevant=frozenset({"/corpus/c.txt"}),
        contents=contents,
        rr5=1 / 3,
    )

    # Assert
    assert ceiling.any_relevant_in_pool is True
    assert ceiling.best_relevant_rank == 3
    assert ceiling.oracle_gain == pytest.approx(2 / 3)
    assert ceiling.distinct_documents == 3


def test_a_relevant_document_the_pool_never_held_gives_no_reorderer_anything_to_gain() -> None:
    # Arrange
    question, contents = _question("what is weft", _chunk("n1", "a.txt", "alpha", 0.9))

    # Act
    ceiling = question_ceiling(
        question,
        text="what is weft",
        relevant=frozenset({"/corpus/z.txt"}),
        contents=contents,
        rr5=0.0,
    )

    # Assert
    assert (ceiling.any_relevant_in_pool, ceiling.best_relevant_rank) == (False, None)
    assert (ceiling.oracle_gain, ceiling.promotion_gain) == (0.0, 0.0)


@pytest.mark.parametrize(
    ("text", "relevant_content", "gain"),
    [
        ("what does WRH123 mean", "WRH123 is the reset code", 1 - 1 / 2),
        ("what does WRH123 mean", "a reset code with no identifier", 0.0),
        ("what does the reset code mean", "WRH123 is the reset code", 0.0),
    ],
    ids=["anchor-held", "anchor-not-held", "no-anchor"],
)
def test_promotion_can_only_gain_where_the_rule_fires_and_a_relevant_chunk_holds_an_anchor(
    text: str, relevant_content: str, gain: float
) -> None:
    # Arrange — the relevant chunk is second: RR 1/2.
    question, contents = _question(
        text,
        _chunk("n1", "a.txt", "the STX58 manual", 0.9),
        _chunk("n2", "b.txt", relevant_content, 0.8),
    )

    # Act
    ceiling = question_ceiling(
        question,
        text=text,
        relevant=frozenset({"/corpus/b.txt"}),
        contents=contents,
        rr5=1 / 2,
    )

    # Assert
    assert ceiling.promotion_gain == pytest.approx(gain)
    assert ceiling.rule_fires is (text != "what does the reset code mean")


def test_a_content_that_no_longer_hashes_to_the_pool_is_refused_naming_the_chunk() -> None:
    # Arrange
    question, contents = _question("what is weft", _chunk("n1", "a.txt", "alpha", 0.9))
    contents["n1"] = "altered"

    # Act
    with pytest.raises(ValueError, match="n1"):
        question_ceiling(
            question,
            text="what is weft",
            relevant=frozenset({"/corpus/a.txt"}),
            contents=contents,
            rr5=1.0,
        )


def _ceiling(identifier: str, *, oracle: float, promotion: float, rr5: float) -> QuestionCeiling:
    return QuestionCeiling(
        question_id=identifier,
        rr5=rr5,
        any_relevant_in_pool=oracle + rr5 > 0,
        best_relevant_rank=1,
        distinct_documents=5,
        rule_fires=promotion > 0,
        oracle_gain=oracle,
        promotion_gain=promotion,
    )


def test_every_slice_is_a_mean_over_its_own_questions_and_all_is_over_every_question() -> None:
    # Arrange
    ceilings = (
        _ceiling("q-1", oracle=0.5, promotion=0.5, rr5=0.5),
        _ceiling("q-2", oracle=0.0, promotion=0.0, rr5=1.0),
        _ceiling("q-3", oracle=1.0, promotion=0.0, rr5=0.0),
    )
    axes = {
        "q-1": {"anchored": "yes", "split": "test"},
        "q-2": {"anchored": "no", "split": "test"},
        "q-3": {"anchored": "no", "split": "train"},
    }

    # Act
    summary = slice_summary(ceilings, axes)

    # Assert
    assert summary["all"].n == 3
    assert summary["all"].oracle_ceiling == pytest.approx(0.5)
    assert summary["all"].promotion_ceiling == pytest.approx(1 / 6)
    assert summary["all"].mrr5 == pytest.approx(0.5)
    assert summary["anchored=no"].n == 2
    assert summary["anchored=no"].oracle_ceiling == pytest.approx(0.5)
    assert summary["split=train"].promotion_ceiling == 0.0
    assert summary["rule-fires=true"].n == 1


def test_relevant_labels_resolve_against_the_pools_own_document_ids() -> None:
    # Arrange — ESCI names relevant documents by manifest id; the pool knows resolved paths.
    labels = {"q-1": ("B01",), "q-2": ("C01",)}
    documents = ("/capture/corpus/b.txt", "/capture/corpus/c.txt")

    # Act
    relevant = relevant_by_question(
        labels, document_ids=documents, document_labels={"B01": "b.txt", "C01": "c.txt"}
    )

    # Assert
    assert relevant == {
        "q-1": frozenset({"/capture/corpus/b.txt"}),
        "q-2": frozenset({"/capture/corpus/c.txt"}),
    }
