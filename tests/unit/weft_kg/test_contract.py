"""`weft_kg` publishes a graph traversal contract — ledger task **11.4**.

`S12` settled that the traversal contract ships from **the pack that owns the capability**, not
from `weft-store`, and that family membership is deferred behind a named trigger rather than
assumed. `02` §1 → *Who publishes a contract* is the rule it follows: the kernel publishes the
contract *mechanism* and no capability contract of its own, and "a pack depends on the pack that
publishes the contract it implements, exactly as it would on any third-party protocol."

**Not a `Stage`, and the tree already fixes what that means.** `weft_store.contract.VectorSearch`
states the rule in its own docstring — *"nothing in an ingest pipeline calls `search_vector`, and a
future `Retriever` resolves this capability directly against the configured store rather than
through the runner's stage machinery."* Traversal is the same shape: it is reached through
`ctx.require`, never run as a rung, so it declares no `Stage[In, Out]` and the runner never reads
`__orig_bases__` off it.

**`version` is declared the way `weft_extract.contract` argues for and every contract in this tree
copies** — under `if TYPE_CHECKING:` inside the body, assigned for real after the class statement
closes. Written directly in the body it would join `__protocol_attrs__` and become a *required*
`isinstance` member, so a stranger implementing all four methods and never restating `version`
would fail a capability check that has nothing to do with capability.

**Selectable through one constant beside the Protocol**, never a `ClassVar` on it, which is the
form task `9.0` fixed and the same reason: `weft_kernel.context.ServiceRole` carries `contract` as a
bare `type`, so the kernel names no capability and `[services] graph` selects one without a kernel
line.

---

**Three decisions this file makes, because the tree makes none of them.**

*One.* **`EntityId` and `Entity` are invented here.** Measured before writing: `EntityId` appears
nowhere in the tree, `weft_kg` does not exist, and the only `Entity` is
`examples/weft-example-graph/src/weft_example_graph/payload.py`'s — whose own docstring calls it
"one entity **mention** … in a single node's content", a mention rather than a resolved identity.
So this task fixes the type its four members return.

*Two.* **It is deliberately two fields.** `S12`: entities are pack rows "because an identity a merge
revises cannot carry a content-digest id", and `11.8` adds that "the canonical id is a function of
the set, not of arrival order". Both constrain how an id is *computed* and where a row is *kept* —
neither names a field. A contract says what a caller gets; the table says how it is stored, and
`11.8` designs that table one task later. Two fields is what traversal needs to answer with and is
the largest surface `11.8` cannot be forced to change: it may add columns freely.

*Three.* **"entities in nodes" is read as the entity↔node relation in the direction retrieval
walks it**, and named `nodes_for_entities` for that reason. `11.10` needs *name → entities →
neighbourhood → nodes*, so a member returning node ids is what closes that loop; a members list
that only ever went nodes→entities would leave `11.10` unbuildable. The tree's only prior art agrees
— `examples/weft-example-graph/src/weft_example_graph/store.py:526` is
`node_ids_for_entities(names)`. Recorded rather than assumed, because the ledger's phrase admits
both readings and only one of them can be built on.
"""

from collections.abc import Mapping, Sequence

import pytest
from pydantic import ValidationError

from weft_kernel.context import ServiceRole
from weft_kernel.payload import NodeId, Vector
from weft_kernel.runner import Stage
from weft_kg.contract import (
    GRAPH_ROLE,
    GRAPH_TRAVERSAL_CONTRACT_VERSION,
    Entity,
    EntityId,
    GraphTraversal,
)


class _Stranger:
    """A traversal implementation that imports none of the Protocol, the way a third party's
    would — the shape `weft_example_graph.store` takes for `NodeStore` and the shape fitness
    function 9(c) asks of a stranger."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def entities_by_name(self, names: Sequence[str]) -> tuple[Entity, ...]:
        self.asked.append("entities_by_name")
        return tuple(Entity(id=EntityId(f"e:{n}"), name=n) for n in names)

    async def nodes_for_entities(
        self, entity_ids: Sequence[EntityId]
    ) -> Mapping[EntityId, tuple[NodeId, ...]]:
        self.asked.append("nodes_for_entities")
        return {eid: (NodeId(f"n:{eid}"),) for eid in entity_ids}

    async def nearest_entities(self, vector: Vector, *, limit: int) -> tuple[Entity, ...]:
        self.asked.append("nearest_entities")
        del vector
        return tuple(Entity(id=EntityId(f"v{i}"), name=f"near-{i}") for i in range(limit))

    async def neighbourhood(
        self, entity_ids: Sequence[EntityId], *, hops: int
    ) -> Mapping[EntityId, tuple[Entity, ...]]:
        self.asked.append("neighbourhood")
        return {
            eid: (Entity(id=EntityId(f"{eid}+{hops}"), name="neighbour"),) for eid in entity_ids
        }


def test_a_class_that_never_imported_the_protocol_satisfies_it() -> None:
    """Structural satisfaction, which is the whole of what `@runtime_checkable` buys here and
    what fitness function 9(c)'s stranger will be asked."""
    # Act / Assert
    assert isinstance(_Stranger(), GraphTraversal)


def test_a_class_missing_one_member_does_not_satisfy_it() -> None:
    """The floor. A Protocol every object satisfies would make the test above vacuous."""

    # Arrange — three of the four.
    class _Partial:
        async def entities_by_name(self, names: Sequence[str]) -> tuple[Entity, ...]:
            del names
            return ()

        async def nodes_for_entities(
            self, entity_ids: Sequence[EntityId]
        ) -> Mapping[EntityId, tuple[NodeId, ...]]:
            del entity_ids
            return {}

        async def nearest_entities(self, vector: Vector, *, limit: int) -> tuple[Entity, ...]:
            del vector, limit
            return ()

    # Act / Assert
    assert not isinstance(_Partial(), GraphTraversal)


def test_the_contract_is_not_a_stage_where_an_extractor_is() -> None:
    """`VectorSearch`'s own rule, applied: traversal is reached through `ctx.require`, never run
    as a pipeline rung, so the runner must never be able to read `In`/`Out` off it.

    **Asked of the MRO, not with `issubclass`, and contrasted against a contract that *is* a
    `Stage`.** `weft_kernel.runner.Stage` is not `@runtime_checkable`, so `issubclass(x, Stage)`
    raises `TypeError` for every `x` — including `Extractor`, which really does inherit it. An
    assertion that raises identically whatever it is handed is not an assertion. `Extractor` on the
    other side is what makes this non-vacuous: the two answers differ, so the check can fail.
    """
    # Arrange — `getattr` with a default is this tree's settled way to read a Protocol's own
    # dunders under a type checker. The precedent is `weft_chunk`'s own
    # `test_chunker_publishes_a_property_vocabulary`, which has read `__protocol_attrs__` that
    # way since Phase 1 — named by its function rather than by a `path:line`, because a line
    # number in a file called `test_contract.py`, cited from a file also called
    # `test_contract.py`, is the ambiguous pointer fitness function 17 clause (b) refuses.
    from weft_extract.contract import Extractor

    # Act
    stage_bases = getattr(Extractor, "__mro__", ())
    traversal_bases = getattr(GraphTraversal, "__mro__", ())

    # Assert
    assert Stage in stage_bases
    assert Stage not in traversal_bases


def test_the_version_is_readable_off_the_class_and_carries_no_isinstance_weight() -> None:
    """Both halves of `weft_extract.contract`'s argument, asserted separately.

    Readable off the class is what the generated contract reference needs. Carrying no
    `isinstance` weight is what lets `_Stranger` — which never restates `version` — satisfy the
    Protocol at all, and it is the half that a `ClassVar` in the body would silently break.
    """
    # Act / Assert
    protocol_attrs = getattr(GraphTraversal, "__protocol_attrs__", frozenset[str]())
    assert GraphTraversal.version == GRAPH_TRAVERSAL_CONTRACT_VERSION
    assert "version" not in protocol_attrs
    assert not hasattr(_Stranger(), "version")
    assert isinstance(_Stranger(), GraphTraversal)


def test_the_contract_version_is_its_own_and_moves_nothing_in_the_store_family() -> None:
    """`11.4`'s line: `STORE_CONTRACT_VERSION` does **not** move when this Protocol is published.
    It moves if the Protocol is ever *promoted* into the family, which is the deferral row's own
    trigger and not this task."""
    # Arrange
    from weft_store.contract import STORE_CONTRACT_VERSION

    # Act / Assert
    assert GRAPH_TRAVERSAL_CONTRACT_VERSION == "1.0.0"
    assert STORE_CONTRACT_VERSION == "2.3.0"


def test_the_pack_declares_the_protocol_selectable_without_a_kernel_line() -> None:
    """Task `9.0`'s form: one `ServiceRole` constant beside the Protocol, its `contract` field a
    bare `type` the kernel never names — so `[services] graph` selects a traversal implementation
    with nothing added to `weft-kernel`."""
    # Act / Assert
    assert isinstance(GRAPH_ROLE, ServiceRole)
    assert GRAPH_ROLE.key == "graph"
    assert GRAPH_ROLE.contract is GraphTraversal


def test_the_role_is_a_module_constant_and_not_an_attribute_of_the_protocol() -> None:
    """The reason `9.0` fixed that form: an attribute on the body joins `__protocol_attrs__` and
    breaks `issubclass` for every implementer that does not restate it."""
    # Act / Assert
    protocol_attrs = getattr(GraphTraversal, "__protocol_attrs__", frozenset[str]())
    assert not hasattr(GraphTraversal, "role")
    assert "role" not in protocol_attrs


def test_an_entity_is_frozen_and_refuses_a_blank_name() -> None:
    """A domain object, so frozen — a merge produces a new entity rather than editing one, which
    is `S12`'s own reason these are rows and not `Node`s. And a nameless entity is one no question
    can ask for by name, which is the member this contract leads with."""
    # Act / Assert
    assert Entity.model_config.get("frozen") is True
    assert Entity.model_config.get("extra") == "forbid"
    with pytest.raises(ValidationError):
        Entity(id=EntityId("e2"), name="")


async def test_the_four_members_answer_in_batch() -> None:
    """Batch granularity is the ledger's word and it is the property that keeps a bounded walk
    from becoming N round trips — `weft_example_graph.store.neighbors_of` takes a single name,
    which is exactly what this contract must not do."""
    # Arrange — deliberately *not* annotated `GraphTraversal`. The `if TYPE_CHECKING: version`
    # declaration makes `version` a member a type checker requires for assignability while
    # `__protocol_attrs__` correctly excludes it at runtime, so annotating a stranger with the
    # Protocol is a static error on every contract in this tree, not something about this one.
    # The runtime satisfaction this file is actually about is asserted by `isinstance` above.
    traversal = _Stranger()
    names = ["mRMR", "RRF"]

    # Act
    entities = await traversal.entities_by_name(names)
    nodes = await traversal.nodes_for_entities([e.id for e in entities])
    neighbours = await traversal.neighbourhood([e.id for e in entities], hops=2)
    nearest = await traversal.nearest_entities(Vector(values=(0.1, 0.2)), limit=3)

    # Assert — every member answered for *all* of its inputs, not the first.
    assert [e.name for e in entities] == names
    assert set(nodes) == {e.id for e in entities}
    assert set(neighbours) == {e.id for e in entities}
    assert len(nearest) == 3
