"""`ExampleFuser` — a stranger's `Fuser`: concatenates every list, keeps the first sighting of
each node, sorted by score.

`weft_retrieve.contract.Fuser`'s own load-bearing choice — `Out` is `Ranking`, never
`Candidates` — is what this class relies on: every stage after a `Fuser` is spared the
question of how many lists there were.
"""

from weft_kernel.context import Context
from weft_kernel.payload import NodeId, Outcome, Produced
from weft_retrieve.payload import Candidates, Passage, Ranking


class ExampleFuser:
    """Concatenates every ranked list, dropping a node it has already kept, then re-sorts by
    score. Satisfies `weft_retrieve.contract.Fuser` structurally — this class never imports it.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Candidates, ctx: Context) -> Outcome[Ranking]:
        del ctx
        seen: set[NodeId] = set()
        merged: list[Passage] = []
        for ranked_list in payload.lists:
            for passage in ranked_list.hits:
                if passage.node.id in seen:
                    continue
                seen.add(passage.node.id)
                merged.append(passage)
        merged.sort(key=lambda passage: passage.score, reverse=True)
        hits = tuple(
            passage.model_copy(update={"rank": index}) for index, passage in enumerate(merged)
        )
        contributors = tuple(dict.fromkeys(ranked_list.retriever for ranked_list in payload.lists))
        return Produced(value=Ranking(origin=payload.origin, hits=hits, contributors=contributors))
