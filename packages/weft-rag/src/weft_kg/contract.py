"""The graph traversal contract — published here, never by the kernel. Ledger task **11.4**.

`S12` settled that this contract ships from **the pack that owns the capability**, not from
`weft-store`, and that family membership is deferred behind a named trigger rather than assumed.
`docs/02-extension-model.md` §1 → *Who publishes a contract* is the rule it follows: the kernel
publishes the contract *mechanism* and no capability contract of its own, and a pack depends on
the pack that publishes the contract it implements, exactly as it would on any third party's.

**Not a `Stage`.** `weft_store.contract.VectorSearch` states the rule this module follows
verbatim: "nothing in an ingest pipeline calls `search_vector`, and a future `Retriever` resolves
this capability directly against the configured store rather than through the runner's stage
machinery." Traversal is the same shape — reached through `ctx.require`, never run as a pipeline
rung — so `GraphTraversal` declares no `Stage[In, Out]` base and the runner never reads
`__orig_bases__` off it.

**`version` is readable off the class but carries no `isinstance` weight** — the argument
`weft_extract.contract`'s module docstring makes in full and every contract in this tree copies
unchanged. `typing.Protocol` computes `__protocol_attrs__` once, by walking every attribute (and
bare annotation) present in the class's own body when the class statement closes. Declared
directly in the body, `version` would become a *required* structural member, and a stranger that
implements every method below and never restates `version` would fail a capability check that
has nothing to do with capability. So it is declared only under `if TYPE_CHECKING:` and assigned
for real once the class body has already closed.

**Selectable through one module-level constant, never a `ClassVar` on the Protocol** — the form
ledger task `9.0` fixed and `weft_store.contract.STORE_ROLE` and `weft_embed.contract.EMBED_ROLE`
both carry: `weft_kernel.context.ServiceRole` holds `contract` as a bare `type`, so the kernel
names no capability and `[services] graph` selects an implementation with nothing added to
`weft-kernel`.

**`EntityId` is a `NewType` over `str`, not a content digest.** `S12`: "an identity a merge
revises cannot carry a content-digest id" — the same reasoning `weft_kernel.payload.ids.NodeId`
carries for a *node's* identity does not hold for an entity's, because a merge must be able to
revise which row a name resolves to without the id itself changing meaning. That is the whole of
why entities are rows rather than `Node`s.

**`Entity` carries exactly two fields, and that is deliberate.** A contract states what a caller
gets; how an entity is stored and how its canonical id is computed is task `11.8`'s, one task
later, and a contract that already carried storage-shaped fields would narrow what `11.8` is free
to design. `id` and `name` are the whole of what every member below needs to answer with.

**`nodes_for_entities` walks entity → node, in the direction retrieval traverses it.** Ledger task
`11.10` needs *name → entities → neighbourhood → nodes*, so a member that only ever went the other
way would leave that walk unbuildable — the reading this module settles rather than assumes,
because the ledger's own phrase admits both directions.

**Every member answers in batch.** `entities_by_name`, `nodes_for_entities` and `neighbourhood`
each take a sequence and answer for every element of it in one call, not one round trip per name —
the property that keeps a bounded walk from becoming N round trips against whatever backs it.

**Three members, not the four `11.4` fixed — narrowed at ledger task `11.5` and versioned `2.0.0`
for it.** The first out-of-tree implementation was a graph over ordinary tables with no vector
column anywhere in it, and it could satisfy three members honestly and `nearest_entities` not at
all — so the bundle made a complete graph backend into a three-quarters implementer of a capability
it fully had. `weft_store.contract` already answers exactly this shape, one level up, by publishing
`VectorSearch` beside `NodeStore` rather than folding search into the base. The same answer applies
here, and the constant below records the Protocol it would take and what would trigger writing it —
which is deliberately **not now**, because nothing consumes it. `docs/internal/lessons.md` `L11.29`.
"""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, ClassVar, NewType, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import ServiceRole
from weft_kernel.payload import NodeId

#: Fitness function 6's subject for this contract — see the module docstring. Deliberately its
#: own constant rather than a move of `weft_store.contract.STORE_CONTRACT_VERSION`: this Protocol
#: is not a member of the store family unless and until it is promoted into it, which is that
#: constant's own deferral row, not this task.
#:
#: **It versions the whole family this module publishes, not one Protocol** —
#: `STORE_CONTRACT_VERSION`'s own arrangement, where one constant is assigned to `NodeStore` and
#: to each of the six capabilities beside it. The name is `GraphTraversal`'s because that Protocol
#: anchors the family, exactly as `NodeStore` anchors the store's.
#:
#: **`1.0.0` → `2.0.0` at ledger task 11.5, and it is a break for callers rather than for
#: implementers.** `nearest_entities` left `GraphTraversal` for `EntityVectorSearch` below. Under
#: G9's two-audience rule that is *additive* for an implementer — a class that still has the method
#: satisfies both Protocols — and **breaking for a caller**, because `ctx.require(GraphTraversal)`
#: no longer answers something with a `nearest_entities` on it. The louder of the two audiences
#: decides, so: major.
GRAPH_TRAVERSAL_CONTRACT_VERSION = "2.0.0"

#: A resolved entity's identity — a `NewType` over `str`, the same shape
#: `weft_kernel.payload.ids.NodeId` takes for a node, and deliberately not a content digest: see
#: the module docstring's note on `S12`.
EntityId = NewType("EntityId", str)


class Entity(BaseModel):
    """One resolved entity — a name a caller can ask a graph about, and the id that names it.

    Exactly two fields, deliberately: a contract states what a caller gets, and task `11.8`
    designs the table an entity is actually stored in one task later, free to add columns this
    contract never has to know about. `name` refuses blank — a nameless entity is one no question
    in this Protocol can ask for by name, which is the member it leads with.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: EntityId
    name: str = Field(min_length=1)


@runtime_checkable
class GraphTraversal(Protocol):
    """A bounded walk over resolved entities and the nodes and neighbours around them.

    Not a `Stage` — see the module docstring. Reached through `ctx.require`, never run as a
    pipeline rung, so it carries no `run` and no `Stage[In, Out]` base.

    Three members, every one `async def` and every one at batch granularity: a caller asking about
    several names, several entity ids, or several hops gets one answer for all of them, never one
    round trip per element. Ranking entities by a vector is `EntityVectorSearch`'s, below — a
    capability a graph backend may or may not also have, never a member this one requires.
    """

    if TYPE_CHECKING:
        #: See the module docstring — declared only for a type checker, assigned for real after
        #: the class body, so it never joins `__protocol_attrs__`.
        version: ClassVar[str]

    async def entities_by_name(self, names: Sequence[str]) -> tuple[Entity, ...]: ...

    async def nodes_for_entities(
        self, entity_ids: Sequence[EntityId]
    ) -> Mapping[EntityId, tuple[NodeId, ...]]: ...

    async def neighbourhood(
        self, entity_ids: Sequence[EntityId], *, hops: int
    ) -> Mapping[EntityId, tuple[Entity, ...]]: ...


GraphTraversal.version = GRAPH_TRAVERSAL_CONTRACT_VERSION


#: **`nearest_entities` is not published, and that is the decision rather than the omission.**
#: Ledger `11.4` fixed four members and `11.5` removed the fourth. It belongs on a Protocol of its
#: own — `EntityVectorSearch`, beside this one, exactly as `weft_store.contract` publishes
#: `VectorSearch` beside `NodeStore` rather than folding search into the base — and that Protocol is
#: **not written yet**, because nothing consumes it. `11.10`'s walk is *name → entities →
#: neighbourhood → nodes* and never starts from a vector, so publishing the capability now would be
#: a producing side with no consuming side, which is `docs/internal/lessons.md` `L5.15`'s shape and
#: the rule this project has paid for five times. **The trigger**: the first task that needs an
#: entity ranked by an embedding writes `EntityVectorSearch` then, `@runtime_checkable`, carrying
#: `GRAPH_TRAVERSAL_CONTRACT_VERSION` like every member of this family, with one member —
#: `async def nearest_entities(self, vector: Vector, *, limit: int) -> tuple[Entity, ...]` — and
#: never embedding for itself (G4). It is additive for a caller and additive for an implementer, so
#: a **minor** when it lands. Recorded here rather than left implicit because the reason it is
#: absent is not that nobody thought of it: `docs/internal/lessons.md` `L11.29` is the measurement
#: that removed it.

#: Selectable without a kernel line — see the module docstring's note on ledger task `9.0`'s
#: form. A plain module-level constant beside the Protocol, never a `ClassVar` on it: placed in
#: the body it would join `__protocol_attrs__` and become a *required* structural member.
GRAPH_ROLE = ServiceRole(key="graph", contract=GraphTraversal)

__all__ = [
    "GRAPH_ROLE",
    "GRAPH_TRAVERSAL_CONTRACT_VERSION",
    "Entity",
    "EntityId",
    "GraphTraversal",
]
