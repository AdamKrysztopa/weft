"""`ExampleReranker` — a stranger's `Reranker`: rescored by lexical overlap with the original ask.

Rescores against `Ranking.origin` — the user's own words — never against a derived query,
which is `weft_retrieve.payload.QuerySet.origin`'s own obligation carried one type further
down the pipeline (see `weft_example_query.transform`'s module docstring for the same rule
stated where it starts).
"""

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Passage, Ranking
from weft_store.contract import Scored


class ExampleReranker:
    """Rescores every passage by the fraction of the original question's words it shares.

    Satisfies `weft_retrieve.contract.Reranker` structurally — this class never imports it.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        del ctx
        query_words = frozenset(payload.origin.text.lower().split())
        ordered = sorted(
            payload.hits, key=lambda passage: _overlap(query_words, passage), reverse=True
        )
        hits = tuple(
            passage.model_copy(
                update={
                    "rank": index,
                    "scored": Scored(value=passage.node, score=_overlap(query_words, passage)),
                }
            )
            for index, passage in enumerate(ordered)
        )
        return Produced(value=payload.model_copy(update={"hits": hits}))


def _overlap(query_words: frozenset[str], passage: Passage) -> float:
    if not query_words:
        return passage.score
    shared = query_words & frozenset(passage.node.content.lower().split())
    return len(shared) / len(query_words)
