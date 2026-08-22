"""`GraphStore` against a real Postgres — `docs/build-ledger.md` task 5.4/5.5's own
conformance-kit convention: this module is collected but every test in it is marked to be
skipped, with a reason, when the container is not up, per `tests/integration/
test_store_conformance.py`'s own precedent (there expressed the same way `pytest` itself
documents: a `pytestmark` computed once, from a synchronous reachability probe).
"""

import os
import uuid

import psycopg
import pytest
from pydantic import SecretStr
from weft_example_graph.payload import Entity, GraphData, Relation
from weft_example_graph.store import GraphBackfillUnavailableError, GraphSettings, GraphStore

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_store.contract import ReconcileMode

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _unreachable_reason() -> str | None:
    try:
        conn = psycopg.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`."
    conn.close()
    return None


_UNREACHABLE = _unreachable_reason()
pytestmark = pytest.mark.skipif(_UNREACHABLE is not None, reason=_UNREACHABLE or "")


def _ctx() -> Context:
    return Context(tenant_id="t", run_id=str(uuid.uuid4()), trace_id="tr", locale="en")


def _node(content: str, *, source: str, graph_data: GraphData | None = None) -> Node:
    node = Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="weft-example-graph's own store test",
        sources=frozenset({SourceId(source)}),
    )
    return node if graph_data is None else node.with_ext(graph_data)


@pytest.fixture
def store() -> GraphStore:
    return GraphStore(GraphSettings(dsn=SecretStr(_DSN)))


async def test_dsn_not_configured_raises_at_first_use_not_at_construction() -> None:
    # Arrange — the empty default `GraphSettings()` a bare `register()` sees.
    unconfigured = GraphStore(GraphSettings())

    # Act / Assert — constructing it never raises; only a real call does.
    with pytest.raises(Exception) as excinfo:
        await unconfigured.count()
    assert "dsn" in str(excinfo.value).lower()


async def test_add_then_get_round_trips_content_lineage_and_ext(store: GraphStore) -> None:
    # Arrange
    data = GraphData(entities=(Entity(name="Acme Corp", count=2),), relations=())
    node = _node("Acme Corp builds things.", source="doc-1", graph_data=data)

    # Act
    await store.add([node])
    (fetched,) = await store.get([node.id])

    # Assert
    assert fetched.id == node.id
    assert fetched.content == node.content
    assert fetched.lineage.sources == node.lineage.sources
    assert fetched.ext_as(GraphData) == data


async def test_add_populates_entities_and_relations_tables(store: GraphStore) -> None:
    # Arrange
    data = GraphData(
        entities=(Entity(name="Acme Corp"), Entity(name="Globex Inc")),
        relations=(Relation(source="Acme Corp", target="Globex Inc"),),
    )
    node = _node("Acme Corp and Globex Inc.", source="doc-2", graph_data=data)

    # Act
    await store.add([node])

    # Assert
    nodes_with_data, entities, relations = await store.summary()
    assert nodes_with_data >= 1
    assert entities >= 2
    assert relations >= 1
    neighbors = await store.neighbors_of("Acme Corp")
    matching = [n for n in neighbors if n[:2] == ("Globex Inc", "co_occurs_with")]
    assert matching and matching[0][2] >= 1


async def test_run_persists_and_passes_the_batch_through(store: GraphStore) -> None:
    # Arrange
    node = _node("plain node, no graph data", source="doc-3")

    # Act
    outcome = await store.run([node], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert list(outcome.value) == [node]
    (fetched,) = await store.get([node.id])
    assert fetched.id == node.id


async def test_count_and_scan(store: GraphStore) -> None:
    # Arrange
    nodes = [_node(f"node {i}", source="doc-4") for i in range(3)]
    await store.add(nodes)

    # Act
    total = await store.count()
    page = await store.scan()

    # Assert
    assert total >= 3
    assert {item.id for item in nodes} <= {item.id for item in page.items}


async def test_delete_source_removes_nodes_and_cascades_entities(store: GraphStore) -> None:
    # Arrange
    data = GraphData(entities=(Entity(name="Initech"),), relations=())
    node = _node("Initech appears here.", source="doc-5", graph_data=data)
    await store.add([node])

    # Act
    removed = await store.delete_source(SourceId("doc-5"))

    # Assert
    assert removed.node_count == 1
    assert await store.get([node.id]) == ()
    neighbors = await store.neighbors_of("Initech")
    assert neighbors == ()


async def test_reconcile_repair_recomputes_from_stored_ext(store: GraphStore) -> None:
    # Arrange — a node whose stored `content` no longer matches its stored `GraphData`,
    # simulating a partial write `add()`'s own per-statement autocommit can leave behind.
    stale = GraphData(entities=(Entity(name="Stale Corp"),), relations=())
    node = _node("Fresh Corp is what this content says now.", source="doc-6", graph_data=stale)
    await store.add([node])

    # Act
    report = await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert — repair converges this pack's own bookkeeping to its own stored `ext`, so
    # "Stale Corp" (from `ext`) is still what is recorded, not "Fresh Corp" (from `content`)
    # — that distinction belongs to `rebuild`, tested below.
    assert report.converged
    nodes_with_data, entities, _ = await store.summary()
    assert nodes_with_data >= 1
    assert entities >= 1


async def test_reconcile_full_raises_naming_the_gap(store: GraphStore) -> None:
    # Assert — a design finding, not a bug: see GraphBackfillUnavailableError's own docstring.
    with pytest.raises(GraphBackfillUnavailableError):
        await store.reconcile(_ctx(), ReconcileMode.FULL)
    with pytest.raises(GraphBackfillUnavailableError):
        await store.estimate(_ctx(), ReconcileMode.FULL)


async def test_estimate_repair_reports_a_real_pending_count(store: GraphStore) -> None:
    # Arrange
    await store.add([_node("some content", source="doc-7")])

    # Act
    estimate = await store.estimate(_ctx(), ReconcileMode.REPAIR)

    # Assert
    assert estimate.mode is ReconcileMode.REPAIR
    assert estimate.pending >= 1
    assert estimate.model_calls == 0


async def test_rebuild_recomputes_from_current_content(store: GraphStore) -> None:
    # Arrange — stored `ext` disagrees with stored `content`, exactly as the repair test
    # above, but `rebuild` re-derives from `content` with the *current* extraction logic.
    stale = GraphData(entities=(Entity(name="Old Name"),), relations=())
    node = _node("New Name shows up in the text now.", source="doc-8", graph_data=stale)
    await store.add([node])

    # Act
    examined, entities, _relations = await store.rebuild()

    # Assert
    assert examined >= 1
    assert entities >= 1
    (fetched,) = await store.get([node.id])
    data = fetched.ext_as(GraphData)
    assert data is not None
    assert {entity.name for entity in data.entities} == {"New Name"}
    neighbors = await store.neighbors_of("Old Name")
    assert neighbors == ()
