"""`weft_kg`'s store and its traversal, against the real Postgres container. Ledger task **11.5**.

Mirrors `packages/weft-rag/src/weft_kg/store.py` and `weft_kg/traversal.py`. Per
`docs/06-phase-0-build.md` step 8, an integration test runs against the real container and is
**skipped with a reason** when it is absent, never silently passed. The form is a module-level
`pytestmark` computed once from a synchronous probe — `tests/integration/test_store_conformance.py`
and `examples/weft-example-graph/tests/test_store.py` both use it, and it is the right one here
because *every* test in this module needs the container. The ones that do not have been moved to
`test_register.py`, which has no container dependency at all, rather than left here to be skipped
along with the rest and quietly stop reporting.

**One container is still one, and the operator says so in one line.** `[packs.graph] dsn` takes a
DSN like any other setting, and the fixture below hands it the same `WEFT_DATABASE_URL` a project
would write as `[packs.graph] dsn = "${env:WEFT_DATABASE_URL}"`. The ledger asked for that offer to
be *ambient* — extended from the one `weft_cli.registry_bootstrap.pack_settings_from_environment`
already makes to `store` — and that turned out to mean `weft_cli` naming this pack in a hard-coded
literal, which is the anticipation Phase 11 exists to prove unnecessary. Settled with the owner
2026-09-09: the pack costs **zero lines outside itself**, and the one line an operator writes is
the line `GraphDsnNotConfiguredError` already prints. The tables are its own — `kg_nodes`,
`kg_sources`, `kg_entities`,
`kg_entity_nodes`, `kg_relations` — because a `NodeStore` backend owns its schema, which is the
footing the Phase 11 preamble's narrowing of G15 puts entity rows on: *"not rows a stage persists
outside the node model, but a `NodeStore` backend's own internal schema"*.

**What this task's entity tables are, and what they are not.** They are the minimum the
traversal members answer over, and **task `11.8` owns their design** — aliases, canonical ids, a
version row. Nothing here should be read as fixing that shape; `Entity` is deliberately two fields
(`11.4`) so that `11.8` stays free, and the schema below is the smallest thing that can hold two
fields and the edges between them. **Nothing writes these rows yet**: `11.6` and `11.7` are the
tasks that produce entities, so the tests below seed them through the same public store the
producers will, and the traversal's first real consumer is `11.10`.

**Three traversal semantics decided here, from the documents, because the contract admits more than
one reading and only one can be built on.** *(i)* `nodes_for_entities` keys the mapping on exactly
the requested ids **the store holds a row for** — an id it does not hold is absent, never a key with
an empty tuple, because `docs/internal/lessons.md` L5.9's rule is that an empty collection means "I
did not find it" and a caller must be able to tell that from "found it, it has nothing". *(ii)*
`neighbourhood` walks relations **undirected**: a relation is stored with a direction because it has
one, but *"the neighbourhood of an entity"* is a question about reach, and a retrieval walk that
could only travel one way would miss the half of the graph pointing at its seed. The seed is
excluded from its own neighbourhood.

**A third semantic was decided here and then removed.** `nearest_entities` ranked entities by
cosine distance, and the first out-of-tree implementation — a graph over ordinary tables with no
vector column in it — could satisfy the other members honestly and that one not at all. It moves to
an `EntityVectorSearch` Protocol of its own, on `weft_store.contract`'s own precedent for
`VectorSearch` beside `NodeStore`, and that Protocol is **not written yet** because nothing consumes
it. `weft_kg.contract` records what it takes and what triggers writing it; `L11.29`.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping

import psycopg
import pytest
from pydantic import SecretStr

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_kg.contract import EntityId
from weft_kg.payload import (
    CooccurrenceEdge,
    CooccurrenceGraph,
    EntityMention,
    ExtractedFact,
    MentionedEntity,
)
from weft_kg.store import (
    KG_SCHEMA_VERSION,
    GraphSchemaVersionRefusedError,
    GraphSettings,
    GraphStore,
)
from weft_kg.traversal import GraphWalk
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_store.contract import ReconcileMode

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _unreachable_reason() -> str | None:
    """The reason the container cannot answer, or `None` — read once, at import."""
    try:
        conn = psycopg.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`."
    conn.close()
    return None


_UNREACHABLE = _unreachable_reason()
pytestmark = pytest.mark.skipif(_UNREACHABLE is not None, reason=_UNREACHABLE or "")


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str, *, source: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="weft_kg's own store test",
        sources=frozenset({SourceId(source)}),
    )


@pytest.fixture
async def store() -> AsyncIterator[GraphStore]:
    """A `GraphStore` against a truncated schema."""
    instance = GraphStore(GraphSettings(dsn=SecretStr(_DSN)))
    await instance.count()  # forces schema creation through the public API
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE kg_nodes, kg_sources, kg_entities CASCADE")
    await conn.close()
    yield instance
    await instance.aclose()


@pytest.fixture
async def walk(store: GraphStore) -> AsyncIterator[GraphWalk]:
    """A `GraphWalk` over the same schema the `store` fixture just truncated."""
    del store
    instance = GraphWalk(GraphSettings(dsn=SecretStr(_DSN)))
    yield instance
    await instance.aclose()


async def _entity_of(walk: GraphWalk, name: str) -> EntityId:
    """The canonical entity a surface form resolves to — the id `GraphTraversal` speaks in.

    Added at `11.8`, when `put_entity` began returning an **alias** id: `kg_entity_nodes` and
    `kg_relations` key on the alias so that re-pointing one moves its evidence in a single
    `UPDATE`, which is what `11.9`'s bridge-merge is. The two ids were the same thing until this
    task split them, and the tests below that pass an id to `neighbourhood` or
    `nodes_for_entities` want the canonical one, because that is what the contract's own members
    take.
    """
    [entity] = await walk.entities_by_name([name])
    return entity.id


async def test_a_node_round_trips_through_add_and_get(store: GraphStore) -> None:
    # Arrange
    node = _node("Reciprocal rank fusion merges ranked lists.", source="doc-a")

    # Act
    await store.add([node])
    [read] = await store.get([node.id])

    # Assert — the fact a store means: what went in comes back, lineage included.
    assert read.content == node.content
    assert read.lineage.sources == node.lineage.sources
    assert await store.count() == 1


async def test_deleting_a_source_removes_its_nodes_and_reports_the_count(
    store: GraphStore,
) -> None:
    # Arrange
    await store.add([_node("one", source="doc-a"), _node("two", source="doc-a")])
    await store.add([_node("three", source="doc-b")])

    # Act
    removed = await store.delete_source(SourceId("doc-a"))

    # Assert
    assert removed.source_id == SourceId("doc-a")
    assert removed.node_count == 2
    assert await store.count() == 1


async def test_a_reconcile_pass_reports_what_it_examined(store: GraphStore) -> None:
    """`repair` over an intact graph examines what is there and removes nothing — the honest
    answer, and the one the automatic post-index pass gets on a fresh corpus.
    """
    # Arrange
    await store.add([_node("one", source="doc-a")])

    # Act
    report = await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert
    assert report.mode is ReconcileMode.REPAIR
    assert report.removed == 0


async def test_entities_are_found_by_name(store: GraphStore, walk: GraphWalk) -> None:
    # Arrange
    node = _node("Chucri and Azouz wrote about adRAP.", source="doc-a")
    await store.add([node])
    await store.put_entity(name="Chucri", nodes=[node.id])
    await store.put_entity(name="Azouz", nodes=[node.id])

    # Act
    found = await walk.entities_by_name(["Chucri", "nobody-by-that-name"])

    # Assert — the name that exists comes back, the one that does not simply is not there.
    assert [entity.name for entity in found] == ["Chucri"]
    # Two aliases nothing has merged are two entities. Asserted against `Azouz` rather than
    # against an id this test computed, because `_entity_of` asks `entities_by_name` — the
    # function under test — so comparing the two would be one source on both sides of a
    # comparison that then cannot disagree (`docs/internal/lessons.md` L5.6).
    [azouz] = await walk.entities_by_name(["Azouz"])
    assert found[0].id != azouz.id


async def test_nodes_for_entities_omits_an_id_the_store_does_not_hold(
    store: GraphStore, walk: GraphWalk
) -> None:
    """Semantics (i) in the module docstring: absent, never a key with an empty tuple.

    A caller has to be able to tell *"no such entity"* from *"that entity, and it has no
    nodes"*, and a mapping that answers `()` for both has thrown that away — `L5.9`.
    """
    # Arrange
    node = _node("Chucri and Azouz wrote about adRAP.", source="doc-a")
    await store.add([node])
    await store.put_entity(name="Chucri", nodes=[node.id])
    chucri = await _entity_of(walk, "Chucri")

    # Act
    found = await walk.nodes_for_entities([chucri, EntityId("never-stored")])

    # Assert
    assert set(found) == {chucri}
    assert found[chucri] == (node.id,)


async def test_the_neighbourhood_walks_relations_in_both_directions(
    store: GraphStore, walk: GraphWalk
) -> None:
    """Semantics (ii): a relation has a direction and *reach* does not.

    `a -> b -> c` is stored forwards; asked for `b`'s neighbourhood at one hop, a walk that
    only travelled forwards would answer `c` alone and lose the half of the graph pointing at
    its own seed, which for retrieval is the half that says why `b` matters.
    """
    # Arrange
    node = _node("a relates to b relates to c", source="doc-a")
    await store.add([node])
    a = await store.put_entity(name="a", nodes=[node.id])
    b = await store.put_entity(name="b", nodes=[node.id])
    c = await store.put_entity(name="c", nodes=[node.id])
    await store.put_relation(source=a, target=b, predicate="relates-to")
    await store.put_relation(source=b, target=c, predicate="relates-to")
    seed_a, seed_b = await _entity_of(walk, "a"), await _entity_of(walk, "b")

    # Act
    one_hop = await walk.neighbourhood([seed_b], hops=1)
    two_hops = await walk.neighbourhood([seed_a], hops=2)

    # Assert — both neighbours at one hop, and the seed is never in its own neighbourhood.
    assert {entity.name for entity in one_hop[seed_b]} == {"a", "c"}
    assert {entity.name for entity in two_hops[seed_a]} == {"b", "c"}


async def test_the_neighbourhood_is_bounded_by_hops(store: GraphStore, walk: GraphWalk) -> None:
    """The bound is the whole point — an unbounded walk over a real corpus returns the corpus."""
    # Arrange
    node = _node("a relates to b relates to c", source="doc-a")
    await store.add([node])
    a = await store.put_entity(name="a", nodes=[node.id])
    b = await store.put_entity(name="b", nodes=[node.id])
    c = await store.put_entity(name="c", nodes=[node.id])
    await store.put_relation(source=a, target=b, predicate="relates-to")
    await store.put_relation(source=b, target=c, predicate="relates-to")
    seed = await _entity_of(walk, "a")

    # Act
    one_hop = await walk.neighbourhood([seed], hops=1)

    # Assert
    assert {entity.name for entity in one_hop[seed]} == {"b"}


async def test_an_entity_can_carry_a_vector_the_traversal_does_not_yet_read(
    store: GraphStore,
) -> None:
    """`kg_entities.embedding` exists and `put_entity` fills it, and **nothing reads it yet**.

    That is deliberate and it is the one place in this task where a column outlives its reader
    on purpose. `01` → Phase 11: *"Entity-name vectors, where a rung wants them, are written by
    the pipeline's embedder and only held by the store"* — `11.6` is that rung, one task away.
    What was removed instead is `GraphWalk.nearest_entities`: ranking entities by an embedding
    belongs on an `EntityVectorSearch` Protocol of its own, which is recorded in
    `weft_kg.contract` and deliberately unwritten because nothing consumes it (`L11.29`,
    `L5.15`). An unused column has its writer one task away; an unreachable method would have
    had neither a contract declaring it nor a caller reaching it.
    """
    # Arrange
    node = _node("vectors", source="doc-a")
    await store.add([node])

    # Act — the write path exists and round-trips, which is what `11.6` will depend on.
    embedded = await store.put_entity(
        name="near", nodes=[node.id], embedding=Vector(values=(1.0, 0.0, 0.0))
    )
    plain = await store.put_entity(name="unembedded", nodes=[node.id])

    # Assert — both are entities; the vector is held, not surfaced.
    assert embedded != plain
    assert not hasattr(GraphWalk, "nearest_entities")


async def test_an_entity_row_dies_with_the_nodes_that_supported_it(
    store: GraphStore, walk: GraphWalk
) -> None:
    """The Phase 11 preamble's narrowing of G15 rests on exactly this: entity rows are a
    backend's internal schema *"cascading from mention node ids, so no row outlives the nodes
    that support it"*. If that were untrue they would be durable state outside the node model,
    which G15's *"no rows that are not nodes"* forbids.
    """
    # Arrange
    node = _node("Chucri wrote about adRAP.", source="doc-a")
    await store.add([node])
    await store.put_entity(name="Chucri", nodes=[node.id])
    chucri = await _entity_of(walk, "Chucri")

    # Act
    await store.delete_source(SourceId("doc-a"))

    # Assert
    assert await walk.entities_by_name(["Chucri"]) == ()
    assert await walk.nodes_for_entities([chucri]) == {}


async def test_node_ids_come_back_ready_for_the_corpus(store: GraphStore, walk: GraphWalk) -> None:
    """`nodes_for_entities` answers with the same `NodeId` a caller would hand `NodeStore.get`.

    `11.10` walks *name → entities → neighbourhood → nodes* and then reads those nodes out of
    the corpus, so an id that did not resolve there would break that walk at its last step —
    which is why this asserts the round trip rather than the type.
    """
    # Arrange
    node = _node("Chucri wrote about adRAP.", source="doc-a")
    await store.add([node])
    await store.put_entity(name="Chucri", nodes=[node.id])
    chucri = await _entity_of(walk, "Chucri")

    # Act
    found = await walk.nodes_for_entities([chucri])
    [read] = await store.get(list(found[chucri]))

    # Assert
    assert found[chucri] == (NodeId(str(node.id)),)
    assert read.id == node.id


async def test_storing_a_node_derives_its_entity_and_relation_rows(
    store: GraphStore, walk: GraphWalk
) -> None:
    """**Ledger `11.6`'s other half, and the seam that keeps the enhancer store-free.**

    `cooccurrence-graph` attaches ext data and writes no rows; `add` reads that ext and derives
    them. That split is what lets the stage run in a pipeline with no graph store configured —
    it attaches a fact nothing reads — and it is why no index-path stage in this pack ever needs
    `ctx.require(NodeStore)`, which is the access G15 and G16 spent a session settling.
    """
    # Arrange
    node = _node("Chucri and Azouz wrote about adRAP.", source="doc-a").with_ext(
        CooccurrenceGraph(
            entities=(EntityMention(name="Chucri"), EntityMention(name="Azouz")),
            relations=(CooccurrenceEdge(source="Azouz", target="Chucri"),),
        )
    )

    # Act — the ordinary store call a pipeline's `store` stage makes, nothing else.
    await store.add([node])

    # Assert — both names are entities the walk can find, and they are neighbours.
    found = await walk.entities_by_name(["Chucri", "Azouz"])
    assert {entity.name for entity in found} == {"Chucri", "Azouz"}
    [chucri] = [entity for entity in found if entity.name == "Chucri"]
    neighbours = await walk.neighbourhood([chucri.id], hops=1)
    assert {entity.name for entity in neighbours[chucri.id]} == {"Azouz"}
    assert (await walk.nodes_for_entities([chucri.id]))[chucri.id] == (node.id,)


async def test_a_node_carrying_no_graph_ext_derives_no_rows(
    store: GraphStore, walk: GraphWalk
) -> None:
    """A pipeline with the graph store and no enhancer stores nodes and builds no graph.

    That is the honest outcome rather than a failure: `index-with-graph` is a real rung on its
    own, and a store that refused a node without this pack's ext would make its own optional
    stage mandatory.
    """
    # Arrange / Act
    await store.add([_node("Chucri wrote about adRAP.", source="doc-a")])

    # Assert
    assert await store.count() == 1
    assert await walk.entities_by_name(["Chucri"]) == ()


# --- ledger task 11.7: the model-extracted rung's own rows --------------------------------


async def test_storing_a_mention_node_derives_the_entity_row_it_anchors(
    store: GraphStore, walk: GraphWalk
) -> None:
    """`11.6`'s split, applied to `llm-facts`: the stage attaches ext, `add` writes the rows.

    A mention node is what an entity row hangs off — `11.8` cascades its entity and alias tables
    from mention node ids — so the anchoring is asserted through `nodes_for_entities` rather than
    through the entity's mere existence: an entity with no node behind it is one no deletion can
    ever reach.
    """
    # Arrange
    mention = _node("Chucri", source="doc-a").with_ext(
        MentionedEntity(name="Chucri", entity_type="person")
    )

    # Act — the ordinary store call a pipeline's `store` stage makes, nothing else.
    await store.add([mention])

    # Assert
    [entity] = await walk.entities_by_name(["Chucri"])
    assert (await walk.nodes_for_entities([entity.id]))[entity.id] == (mention.id,)


async def test_storing_a_fact_node_derives_the_relation_between_its_two_entities(
    store: GraphStore, walk: GraphWalk
) -> None:
    """The edge a model-extracted fact contributes, walkable by the traversal `11.10` uses.

    The predicate is the model's own word rather than `co-occurs-with`, which is the whole
    difference between this rung and `index-with-cooccurrence`: a co-occurrence edge says two
    names shared a chunk, and this one says what the text claimed about them.
    """
    # Arrange
    fact = _node("Chucri wrote adRAP", source="doc-a").with_ext(
        ExtractedFact(
            source="Chucri",
            source_type="person",
            predicate="wrote",
            target="adRAP",
            target_type="method",
        )
    )

    # Act
    await store.add([fact])

    # Assert — both endpoints exist and each reaches the other, the walk being undirected.
    found = await walk.entities_by_name(["Chucri", "adRAP"])
    assert {entity.name for entity in found} == {"Chucri", "adRAP"}
    [chucri] = [entity for entity in found if entity.name == "Chucri"]
    neighbours = await walk.neighbourhood([chucri.id], hops=1)
    assert {entity.name for entity in neighbours[chucri.id]} == {"adRAP"}


async def test_an_entity_a_fact_named_dies_with_the_fact_node(
    store: GraphStore, walk: GraphWalk
) -> None:
    """The G15 narrowing this pack stands on: no row outlives the nodes that support it.

    Asserted for the fact path as well as the co-occurrence one, because the two reach
    `put_entity` by different routes and only the call sites say whether both attach.
    """
    # Arrange
    fact = _node("Chucri wrote adRAP", source="doc-b").with_ext(
        ExtractedFact(
            source="Chucri",
            source_type="person",
            predicate="wrote",
            target="adRAP",
            target_type="method",
        )
    )
    await store.add([fact])
    assert await walk.entities_by_name(["Chucri"]) != ()

    # Act
    await store.delete_source(SourceId("doc-b"))

    # Assert
    assert await walk.entities_by_name(["Chucri", "adRAP"]) == ()


# --- ledger task 11.8: aliases, canonical entities, and a schema that says which it is -----


async def test_a_surface_form_is_an_alias_and_an_entity_is_what_aliases_point_at(
    store: GraphStore, walk: GraphWalk
) -> None:
    """The table split `11.8` asks for, asserted through the traversal rather than the tables.

    Before any resolution runs every alias points at a canonical entity of its own, so the graph
    reads exactly as it did at `11.7` — which is what makes resolution an improvement to an
    existing answer rather than a precondition for having one.
    """
    # Arrange / Act
    await store.put_entity(name="Chucri", nodes=[])
    await store.put_entity(name="Azouz", nodes=[])

    # Assert
    found = await walk.entities_by_name(["Chucri", "Azouz"])
    assert {entity.name for entity in found} == {"Chucri", "Azouz"}
    assert len({entity.id for entity in found}) == 2


async def test_two_spellings_of_one_name_become_one_entity_both_are_found_by(
    store: GraphStore, walk: GraphWalk
) -> None:
    """The headline property. Both surface forms survive as aliases — the corpus said both — and
    both resolve to one canonical entity, so a question naming either reaches the same nodes.
    """
    # Arrange — two aliases a trigram score and a shared vector will merge.
    vector = Vector(values=(1.0, 0.0, 0.0, 0.0))
    await store.put_entity(name="Reciprocal Rank Fusion", nodes=[], embedding=vector)
    await store.put_entity(name="Reciprocal Rank Fusion.", nodes=[], embedding=vector)

    # Act
    report = await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert — one entity, reachable under either spelling, and the pass says what it did.
    first = await walk.entities_by_name(["Reciprocal Rank Fusion"])
    second = await walk.entities_by_name(["Reciprocal Rank Fusion."])
    assert len(first) == 1
    assert {entity.id for entity in first} == {entity.id for entity in second}
    assert report.backfilled >= 1


async def test_the_canonical_name_is_the_smallest_member_not_the_first_written(
    store: GraphStore, walk: GraphWalk
) -> None:
    """*A function of the set, not of arrival order.* Written in one order and asserted against
    the order-independent answer, so a pass that kept whichever row it saw first fails here.
    """
    # Arrange — `ADRAP` sorts before `adRAP`, and is written second.
    vector = Vector(values=(0.0, 1.0, 0.0, 0.0))
    await store.put_entity(name="adRAP", nodes=[], embedding=vector)
    await store.put_entity(name="ADRAP", nodes=[], embedding=vector)

    # Act
    await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert
    [entity] = await walk.entities_by_name(["adRAP"])
    assert entity.name == "ADRAP"


async def test_a_second_pass_changes_nothing_a_first_pass_decided(
    store: GraphStore, walk: GraphWalk
) -> None:
    """Idempotence against the database, not against the pure function — the pass runs on every
    `weft reconcile`, so a canonical id that moved would re-point every alias each time and make
    the entity's identity a fact about how often somebody ran the command.
    """
    # Arrange
    vector = Vector(values=(0.0, 0.0, 1.0, 0.0))
    await store.put_entity(name="Reciprocal Rank Fusion", nodes=[], embedding=vector)
    await store.put_entity(name="Reciprocal Rank Fusion.", nodes=[], embedding=vector)
    await store.reconcile(_ctx(), ReconcileMode.REPAIR)
    [before] = await walk.entities_by_name(["Reciprocal Rank Fusion"])

    # Act
    second = await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert
    [after] = await walk.entities_by_name(["Reciprocal Rank Fusion"])
    assert after.id == before.id
    assert after.name == before.name
    assert second.backfilled == 0, (
        "a second pass re-pointed an alias, so the canonical id is a function of how many times "
        "the pass has run rather than of the mention set"
    )


async def test_merging_two_aliases_merges_the_nodes_they_anchor(
    store: GraphStore, walk: GraphWalk
) -> None:
    """Why `kg_entity_nodes` keys on the **alias**: re-pointing the alias moves its evidence with
    it, in one `UPDATE`, and nothing is deleted. `11.9`'s bridge-merge is the same operation.
    """
    # Arrange
    first = _node("Reciprocal Rank Fusion", source="doc-a")
    second = _node("Reciprocal Rank Fusion.", source="doc-a")
    await store.add([first, second])
    vector = Vector(values=(0.0, 0.0, 0.0, 1.0))
    await store.put_entity(name="Reciprocal Rank Fusion", nodes=[first.id], embedding=vector)
    await store.put_entity(name="Reciprocal Rank Fusion.", nodes=[second.id], embedding=vector)

    # Act
    await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert — one entity, and both mention nodes hang off it.
    [entity] = await walk.entities_by_name(["Reciprocal Rank Fusion"])
    assert set((await walk.nodes_for_entities([entity.id]))[entity.id]) == {first.id, second.id}


async def test_an_edge_written_against_a_merged_alias_still_walks(
    store: GraphStore, walk: GraphWalk
) -> None:
    """Relations key on aliases too, so a merge re-points both endpoints for free. Without this
    the graph silently loses an edge the moment its endpoint is canonicalised.
    """
    # Arrange
    vector = Vector(values=(1.0, 1.0, 0.0, 0.0))
    left = await store.put_entity(name="adRAP", nodes=[], embedding=vector)
    right = await store.put_entity(name="ADRAP", nodes=[], embedding=vector)
    other = await store.put_entity(
        name="RAPTOR", nodes=[], embedding=Vector(values=(0.0, 0.0, 1.0, 1.0))
    )
    await store.put_relation(source=right, target=other, predicate="extends")
    del left

    # Act
    await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert — the edge is reachable from the canonical entity, under either spelling's name.
    [entity] = await walk.entities_by_name(["adRAP"])
    neighbours = await walk.neighbourhood([entity.id], hops=1)
    assert {found.name for found in neighbours[entity.id]} == {"RAPTOR"}


async def test_a_definition_the_corpus_stated_merges_without_any_vector(
    store: GraphStore, walk: GraphWalk
) -> None:
    """Signal 2 reaching the database. The chunk text is read from the nodes this store holds —
    the corpus is the evidence, so a pack that asked anywhere else would be guessing.

    No embedding on either alias, deliberately: this signal is exact and carries no threshold, so
    it must fire where the blended one cannot.
    """
    # Arrange — the chunk that defines the pair, stored as an ordinary node.
    await store.add(
        [_node("We use Reciprocal Rank Fusion (RRF) to merge the lists.", source="doc-a")]
    )
    await store.put_entity(name="RRF", nodes=[])
    await store.put_entity(name="Reciprocal Rank Fusion", nodes=[])

    # Act
    await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert
    [short] = await walk.entities_by_name(["RRF"])
    [long_form] = await walk.entities_by_name(["Reciprocal Rank Fusion"])
    assert short.id == long_form.id


async def test_names_the_corpus_never_equated_stay_two_entities(
    store: GraphStore, walk: GraphWalk
) -> None:
    """The floor under every assertion above, and the failure this pass is most likely to have.

    Two techniques whose names differ by one character, with vectors that disagree. A pass that
    merged them would produce a graph that is smaller, tidier and wrong — and nothing downstream
    would report it.
    """
    # Arrange
    await store.put_entity(name="adRAP", nodes=[], embedding=Vector(values=(1.0, 0.0, 0.0, 0.0)))
    await store.put_entity(name="adRAG", nodes=[], embedding=Vector(values=(0.0, 1.0, 0.0, 0.0)))

    # Act
    await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert
    first = await walk.entities_by_name(["adRAP"])
    second = await walk.entities_by_name(["adRAG"])
    assert {entity.id for entity in first} != {entity.id for entity in second}


async def test_the_pass_runs_under_repair_as_well_as_full(
    store: GraphStore, walk: GraphWalk
) -> None:
    """Settled with the owner 2026-09-09, against `ReconcileMode`'s own wording.

    That docstring calls `full` the mode that *"also backfills state that was never built"*, and
    a canonical id is state that was never built — but its own reason for the split is **consent**,
    *"because backfill runs model calls and writes"*. This pass makes no model call, so
    `ReconcileEstimate.model_calls` stays `0` and nothing is spent without asking. `11.9`'s
    model-calling half is what `full` gates, and that distinction only means something if this
    half runs more widely — including in the automatic post-index pass, which is hardcoded
    `repair`.
    """
    # Arrange
    vector = Vector(values=(1.0, 1.0, 1.0, 0.0))
    await store.put_entity(name="Reciprocal Rank Fusion", nodes=[], embedding=vector)
    await store.put_entity(name="Reciprocal Rank Fusion.", nodes=[], embedding=vector)

    # Act
    await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert
    assert len(await walk.entities_by_name(["Reciprocal Rank Fusion"])) == 1
    estimate = await store.estimate(_ctx(), ReconcileMode.REPAIR)
    assert estimate.model_calls == 0


async def test_the_schema_carries_its_own_version(store: GraphStore) -> None:
    """`S5`, per surface: a persisted schema carries a version in the stored bytes, because at
    the read site the pack that wrote it may not be the one installed.
    """
    # Assert
    assert await store.schema_version() == KG_SCHEMA_VERSION


async def test_a_schema_version_this_pack_does_not_know_is_refused(store: GraphStore) -> None:
    """Upgrade-or-refuse, and refuse is the whole of it today.

    A newer `weft-kg` writing a layout this one cannot read must not be quietly written over: the
    rows are an operator's data, and guessing at a shape means silently misreading it. The
    refusal names both versions and what to do, because an operator who cannot act on it has
    been given a crash with better manners.
    """
    # Arrange — a version from the future, written directly into the surface's own row.
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("UPDATE kg_schema SET version = %s", ("999.0.0",))
    await conn.close()

    # Act / Assert — restored in `finally`, because the `store` fixture truncates rows and this
    # test edits the one row that says how to read them: leaving it would make every later test
    # in this module depend on collection order.
    stranger = GraphStore(GraphSettings(dsn=SecretStr(_DSN)))
    try:
        with pytest.raises(GraphSchemaVersionRefusedError) as raised:
            await stranger.count()
        assert "999.0.0" in str(raised.value)
        assert KG_SCHEMA_VERSION in str(raised.value)
    finally:
        await stranger.aclose()
        conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
        async with conn.cursor() as cur:
            await cur.execute("UPDATE kg_schema SET version = %s", (KG_SCHEMA_VERSION,))
        await conn.close()


# --- ledger task 11.3: the deletion says what it actually reaped ---------------------------


async def test_deleting_a_source_reports_what_it_removed_by_kind(store: GraphStore) -> None:
    """`11.3`'s own line: a store that reaped forty of its own rows never answers with
    `node_count=0` as its whole account.

    Every non-graph half of this landed at `9.3` — `Removed.removed`, the fan-out carrying it,
    and `weft_cli.render`'s `f"{count} {kind}(s)"`. What was missing until `11.7` and `11.8` is
    that this pack had no three kinds to count: a fact and a mention became `Node`s at `11.7`,
    and an entity became a row reached through an alias at `11.8`. This is the participant's own
    half, and nothing else.

    **`fact` and `mention` are counted *beside* `node_count`, not instead of it.** Both are
    nodes, so both are already inside that total; what `removed` adds is the breakdown, which is
    the whole reason `"node"` is a reserved key — a second spelling of the total would be two
    lists that can drift, inside one model.
    """
    # Arrange — one chunk, one fact derived from it, one mention, and the rows they anchor.
    chunk = _node("Chucri wrote adRAP.", source="doc-a")
    fact = _node("Chucri wrote adRAP", source="doc-a").with_ext(
        ExtractedFact(
            source="Chucri",
            source_type="person",
            predicate="wrote",
            target="adRAP",
            target_type="method",
        )
    )
    mention = _node("Chucri", source="doc-a").with_ext(
        MentionedEntity(name="Chucri", entity_type="person")
    )
    await store.add([chunk, fact, mention])

    # Act
    removed = await store.delete_source(SourceId("doc-a"))

    # Assert — the total, and the account of it.
    assert removed.node_count == 3
    assert removed.removed["fact"] == 1
    assert removed.removed["mention"] == 1
    assert removed.removed["entity"] == 2, "both endpoints of the fact were entities"
    assert removed.removed["relation"] == 1
    assert "node" not in removed.removed


async def test_a_source_with_nothing_of_this_pack_s_own_reports_no_kinds(
    store: GraphStore,
) -> None:
    """An empty account is a fact, and it must be *empty* rather than zeroed.

    A participant reporting `fact: 0, mention: 0, entity: 0` says *"I looked and found none"* in
    a shape indistinguishable from *"I do not count these"* once a reader is scanning a column of
    numbers. Absent kinds are how `Removed`'s own open vocabulary says nothing of that kind was
    there — `docs/internal/lessons.md` L5.9, one model over.
    """
    # Arrange — an ordinary chunk carrying none of this pack's ext.
    await store.add([_node("nothing derived from this", source="doc-b")])

    # Act
    removed = await store.delete_source(SourceId("doc-b"))

    # Assert
    assert removed.node_count == 1
    assert removed.removed == {}


async def test_the_counts_are_of_rows_this_deletion_actually_removed(store: GraphStore) -> None:
    """Counted against what went, not against what the table held.

    Two sources, one deleted: a count taken as *"how many entity rows are gone from the table"*
    would be right here by accident and wrong the moment a second source shared an entity, which
    is the ordinary case in any real corpus. So the arrangement is exactly that — `Chucri` is
    mentioned by both sources and survives the first deletion.
    """
    # Arrange
    shared_a = _node("Chucri", source="doc-a").with_ext(
        MentionedEntity(name="Chucri", entity_type="person")
    )
    shared_b = _node("Chucri.", source="doc-b").with_ext(
        MentionedEntity(name="Chucri", entity_type="person")
    )
    only_b = _node("Azouz", source="doc-b").with_ext(
        MentionedEntity(name="Azouz", entity_type="person")
    )
    await store.add([shared_a, shared_b, only_b])

    # Act — `doc-a` goes; `Chucri` is still supported by `doc-b`'s own mention node.
    removed = await store.delete_source(SourceId("doc-a"))

    # Assert — one mention node, and no entity, because none was orphaned.
    assert removed.node_count == 1
    assert removed.removed["mention"] == 1
    assert "entity" not in removed.removed


# --- ledger task 11.9: the expensive pass asks before it spends, and abstains out loud ---
#
# Everything above this line runs with no model and no credential. What follows is the half
# `full` gates: pairs the cheap blend could neither merge nor refuse are put to a model, one call
# per pair, and the number of those calls is stated by `estimate` before `reconcile` spends them.
#
# **How a pair is put *into* the band, and why these particular names.** The blend is
# `0.7 * cosine + 0.3 * trigram similarity`. `Chucri` and `Azouz` share no trigram, so the lexical
# term is `0` and the blend is exactly `0.7 * cosine` — which puts the pair wherever the fixture's
# vectors put it, with no dependence on how `pg_trgm` scores anything. Identical vectors give
# `0.7`, inside the band `[0.60, 0.83)`; orthogonal ones give `0`, below its floor. Neither name
# has a short form's shape, so signal 3 never looks at them, and no node defines one as the other,
# so signal 2 does not either: the only thing that can merge this pair is the model.


class _StubAdjudicator:
    """An `LLM` answering the adjudication prompt from a script keyed by what it was shown.

    Copied in shape from `tests/unit/weft_kg/test_extraction.py`'s own `_StubLLM`, which is this
    pack's existing double for a plugin that reaches a model through `weft_prompts.cascade`.
    `native_structured_available` is `False`, so tier 1 is skipped structurally rather than by a
    flag — the same derived-capability check a real provider is subject to — and the cascade
    itself is real, because a pass that agreed with a stubbed cascade and disagreed with the one
    `weft_cli` builds would be tested against the wrong thing.

    `calls` is the assertion subject for every *"no model call"* test here: the property `full`
    gates is that nothing is spent, and a count is the only way to see it.
    """

    def __init__(self, replies: Mapping[str, str], *, fallback: str = "") -> None:
        self._replies = replies
        self._fallback = fallback if fallback else _verdict("unsure")
        self.calls = 0

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del role, ctx
        self.calls += 1
        shown = "\n".join(message.content for message in rendered.conversation.messages)
        for marker, reply in self._replies.items():
            if marker in shown:
                return Produced(value=Completion(text=reply, model="stub-model"))
        return Produced(value=Completion(text=self._fallback, model="stub-model"))

    async def close(self) -> None: ...


def _verdict(answer: str, *, reason: str = "the stub said so") -> str:
    """The JSON a model answers tier 2 of the adjudication cascade with."""
    return json.dumps({"verdict": answer, "reason": reason})


def _model_ctx(llm: object) -> Context:
    """The `Context` `weft reconcile --mode full` carries — `_ctx()` above plus the one service
    the expensive pass reaches for. `weft_cli.commands._register_model_services` is what puts it
    there in a real run, and only when the mode is `full`.
    """
    services = ServiceRegistry()
    services.add(LLM, llm)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


async def _banded_pair(store: GraphStore) -> None:
    """Two aliases whose blended score lands inside the band — see the note above for why."""
    vector = Vector(values=(1.0, 0.0, 0.0, 0.0))
    await store.put_entity(name="Chucri", nodes=[], embedding=vector)
    await store.put_entity(name="Azouz", nodes=[], embedding=vector)


async def test_a_pair_in_the_band_reaches_no_model_under_repair(
    store: GraphStore, walk: GraphWalk
) -> None:
    """`repair` is the mode the automatic post-index pass runs in, unasked, after every
    `weft index`. A model call there would be spend nobody consented to — G3's
    installed-and-ambient threat wearing the shape of a convergence pass.
    """
    # Arrange
    await _banded_pair(store)
    llm = _StubAdjudicator({"Chucri": _verdict("yes")})

    # Act
    report = await store.reconcile(_model_ctx(llm), ReconcileMode.REPAIR)

    # Assert
    assert llm.calls == 0
    assert report.abstained == 0
    assert len(await walk.entities_by_name(["Chucri", "Azouz"])) == 2


async def test_full_states_its_model_calls_before_it_spends_any(store: GraphStore) -> None:
    """`docs/03-cli.md`: *"full states its cost before it spends it."* The number has to come
    from the same query `reconcile` then runs, or the stated cost and the spent cost are two
    facts that can disagree — which is why the second assertion counts the calls the estimate
    itself made.
    """
    # Arrange
    await _banded_pair(store)
    llm = _StubAdjudicator({"Chucri": _verdict("yes")})

    # Act
    estimate = await store.estimate(_model_ctx(llm), ReconcileMode.FULL)

    # Assert
    assert estimate.model_calls == 1
    assert "1" in estimate.description
    assert llm.calls == 0, "the estimate spent what it was supposed to be estimating"


async def test_repair_estimates_no_model_calls_however_much_is_in_the_band(
    store: GraphStore,
) -> None:
    """`ReconcileEstimate`'s own docstring: *"`repair` never backfills, so its own honest
    `model_calls` is always `0`."* Asserted with a full band, so a `model_calls` computed
    without reading the mode fails here rather than passing on an empty corpus.
    """
    # Arrange
    await _banded_pair(store)

    # Act
    estimate = await store.estimate(_ctx(), ReconcileMode.REPAIR)

    # Assert
    assert estimate.model_calls == 0


async def test_a_model_saying_yes_merges_the_two_and_moves_their_evidence(
    store: GraphStore, walk: GraphWalk
) -> None:
    """The headline property, and the reason `11.8` put the join on the alias: a bridge-merge is
    one `UPDATE` of `kg_aliases.entity_id`, so both surface forms, both their nodes and every
    edge written against either endpoint arrive under the winner without anything being deleted.
    *The evidence for the judgement survives the judgement* is that sentence read as an
    assertion — a merge that dropped the loser's alias would erase the very mention the model
    was shown.
    """
    # Arrange
    first = _node("Chucri wrote adRAP.", source="doc-a")
    second = _node("Azouz reviewed adRAP.", source="doc-a")
    await store.add([first, second])
    vector = Vector(values=(1.0, 0.0, 0.0, 0.0))
    left = await store.put_entity(name="Chucri", nodes=[first.id], embedding=vector)
    await store.put_entity(name="Azouz", nodes=[second.id], embedding=vector)
    other = await store.put_entity(
        name="adRAP", nodes=[], embedding=Vector(values=(0.0, 0.0, 1.0, 0.0))
    )
    await store.put_relation(source=left, target=other, predicate="wrote")
    llm = _StubAdjudicator({"Chucri": _verdict("yes")})

    # Act
    report = await store.reconcile(_model_ctx(llm), ReconcileMode.FULL)

    # Assert — one entity under either spelling, holding both mentions and still walking.
    [merged] = await walk.entities_by_name(["Chucri"])
    assert {entity.id for entity in await walk.entities_by_name(["Azouz"])} == {merged.id}
    assert set((await walk.nodes_for_entities([merged.id]))[merged.id]) == {first.id, second.id}
    neighbours = await walk.neighbourhood([merged.id], hops=1)
    assert {found.name for found in neighbours[merged.id]} == {"adRAP"}
    assert llm.calls == 1
    assert report.backfilled >= 1
    assert report.abstained == 0


async def test_a_model_saying_no_leaves_two_entities(store: GraphStore, walk: GraphWalk) -> None:
    """The refusal path, and the one that costs most if it is wrong: a merge cannot be undone by
    a later pass, because the losing entity's id is gone from every row that pointed at it.
    """
    # Arrange
    await _banded_pair(store)
    llm = _StubAdjudicator({"Chucri": _verdict("no")})

    # Act
    report = await store.reconcile(_model_ctx(llm), ReconcileMode.FULL)

    # Assert
    assert len({entity.id for entity in await walk.entities_by_name(["Chucri", "Azouz"])}) == 2
    assert llm.calls == 1
    assert report.abstained == 0, "a refusal is a decision, not an abstention"


async def test_a_model_that_is_unsure_abstains_and_the_pass_says_so(
    store: GraphStore, walk: GraphWalk
) -> None:
    """The third value reaching the report. Two entities that may be one is a state a reader can
    act on; the same state reported as a clean `backfilled 0` is the plausible-looking wrong
    answer requirement 5 exists to forbid.
    """
    # Arrange
    await _banded_pair(store)
    llm = _StubAdjudicator({"Chucri": _verdict("unsure")})

    # Act
    report = await store.reconcile(_model_ctx(llm), ReconcileMode.FULL)

    # Assert
    assert report.abstained == 1
    assert report.converged, "an abstention is a finished decision, not outstanding work"
    assert len({entity.id for entity in await walk.entities_by_name(["Chucri", "Azouz"])}) == 2


async def test_a_pair_below_the_floor_is_never_put_to_a_model(
    store: GraphStore, walk: GraphWalk
) -> None:
    """The floor is what keeps `model_calls` proportional to genuine ambiguity rather than to
    the square of the corpus. Orthogonal vectors and no shared trigram put this pair at `0.0`.
    """
    # Arrange
    await store.put_entity(name="Chucri", nodes=[], embedding=Vector(values=(1.0, 0.0, 0.0, 0.0)))
    await store.put_entity(name="Azouz", nodes=[], embedding=Vector(values=(0.0, 1.0, 0.0, 0.0)))
    llm = _StubAdjudicator({"Chucri": _verdict("yes")})

    # Act
    report = await store.reconcile(_model_ctx(llm), ReconcileMode.FULL)

    # Assert
    assert llm.calls == 0
    assert report.abstained == 0
    assert len({entity.id for entity in await walk.entities_by_name(["Chucri", "Azouz"])}) == 2


async def test_the_winner_of_a_bridge_merge_is_the_smaller_name(
    store: GraphStore, walk: GraphWalk
) -> None:
    """`11.8`'s rule, extended to the merge a model licenses: the canonical name is a function of
    the **set**, not of arrival order. Written in the order that would give the wrong answer to a
    pass that kept whichever entity it read first.
    """
    # Arrange — `Chucri` is written first and `Azouz` sorts before it.
    await _banded_pair(store)
    llm = _StubAdjudicator({"Chucri": _verdict("yes")})

    # Act
    await store.reconcile(_model_ctx(llm), ReconcileMode.FULL)

    # Assert
    [entity] = await walk.entities_by_name(["Chucri"])
    assert entity.name == "Azouz"


async def test_a_second_full_pass_asks_nothing_and_changes_nothing(
    store: GraphStore, walk: GraphWalk
) -> None:
    """Idempotence against the database with a model in the loop — the property that makes
    `weft reconcile --mode full` safe to run twice. Once the pair is one entity it leaves the
    band by construction, because the band only ever holds pairs whose aliases currently point
    at *different* entities, so the second pass spends nothing.
    """
    # Arrange
    await _banded_pair(store)
    llm = _StubAdjudicator({"Chucri": _verdict("yes")})
    await store.reconcile(_model_ctx(llm), ReconcileMode.FULL)
    [before] = await walk.entities_by_name(["Chucri"])

    # Act
    second = await store.reconcile(_model_ctx(llm), ReconcileMode.FULL)

    # Assert
    assert llm.calls == 1, "the second pass asked the model a question it had already answered"
    assert second.backfilled == 0
    assert second.abstained == 0
    [after] = await walk.entities_by_name(["Chucri"])
    assert after.id == before.id


async def test_a_full_pass_with_nothing_in_the_band_needs_no_model_at_all(
    store: GraphStore,
) -> None:
    """A `full` run on a project that never configured a provider must converge, not fail: the
    service is reached only where a pair actually has to be judged. `_ctx()` here is the bare
    context every test above this section uses — no `LLM` registered — so a `ctx.require(LLM)`
    hoisted to the top of the pass raises `UnresolvedServiceError` and fails this test.
    """
    # Arrange
    await store.put_entity(name="Chucri", nodes=[], embedding=Vector(values=(1.0, 0.0, 0.0, 0.0)))

    # Act
    report = await store.reconcile(_ctx(), ReconcileMode.FULL)

    # Assert
    assert report.abstained == 0
    assert report.converged
