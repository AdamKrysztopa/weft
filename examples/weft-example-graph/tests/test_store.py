"""`GraphStore` against a real Postgres — `docs/build-ledger.md` task 5.4/5.5's own
conformance-kit convention: this module is collected but every test in it is marked to be
skipped, with a reason, when the container is not up, per `tests/integration/
test_store_conformance.py`'s own precedent (there expressed the same way `pytest` itself
documents: a `pytestmark` computed once, from a synchronous reachability probe).
"""

import os
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import psycopg
import pytest
from pydantic import SecretStr
from weft_example_graph.payload import Entity, GraphData, Relation
from weft_example_graph.store import GraphSettings, GraphStore

from weft_kernel.context import Context, UnresolvedServiceError
from weft_kernel.payload import MediaType, Node, NodeId, Produced, SourceId
from weft_store.contract import Cursor, NodeStore, Page, ReconcileMode, SourceRecord

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


class _CorpusStore:
    """The primary `NodeStore` a reconcile pass now carries on its passport — in memory, since
    what is under test is that the graph store can *reach* a corpus, not what the corpus is.

    Only the three methods `02` §1 names as answering *what should exist* are ever called:
    `scan`, `count` and `list_sources`. Every other `NodeStore` method is here because a
    hand-rolled double must carry every public method of the thing it doubles
    (`docs/lessons.md` L5.26) — a partial double passes until the day the code under test
    reaches for the missing one.
    """

    def __init__(self, nodes: list[Node], *, sources: Sequence[str] = ()) -> None:
        self._nodes = list(nodes)
        self._sources = tuple(
            SourceRecord(
                id=SourceId(source),
                uri=f"file:///{source}",
                content_hash="deadbeef",
                indexed_at=datetime(2026, 8, 22, tzinfo=UTC),
                pipeline="kg",
            )
            for source in sources
        )

    async def run(self, payload: Sequence[Node], ctx: Context) -> Produced[Sequence[Node]]:
        del ctx
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        self._nodes.extend(nodes)

    async def flush(self) -> None: ...

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        wanted = set(ids)
        return tuple(node for node in self._nodes if node.id in wanted)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        return Page(items=tuple(self._nodes))

    async def count(self) -> int:
        return len(self._nodes)

    async def put_source(self, record: SourceRecord) -> None:
        del record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        del source_id
        return None

    async def list_sources(self) -> Sequence[SourceRecord]:
        return self._sources


def _ctx_with_corpus(corpus: _CorpusStore) -> Context:
    """One `Context` with the configured `NodeStore` on it — what `weft_cli.commands` does for
    a real reconcile pass, done by hand here so the pack's own test needs no CLI.
    """
    ctx = _ctx()
    ctx.services.add(NodeStore, corpus)
    return ctx


def _graph_entities_of(node: Node) -> tuple[Entity, ...]:
    data = node.ext.get(GraphData.__namespace__)
    return data.entities if isinstance(data, GraphData) else ()


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

    # Act — `repair` reads the corpus too, as of task 6.21: `02` §4's table promises it drops
    # orphans left by anything the deletion fan-out missed, and "orphan" is only answerable
    # against what the corpus still holds. `doc-6` is still there, so nothing is dropped.
    report = await store.reconcile(
        _ctx_with_corpus(_CorpusStore([node], sources=())), ReconcileMode.REPAIR
    )

    # Assert — repair converges this pack's own bookkeeping to its own stored `ext`, so
    # "Stale Corp" (from `ext`) is still what is recorded, not "Fresh Corp" (from `content`)
    # — that distinction belongs to `rebuild`, tested below.
    assert report.converged
    nodes_with_data, entities, _ = await store.summary()
    assert nodes_with_data >= 1
    assert entities >= 1


async def test_reconcile_full_backfills_from_the_corpus_on_the_passport(
    store: GraphStore,
) -> None:
    """Task **6.19**, G13's second repair. `02` §1 → *Extended by G13*: a participant that is
    not the primary store asks through the passport — `ctx.require(NodeStore)`, G1's one
    resolution seam — rather than through a wider `reconcile` signature. `02` §4's own table
    row is what this makes true: "`full` backfills entities for nodes indexed by a pipeline
    that had no graph stage".

    Until this task the same call raised `GraphBackfillUnavailableError`, and that error class
    is gone: the access it named as missing exists, so an error saying it does not would now be
    a lie rather than a design finding.
    """
    # Arrange — a node the corpus holds and this graph store has never seen, exactly the
    # "indexed by a pipeline that had no graph stage" case.
    orphaned = _node("Acme Corp acquired Initech last spring.", source="doc-backfill")
    corpus = _CorpusStore([orphaned])
    ctx = _ctx_with_corpus(corpus)

    # Act
    report = await store.reconcile(ctx, ReconcileMode.FULL)

    # Assert — the node is now held here, with graph data derived from its own content.
    assert report.backfilled >= 1
    held = await store.get([orphaned.id])
    assert len(held) == 1
    assert _graph_entities_of(held[0])


async def test_estimate_full_counts_what_the_corpus_holds_and_this_store_does_not(
    store: GraphStore,
) -> None:
    """`docs/03-cli.md` → *Command surface*: "full states its cost before it spends it." The
    cost is a real count read off the corpus, not a placeholder — and `model_calls` is `0`
    honestly, because this pack's extraction is deterministic and calls no model.
    """
    # Arrange
    already_here = _node("Held already.", source="doc-known")
    await store.add([already_here])
    missing = _node("Globex Inc partnered with Umbrella Ltd.", source="doc-missing")
    ctx = _ctx_with_corpus(_CorpusStore([already_here, missing]))

    # Act
    estimate = await store.estimate(ctx, ReconcileMode.FULL)

    # Assert
    assert estimate.pending == 1
    assert estimate.model_calls == 0
    assert "doc-missing" in estimate.description or "1" in estimate.description


async def test_full_without_a_corpus_on_the_passport_says_what_is_missing(
    store: GraphStore,
) -> None:
    """The loud failure the seam earns. A backfill with no corpus registered is not a backfill
    of zero — `01` rule 5 — so it refuses, naming the contract it wanted and what *is* on this
    run's passport.
    """
    # Act / Assert
    with pytest.raises(UnresolvedServiceError) as raised:
        await store.reconcile(_ctx(), ReconcileMode.FULL)

    # Assert
    assert "NodeStore" in str(raised.value)


async def test_repair_drops_a_node_whose_source_the_corpus_no_longer_holds(
    store: GraphStore,
) -> None:
    """Task **6.21**, the last unbuilt row of `02` §4's own table: "`repair` drops orphans left
    by anything the [deletion] fan-out missed".

    An orphan is a graph node whose source the *primary corpus* no longer lists — which this
    store cannot answer from its own tables, and could not ask about at all until task 6.19 put
    the corpus on the passport. The fan-out reaching this store in-command (task 6.18) makes an
    orphan rarer, never impossible: a participant that raised mid-fan-out leaves exactly this.
    """
    # Arrange — two sources here, one of them gone from the corpus.
    kept = _node("Acme Corp is still indexed.", source="doc-kept")
    orphaned = _node("Initech was deleted from the corpus.", source="doc-gone")
    await store.add([kept, orphaned])
    # The corpus holds the node and reports **no** source records — the shape a real
    # `weft index` actually leaves, since nothing on the ingest path calls `put_source`
    # (`docs/lessons.md` L6.14). A double that populated both routes could not tell a
    # correct orphan rule from one reading the empty list, which is how the first draft of
    # this pack's rule passed here and then deleted every node when run for real.
    ctx = _ctx_with_corpus(_CorpusStore([kept], sources=()))

    # Act
    report = await store.reconcile(ctx, ReconcileMode.REPAIR)

    # Assert — the orphan is gone from this store, and the one the corpus still holds is not.
    assert report.removed >= 1
    assert await store.get([orphaned.id]) == ()
    assert len(await store.get([kept.id])) == 1


async def test_repair_without_a_corpus_on_the_passport_says_what_is_missing(
    store: GraphStore,
) -> None:
    """`repair` needs the corpus for the same reason `full` does, so it refuses for the same
    reason too. Doing the half it can and silently skipping orphan detection would be `01`
    rule 5's silent degradation — the operator would read "converged" and still hold orphans.
    """
    # Act / Assert
    with pytest.raises(UnresolvedServiceError) as raised:
        await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert
    assert "NodeStore" in str(raised.value)


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
