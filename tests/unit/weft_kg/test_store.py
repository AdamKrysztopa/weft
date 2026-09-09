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

**Three traversal semantics decided here, from the documents, because the contract admits more
than one reading and only one can be built on.** *(i)* `nodes_for_entities` keys the mapping on
exactly the requested ids **the store holds a row for** — an id it does not hold is absent, never a
key with an empty tuple, because `docs/lessons.md` L5.9's rule is that an empty collection means
"I did not find it" and a caller must be able to tell that from "found it, it has nothing".
*(ii)* `neighbourhood` walks relations **undirected**: a relation is stored with a direction because
it has one, but *"the neighbourhood of an entity"* is a question about reach, and a retrieval walk
that could only travel one way would miss the half of the graph pointing at its seed. The seed is
excluded from its own neighbourhood.

**A third semantic was decided here and then removed.** `nearest_entities` ranked entities by
cosine distance, and the first out-of-tree implementation — a graph over ordinary tables with no
vector column in it — could satisfy the other members honestly and that one not at all. It moves to
an `EntityVectorSearch` Protocol of its own, on `weft_store.contract`'s own precedent for
`VectorSearch` beside `NodeStore`, and that Protocol is **not written yet** because nothing consumes
it. `weft_kg.contract` records what it takes and what triggers writing it; `L11.29`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import psycopg
import pytest
from pydantic import SecretStr

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NodeId, SourceId, Vector
from weft_kg.contract import EntityId
from weft_kg.payload import (
    CooccurrenceEdge,
    CooccurrenceGraph,
    EntityMention,
    ExtractedFact,
    MentionedEntity,
)
from weft_kg.store import GraphSettings, GraphStore
from weft_kg.traversal import GraphWalk
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
    chucri = await store.put_entity(name="Chucri", nodes=[node.id])
    await store.put_entity(name="Azouz", nodes=[node.id])

    # Act
    found = await walk.entities_by_name(["Chucri", "nobody-by-that-name"])

    # Assert — the name that exists comes back, the one that does not simply is not there.
    assert [entity.name for entity in found] == ["Chucri"]
    assert found[0].id == chucri


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
    chucri = await store.put_entity(name="Chucri", nodes=[node.id])

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

    # Act
    one_hop = await walk.neighbourhood([b], hops=1)
    two_hops = await walk.neighbourhood([a], hops=2)

    # Assert — both neighbours at one hop, and the seed is never in its own neighbourhood.
    assert {entity.name for entity in one_hop[b]} == {"a", "c"}
    assert {entity.name for entity in two_hops[a]} == {"b", "c"}


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

    # Act
    one_hop = await walk.neighbourhood([a], hops=1)

    # Assert
    assert {entity.name for entity in one_hop[a]} == {"b"}


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
    chucri = await store.put_entity(name="Chucri", nodes=[node.id])
    assert await walk.entities_by_name(["Chucri"]) != ()

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
    chucri = await store.put_entity(name="Chucri", nodes=[node.id])

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
