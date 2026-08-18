"""`ExampleFixedRetriever` — a stranger's `Retriever`: two fixture passages, no database.

`docs/07-extension-cost.md` §9's own note: this pack's whole point is proving the query-path
contracts are implementable from outside, not proving a search engine — a real retriever
declares `needs_store` and reaches a store through `ctx.require(...)` (ledger 2.5); this one
declares an empty `needs_store` truthfully, because it needs none.
"""

from collections.abc import Sequence
from typing import ClassVar

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Outcome, Produced
from weft_retrieve.payload import Candidates, Passage, Query, QuerySet, RankedList
from weft_store.contract import Scored

NAME = "example-fixed"

_FIXTURE_TEXT: Sequence[str] = (
    "Weft is a RAG engine built as a microkernel.",
    "A capability is one package, zero edits to core.",
)


class ExampleFixedRetriever:
    """Answers every query with the same two fixture passages, ranked by fixture order.

    Satisfies `weft_retrieve.contract.Retriever` structurally — this class never imports it.
    """

    needs_store: ClassVar[tuple[type, ...]] = ()

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        lists = tuple(_ranked_list_for(query) for query in payload.queries)
        return Produced(value=Candidates(origin=payload.origin, lists=lists))


def _ranked_list_for(query: Query) -> RankedList:
    hits = tuple(
        Passage(
            scored=Scored(value=_fixture_node(text, rank), score=1.0 - rank * 0.1),
            rank=rank,
            retrieved_by=NAME,
        )
        for rank, text in enumerate(_FIXTURE_TEXT)
    )
    return RankedList(query=query, retriever=NAME, hits=hits)


def _fixture_node(text: str, rank: int) -> Node:
    return Node.synthetic(
        content=text,
        media_type=MediaType.TEXT,
        reason="example-fixed retriever fixture",
        ordinal=rank,
    )
