"""`oracle-anchor-promote` — ledger **40.7**: `anchor-promote` with the anchors a person wrote.

Phase 40 reads the rule extractor's arm beside this one, question by question, so a null from
promotion can be told apart from a null from extraction. It promotes by `40.5`'s blind labels
through the same `promote` function `anchor-promote` calls, finds its question through the pool
entry replay puts on each ranking — `Query` carries no id, and TechQA asks twelve texts twice — and
refuses a question by name rather than guessing when the entry, the label, or the text disagree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from weft_eval.pool import PoolQuestionEntry, text_sha256
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Failed, MediaType, Node, Produced
from weft_kernel.registry import Registry
from weft_oracle_anchors import (
    NAME,
    OracleAnchorPromote,
    OracleAnchorPromoteConfig,
    OracleLabelsError,
    Settings,
    load_oracle_labels,
    register,
)
from weft_retrieve import Reranker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store import Scored

_TEXT = "how do I clear the reset code"


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def _hit(words: str, score: float, rank: int) -> Passage:
    node = Node.synthetic(content=words, media_type=MediaType.TEXT, reason="fixture")
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by="pool")


def _ranking(question_id: str | None, text: str = _TEXT) -> Ranking:
    ext = (
        {}
        if question_id is None
        else {
            PoolQuestionEntry.__namespace__: PoolQuestionEntry(
                corpus_digest="c" * 64, question_id=question_id, text_sha256=text_sha256(text)
            )
        }
    )
    return Ranking(
        origin=Query(text=text),
        hits=(_hit("an unrelated page", 0.9, 0), _hit("the reset code is cleared by", 0.5, 1)),
        ext=ext,
    )


def _labels(tmp_path: Path, *rows: dict[str, object]) -> Path:
    path = tmp_path / "labels.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _oracle(path: Path) -> OracleAnchorPromote:
    return OracleAnchorPromote(OracleAnchorPromoteConfig(labels=path))


async def test_the_labelled_anchors_promote_where_the_rule_would_find_none(tmp_path: Path) -> None:
    # Arrange — "reset code" has no identifier shape, so the rule leaves this ranking alone.
    path = _labels(
        tmp_path,
        {"question_id": "q-1", "text_sha256": text_sha256(_TEXT), "anchors": ["reset code"]},
    )

    # Act
    outcome = await _oracle(path).run(_ranking("q-1"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [p.node.content for p in outcome.value.hits][0] == "the reset code is cleared by"


async def test_two_ids_asking_one_text_each_receive_their_own_label(tmp_path: Path) -> None:
    # Arrange — the same text, labelled differently under two ids.
    path = _labels(
        tmp_path,
        {"question_id": "q-1", "text_sha256": text_sha256(_TEXT), "anchors": ["reset code"]},
        {"question_id": "q-2", "text_sha256": text_sha256(_TEXT), "anchors": []},
    )
    oracle = _oracle(path)

    # Act
    first = await oracle.run(_ranking("q-1"), _ctx())
    second = await oracle.run(_ranking("q-2"), _ctx())

    # Assert
    assert isinstance(first, Produced) and isinstance(second, Produced)
    assert first.value.hits[0].node.content == "the reset code is cleared by"
    assert second.value.hits == _ranking("q-2").hits


@pytest.mark.parametrize(
    ("question_id", "text", "named"),
    [
        (None, _TEXT, "pool"),
        ("q-9", _TEXT, "q-9"),
        ("q-1", "a different question", "q-1"),
    ],
    ids=["no-pool-entry", "no-label", "text-differs"],
)
async def test_a_question_it_cannot_match_to_its_label_is_refused_by_name(
    tmp_path: Path, question_id: str | None, text: str, named: str
) -> None:
    # Arrange
    path = _labels(
        tmp_path,
        {"question_id": "q-1", "text_sha256": text_sha256(_TEXT), "anchors": ["reset code"]},
    )

    # Act
    outcome = await _oracle(path).run(_ranking(question_id, text), _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert named in outcome.reason


def test_a_labels_file_naming_one_question_twice_is_refused(tmp_path: Path) -> None:
    # Arrange
    row: dict[str, object] = {
        "question_id": "q-1",
        "text_sha256": text_sha256(_TEXT),
        "anchors": [],
    }
    path = _labels(tmp_path, row, row)

    # Act
    with pytest.raises(OracleLabelsError) as caught:
        load_oracle_labels(path)

    # Assert
    assert "q-1" in str(caught.value)


def test_it_registers_one_reranker_through_the_public_pack_entry() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-oracle-anchors")

    # Act
    register(registrar, Settings())
    registrar.commit()

    # Assert
    assert registry.names_for(Reranker) == {NAME}
    assert NAME == "oracle-anchor-promote"
