"""`GraphData` — this pack's own namespaced fact: which entities a node mentions, and which
of them co-occur.

Attaches to `Node.ext` (`weft_kernel.payload.ext.ExtModel`), never to a query-path payload's
`ext` — so, per `docs/02-extension-model.md` section 1's own "Call it only for an `ExtModel`
that attaches to `Node.ext`" rule (`docs/lessons.md` L5.20), this pack's `register()` calls
`registrar.add_ext_model(GraphData)`. `Entity`/`Relation` are plain, unnamespaced value
objects carried *inside* `GraphData` — only the outer model needs a namespace and a schema
version, the same shape `weft_retrieve.payload.RankedList` carries plain `Passage` values
without each one separately declaring anything.
"""

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.payload import ExtModel


class Entity(BaseModel):
    """One entity mention this pack's own extractor found in a single node's content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    #: How many times this exact name occurred in the node's own content — never a corpus-wide
    #: count, which lives in `weft_example_graph_entities` instead (see `weft_example_graph.store`).
    count: int = Field(ge=1, default=1)


class Relation(BaseModel):
    """One undirected co-occurrence: `source` and `target` were both mentioned by the same node.

    `source < target` lexicographically is this pack's own convention for a canonical
    spelling — `weft_example_graph.extraction.extract_graph_data` is the one place that invariant is
    established, so a relation is never stored twice under swapped endpoints.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    predicate: str = "co_occurs_with"
    count: int = Field(ge=1, default=1)


class GraphData(ExtModel):
    """This node's own entities and relations — crude, deterministic, no model call.

    `__namespace__` is this distribution's own name, collision-free by construction
    (`docs/02-extension-model.md` section 1). `__schema_version__` is G9's own second axis —
    a schema in a user's database, not a fact about which contract version this pack
    implements — and the default `upgrade` (refuse, naming the stored and current versions)
    is correct until this shape's first change.
    """

    __namespace__ = "weft-example-graph"
    __schema_version__ = "1.0.0"

    entities: tuple[Entity, ...] = ()
    relations: tuple[Relation, ...] = ()


__all__ = ["Entity", "GraphData", "Relation"]
