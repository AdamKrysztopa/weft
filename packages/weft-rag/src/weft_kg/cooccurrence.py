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
"""

import itertools
import re
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced
from weft_kg.payload import CooccurrenceEdge, CooccurrenceGraph, EntityMention

#: Words that are capitalised only because they open a sentence, not because they name
#: anything — filtered so a determiner does not become this stage's densest entity in every
#: node. Written fresh for this pack, not carried from any other module in this tree.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "A", "An", "And", "As", "At", "Because", "But", "By", "For", "From", "He", "How",
        "I", "If", "In", "Is", "It", "Its", "Of", "On", "Or", "She", "So", "Some", "That",
        "The", "There", "These", "They", "This", "Those", "To", "Was", "We", "Were",
        "What", "When", "Where", "Which", "Who", "Why", "With",
    }
)  # fmt: skip


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


def _cleaned(raw: str) -> str | None:
    """`raw`, whitespace-normalised, with every *leading* stopword stripped — `None` if nothing
    is left. A multi-word match starting a sentence ("The Board met...") would otherwise carry
    its sentence-initial stopword into the name ("The Board"); stripped only from the front,
    since a stopword is a sentence-initial artefact and the pattern below only ever matches a
    run starting where a capital letter begins.
    """
    words = raw.split()
    while words and words[0] in _STOPWORDS:
        words.pop(0)
    return " ".join(words) if words else None


class CooccurrenceGraphBuilder:
    """Attaches a `CooccurrenceGraph` to every node in a non-empty batch — never rewrites
    `content`, so node identity (`node.id`) is untouched.

    Satisfies `weft_enhance.contract.Enhancer` structurally: this class never imports it, the
    same path a third-party `Enhancer` plugin takes.
    """

    def __init__(self, config: CooccurrenceSettings | None = None) -> None:
        self._config = config if config is not None else CooccurrenceSettings()
        # `{0, n-1}` additional words beyond the first — `max_name_words` total.
        self._pattern = re.compile(
            rf"\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){{0,{self._config.max_name_words - 1}}}\b"
        )

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no node to build a co-occurrence graph from")
        enhanced = [node.with_ext(self._graph_for(node.content)) for node in payload]
        return Produced(value=enhanced)

    def _graph_for(self, content: str) -> CooccurrenceGraph:
        counts: dict[str, int] = {}
        for match in self._pattern.finditer(content):
            name = _cleaned(match.group())
            if name is None:
                continue
            counts[name] = counts.get(name, 0) + 1
        names = tuple(name for name, count in counts.items() if count >= self._config.min_mentions)
        entities = tuple(EntityMention(name=name, count=counts[name]) for name in names)
        relations = tuple(
            CooccurrenceEdge(source=source, target=target)
            for source, target in itertools.combinations(sorted(names), 2)
        )
        return CooccurrenceGraph(entities=entities, relations=relations)


__all__ = ["CooccurrenceGraphBuilder", "CooccurrenceSettings"]
