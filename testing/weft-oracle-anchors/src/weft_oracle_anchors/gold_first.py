"""`oracle-gold-first`: the instrument check Phase 41's pool-promotion protocol declares.

`oracle-gold-first` — the instrument check `eval/pool-promotion/protocol.toml` →
`[phase_41.instrument]` declares, ledger **41.3**.

Every chunk of a relevant document moves to the top in the order it arrived; everything else follows
in its own order. Replayed over a frozen pool, that ordering can only realise dense's mrr@5 plus the
oracle ceiling, so any shortfall is the instrument losing a gain, not the reorderer missing one. The
relevant chunk ids come from a file built with `scripts/pool_ceilings.py`'s own resolver, and the
question from the pool entry replay attaches, refused by name when either is missing.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_eval.pool import PoolQuestionEntry
from weft_kernel.context import Context
from weft_kernel.payload import Failed, Outcome, Produced
from weft_retrieve.payload import Passage, Ranking
from weft_store import Scored

GOLD_FIRST = "oracle-gold-first"

#: Added to a relevant chunk's score, so the emitted order and the scores agree while incoming
#: scores span less than it — true of cosine similarity.
_LIFT = 10.0


class GoldLabel(BaseModel):
    """One question's relevant chunk ids, one line of the labels file.

    Attributes:
        question_id: The pool question the label belongs to.
        text_sha256: The digest of the question's text.
        chunk_ids: Every chunk of a relevant document.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    text_sha256: str
    chunk_ids: tuple[str, ...]


class OracleGoldFirstConfig(BaseModel):
    """`oracle-gold-first`'s `with:` config.

    Attributes:
        labels: The labels file, one `GoldLabel` per line.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    labels: Path


class OracleGoldFirst:
    """Puts the relevant chunks first.

    Satisfies `weft_retrieve.contract.Reranker` structurally; `cost_bound = (0, 0)`, a set lookup
    per hit.
    """

    score_semantics: ClassVar[str] = (
        "the incoming score, plus 10 for a chunk of a relevant document — orders relevant "
        "chunks first and is not comparable to a score from a different stage"
    )
    config_model: ClassVar[type[OracleGoldFirstConfig]] = OracleGoldFirstConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: OracleGoldFirstConfig) -> None:
        self._labels = {
            label.question_id: label
            for label in (
                GoldLabel.model_validate_json(line)
                for line in config.labels.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        }

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Move every relevant chunk to the top, keeping arrival order within both groups.

        Args:
            payload: The ranking to reorder; it must carry a pool question entry.
            ctx: Unused.

        Returns:
            `Produced` carrying the reordered, lifted hits, or `Failed` when the ranking carries no
            pool question entry or its question has no gold label.
        """
        del ctx
        entry = payload.ext.get(PoolQuestionEntry.__namespace__)
        if not isinstance(entry, PoolQuestionEntry):
            return Failed(reason="oracle-gold-first requires a pool question entry on the ranking")
        label = self._labels.get(entry.question_id)
        if label is None:
            return Failed(reason=f"no gold label for question id {entry.question_id!r}")
        gold = frozenset(label.chunk_ids)
        order = sorted(
            range(len(payload.hits)), key=lambda i: str(payload.hits[i].node.id) not in gold
        )
        if order == list(range(len(payload.hits))) and not gold:
            return Produced(value=payload)
        hits = tuple(
            Passage(
                scored=Scored(
                    value=payload.hits[i].node,
                    score=payload.hits[i].score
                    + (_LIFT if str(payload.hits[i].node.id) in gold else 0.0),
                ),
                rank=rank,
                retrieved_by=payload.hits[i].retrieved_by,
                label=payload.hits[i].label,
            )
            for rank, i in enumerate(order)
        )
        return Produced(value=payload.model_copy(update={"hits": hits}))


__all__ = ["GOLD_FIRST", "GoldLabel", "OracleGoldFirst", "OracleGoldFirstConfig"]
