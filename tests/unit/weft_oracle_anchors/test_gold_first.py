"""`oracle-gold-first` — ledger **41.3**'s instrument check, `[phase_41.instrument]`.

A reorderer that puts every chunk of a relevant document first must, replayed through the same
capture, packing and scoring every arm goes through, realise dense's mrr@5 plus the oracle ceiling
exactly. If it does not, the instrument is losing gains a real reranker would have made. It reads
the relevant chunk ids per question from a file, finds its question through the pool entry, and
refuses by name rather than guessing.
"""

from __future__ import annotations

import json
from pathlib import Path

from weft_eval.pool import PoolQuestionEntry, text_sha256
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Failed, MediaType, Node, Produced
from weft_kernel.registry import Registry
from weft_oracle_anchors import Settings, register
from weft_oracle_anchors.gold_first import GOLD_FIRST, OracleGoldFirst, OracleGoldFirstConfig
from weft_retrieve import Reranker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store import Scored

_TEXT = "which charger fits"


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def _hit(words: str, score: float, rank: int) -> Passage:
    node = Node.synthetic(content=words, media_type=MediaType.TEXT, reason="fixture")
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by="pool")


def _ranking(hits: tuple[Passage, ...], question_id: str | None = "q-1") -> Ranking:
    ext = (
        {}
        if question_id is None
        else {
            PoolQuestionEntry.__namespace__: PoolQuestionEntry(
                corpus_digest="c" * 64, question_id=question_id, text_sha256=text_sha256(_TEXT)
            )
        }
    )
    return Ranking(origin=Query(text=_TEXT), hits=hits, ext=ext)


def _labels(tmp_path: Path, relevant: dict[str, list[str]]) -> Path:
    path = tmp_path / "gold.jsonl"
    path.write_text(
        "".join(
            json.dumps({"question_id": q, "text_sha256": text_sha256(_TEXT), "chunk_ids": ids})
            + "\n"
            for q, ids in relevant.items()
        ),
        encoding="utf-8",
    )
    return path


async def test_relevant_chunks_move_first_in_their_own_order_and_scores_agree(
    tmp_path: Path,
) -> None:
    # Arrange — relevant chunks sit at ranks 2 and 3 of four.
    hits = tuple(_hit(f"chunk {i}", 0.9 - i / 10, i) for i in range(4))
    gold = [str(hits[3].node.id), str(hits[2].node.id)]
    stage = OracleGoldFirst(OracleGoldFirstConfig(labels=_labels(tmp_path, {"q-1": gold})))

    # Act
    outcome = await stage.run(_ranking(hits), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    out = outcome.value.hits
    assert [hit.node.id for hit in out] == [hits[i].node.id for i in (2, 3, 0, 1)]
    assert [hit.rank for hit in out] == [0, 1, 2, 3]
    assert [hit.score for hit in out] == sorted((hit.score for hit in out), reverse=True)


async def test_a_question_with_no_relevant_chunk_in_the_pool_is_left_as_it_arrived(
    tmp_path: Path,
) -> None:
    # Arrange
    hits = (_hit("chunk 0", 0.9, 0), _hit("chunk 1", 0.8, 1))
    stage = OracleGoldFirst(OracleGoldFirstConfig(labels=_labels(tmp_path, {"q-1": []})))
    ranking = _ranking(hits)

    # Act
    outcome = await stage.run(ranking, _ctx())

    # Assert
    assert outcome == Produced(value=ranking)


async def test_a_ranking_with_no_pool_entry_or_an_unlabelled_question_fails_by_name(
    tmp_path: Path,
) -> None:
    # Arrange
    stage = OracleGoldFirst(OracleGoldFirstConfig(labels=_labels(tmp_path, {"q-1": []})))
    hits = (_hit("chunk 0", 0.9, 0),)

    # Act
    no_entry = await stage.run(_ranking(hits, question_id=None), _ctx())
    unlabelled = await stage.run(_ranking(hits, question_id="q-9"), _ctx())

    # Assert
    assert isinstance(no_entry, Failed) and "pool question entry" in no_entry.reason
    assert isinstance(unlabelled, Failed) and "'q-9'" in unlabelled.reason


def test_it_is_registered_beside_the_anchor_oracle(tmp_path: Path) -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-oracle-anchors")
    register(registrar, Settings())
    registrar.commit()

    # Act
    plugin = registry.entry(Reranker, GOLD_FIRST).factory(
        OracleGoldFirstConfig(labels=_labels(tmp_path, {}))
    )

    # Assert
    assert isinstance(plugin, OracleGoldFirst)
    assert GOLD_FIRST == "oracle-gold-first"
