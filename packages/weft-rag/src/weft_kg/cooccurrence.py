"""`CooccurrenceGraphBuilder` — the no-model, no-credential `Enhancer` rung. Ledger **11.6**.

**The heuristic, stated plainly rather than left for a reader to discover by running it on a
real corpus.** A Title-Case run of words is a name candidate; any two candidates the same node
mentions co-occur. It over-generates (a sentence-initial capitalised word that names nothing —
`"The"`, at the start of a sentence) and under-generates (a lower-cased acronym, or a name split
across a chunk boundary is missed as a single name). Both are accepted rather than hidden: this
stage's whole point is that the mechanism is honest and reproducible, not that it is good.

**Attaches a fact and writes no row.** `run` calls `Node.with_ext`, never `weft_kg.store`; that
split is what lets `cooccurrence-graph` sit in a pipeline with no graph store configured at all
— it simply attaches a fact nothing reads. `weft_kg.store.GraphStore.add` is the other half: it
reads `CooccurrenceGraph` off a node's `ext` and derives the entity and relation rows.

**The heuristic itself — the stopword list, the leading-stopword strip and the Title-Case-run
regex — lives in `weft_kg.names` now, not here.** Ledger `11.10` moved it once `graph-walk`
needed the identical rule to match a name in a *question* rather than a *chunk*: one notion of
what a name looks like, imported by both callers, rather than two copies free to drift apart.
`candidate_names` is that moved rule; `_graph_for` below still does its own counting over what
it returns, exactly as it always has.
"""

import itertools
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced
from weft_kg.names import candidate_names
from weft_kg.payload import CooccurrenceEdge, CooccurrenceGraph, EntityMention


class CooccurrenceSettings(BaseModel):
    """`cooccurrence-graph`'s `with:` config — two real knobs, requirement 6.

    Neither is a silent clamp: a value below 1 for either can only be a mistake — `Field(ge=1)`
    is what makes construction refuse loudly, naming the field, rather than quietly repairing it
    into an empty graph an operator would have to diagnose from an absence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The longest name candidate, in words. `New York City` is one candidate at `>=3` and
    #: three at `1`.
    max_name_words: int = Field(ge=1, default=4)
    #: A candidate mentioned fewer times than this, in one node's own content, is dropped
    #: before edges are formed.
    min_mentions: int = Field(ge=1, default=1)


class CooccurrenceGraphBuilder:
    """Attaches a `CooccurrenceGraph` to every node in a non-empty batch — never rewrites
    `content`, so node identity (`node.id`) is untouched.

    Satisfies `weft_enhance.contract.Enhancer` structurally: this class never imports it, the
    same path a third-party `Enhancer` plugin takes.
    """

    def __init__(self, config: CooccurrenceSettings | None = None) -> None:
        self._config = config if config is not None else CooccurrenceSettings()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no node to build a co-occurrence graph from")
        enhanced = [node.with_ext(self._graph_for(node.content)) for node in payload]
        return Produced(value=enhanced)

    def _graph_for(self, content: str) -> CooccurrenceGraph:
        counts: dict[str, int] = {}
        for name in candidate_names(content, max_words=self._config.max_name_words):
            counts[name] = counts.get(name, 0) + 1
        names = tuple(name for name, count in counts.items() if count >= self._config.min_mentions)
        entities = tuple(EntityMention(name=name, count=counts[name]) for name in names)
        relations = tuple(
            CooccurrenceEdge(source=source, target=target)
            for source, target in itertools.combinations(sorted(names), 2)
        )
        return CooccurrenceGraph(entities=entities, relations=relations)


__all__ = ["CooccurrenceGraphBuilder", "CooccurrenceSettings"]
