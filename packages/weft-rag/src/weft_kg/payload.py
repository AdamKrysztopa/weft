"""`CooccurrenceGraph` — this pack's own namespaced fact: which names a node mentions, and
which of them co-occur. Ledger **11.6**.

Attaches to `Node.ext` (`weft_kernel.payload.ext.ExtModel`), never to a query-path payload's
`ext` — `docs/02-extension-model.md` §1's own "Call it only for an `ExtModel` that attaches to
`Node.ext`" rule (`docs/lessons.md` L5.20) — so `weft_kg.register` calls
`registrar.add_ext_model(CooccurrenceGraph)`. `EntityMention`/`CooccurrenceEdge` are plain,
unnamespaced value objects carried *inside* it; only the outer model needs a namespace and a
schema version.

**No field named `technique`, on any of the three models.** `weft_generate.representation.
citable_nodes` cites a single-parent node carrying an ext model with a `technique: str`
attribute *as its parent* — a field of that name here would make anything derived from these
nodes cite the chunk instead of itself. `11.7`'s fact nodes are the ones that constraint binds;
kept out of this pack's vocabulary from its very first ext model.
"""

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.payload import ExtModel


class EntityMention(BaseModel):
    """One name this pack's own co-occurrence heuristic found in a single node's content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    #: How many times this exact name occurred in the node's own content — never a corpus-wide
    #: count, which lives in the store's `kg_entities` table instead.
    count: int = Field(ge=1, default=1)


class CooccurrenceEdge(BaseModel):
    """One undirected co-occurrence: `source` and `target` were both mentioned by the same node.

    `source < target` lexicographically is this pack's own convention for a canonical
    spelling, so a pair is never stored twice under swapped endpoints —
    `weft_kg.cooccurrence.CooccurrenceGraphBuilder` is the one place that invariant is
    established.

    `predicate` is a plain `str`, deliberately not an `Enum`: `11.7` extracts an open
    vocabulary of predicates from a model, so the value space this field admits is not this
    task's to close.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    predicate: str = "co-occurs-with"
    count: int = Field(ge=1, default=1)


class CooccurrenceGraph(ExtModel):
    """This node's own entity mentions and co-occurrence edges — crude, deterministic, no model
    call.

    `__namespace__` is this distribution's own pack name, collision-free by construction
    (`docs/02-extension-model.md` §1). `__schema_version__` is G9's own second axis — a schema
    in a user's database, not a fact about which contract version this pack implements.
    """

    __namespace__ = "weft-kg"
    __schema_version__ = "1.0.0"

    entities: tuple[EntityMention, ...] = ()
    relations: tuple[CooccurrenceEdge, ...] = ()


__all__ = ["CooccurrenceEdge", "CooccurrenceGraph", "EntityMention"]
