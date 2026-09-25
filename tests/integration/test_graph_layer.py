"""Proves the graph layer is reachable by traversal, and cleaned up when its source goes.

Ledger task **43.17** — the graph layer over a real `index-with-graph` base, and what deleting a
source leaves of the relations it stated.

`enrich-with-facts-and-graph` runs `cooccurrence-graph` then `llm-facts` over the leaves a base
stored, and the base's own tail embeds and stores what they derive in both of its stores. The
graph store turns fact nodes into entity and relation rows, so after the layer an entity is
reachable through the traversal `graph-walk` reads. A layer run after it selects leaves only, so a
fact or mention node is never handed to it (R43.22's marker). Re-indexing a changed source and
deleting one cascade through the layer's rows as they do through the base's.

**The relation half is an unconfirmed finding under test.** `weft_kg.store` says deleting a fact
node makes the relation it stated unreachable. `kg_relations` is keyed `(source_alias,
target_alias, predicate)` and cascades only from `kg_aliases`, and an alias survives while any
node still attaches it. So a relation one source stated, between names another source's facts
also name, may outlive the source that stated it.

**One fresh database per test**, created and dropped by its exact recorded name, never truncated
and never matched by prefix (`L8.30`, `L22.47`). `hash` embeds and the `scripted` provider answers
with one fixed reply, so nothing leaves the machine. An absent container skips with the reason.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr

from weft_cli.ingest import IndexResult, run_index_for
from weft_engine.registry_bootstrap import build_dependencies
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, SourceId
from weft_kg.payload import ExtractedFact
from weft_kg.store import GraphSettings, GraphStore
from weft_kg.traversal import GraphWalk
from weft_store.contract import Cursor, LayerStatus
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_GRAPH_LAYER = "enrich-with-facts-and-graph"
#: Lower-case prose, so `cooccurrence-graph` finds no name and every graph row comes from a fact.
_TEXT = "a pump moves water through a pipe into a tank."


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_graph_layer_{uuid4().hex[:12]}"
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield f"{_DSN.rsplit('/', 1)[0]}/{name}"
    finally:
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _reply(*facts: tuple[str, str, str]) -> str:
    return json.dumps(
        {
            "facts": [
                {
                    "source": source,
                    "source_type": "organisation",
                    "predicate": predicate,
                    "target": target,
                    "target_type": "organisation",
                }
                for source, predicate, target in facts
            ]
        }
    )


def _configure(project: Path, dsn: str, reply: str) -> Path:
    config = project / "weft.toml"
    config.write_text(
        f'[packs.store]\ndsn = "{dsn}"\n\n'
        f'[packs.graph]\ndsn = "{dsn}"\n\n'
        '[llm.roles.index]\nprovider = "scripted"\n\n'
        f"[llm.roles.index.settings]\nreply = '{reply}'\n",
        encoding="utf-8",
    )
    return config


async def _index(
    project: Path,
    corpus: Path,
    dsn: str,
    reply: str,
    *,
    layers: tuple[str, ...],
    layers_only: bool = False,
) -> IndexResult:
    deps = build_dependencies(config_path=_configure(project, dsn, reply))
    return await run_index_for(
        deps,
        corpus,
        ctx=_ctx(),
        pipeline="index-with-graph",
        layers=layers,
        layers_only=layers_only,
    )


def _corpus(project: Path) -> Path:
    corpus = project / "corpus"
    corpus.mkdir()
    (corpus / "pumps.txt").write_text(_TEXT, encoding="utf-8")
    return corpus


async def _neighbours(dsn: str, name: str) -> set[str]:
    """The names one hop from `name` through the traversal `graph-walk` reads, or `set()`."""
    walk = GraphWalk(GraphSettings(dsn=SecretStr(dsn)))
    try:
        found = await walk.entities_by_name([name])
        if not found:
            return set()
        (entity,) = found
        around = await walk.neighbourhood([entity.id], hops=1)
        return {neighbour.name for neighbour in around.get(entity.id, ())}
    finally:
        await walk.aclose()


async def _entity_names(dsn: str, names: Sequence[str]) -> set[str]:
    walk = GraphWalk(GraphSettings(dsn=SecretStr(dsn)))
    try:
        return {entity.name for entity in await walk.entities_by_name(list(names))}
    finally:
        await walk.aclose()


async def _every_node(store: PgVectorStore) -> list[Node]:
    nodes: list[Node] = []
    cursor: Cursor | None = None
    while True:
        page = await store.scan(cursor)
        nodes.extend(page.items)
        if page.next_cursor is None:
            return nodes
        cursor = page.next_cursor


# --- the layer over a graph base -----------------------------------------------------------------


async def test_the_graph_layer_writes_relations_the_traversal_walks(
    dsn: str, tmp_path: Path
) -> None:
    # Arrange
    corpus = _corpus(tmp_path)
    reply = _reply(("Acme", "acquired", "Beta"))

    # Act
    result = await _index(tmp_path, corpus, dsn, reply, layers=(_GRAPH_LAYER,))

    # Assert
    assert result.layers_failed == ()
    assert await _neighbours(dsn, "Acme") == {"Beta"}
    vector = PgVectorStore(PgVectorSettings(dsn=SecretStr(dsn)))
    try:
        (record,) = await vector.list_sources()
    finally:
        await vector.aclose()
    assert [(layer.name, layer.status) for layer in record.layers] == [
        (_GRAPH_LAYER, LayerStatus.ACTIVE)
    ]


async def test_a_layer_run_after_the_graph_layer_is_handed_no_fact_or_mention_node(
    dsn: str, tmp_path: Path
) -> None:
    # Arrange — the same scripted reply answers `llm-facts` and, as one line, the question prompt.
    corpus = _corpus(tmp_path)
    reply = _reply(("Acme", "acquired", "Beta"))
    await _index(tmp_path, corpus, dsn, reply, layers=(_GRAPH_LAYER,))

    # Act
    await _index(tmp_path, corpus, dsn, reply, layers=("enrich-with-questions",), layers_only=True)

    # Assert
    vector = PgVectorStore(PgVectorSettings(dsn=SecretStr(dsn)))
    try:
        nodes = await _every_node(vector)
    finally:
        await vector.aclose()
    by_id = {node.id: node for node in nodes}
    facts = [node for node in nodes if "weft-kg-fact" in node.ext]
    questions = [node for node in nodes if "weft-index" in node.ext]
    assert facts, "the graph layer stored no fact node, so there was nothing to exclude"
    assert questions, "the question layer derived nothing"
    parents = {parent for node in questions for parent in node.lineage.parents}
    assert not [p for p in parents if {"weft-kg-fact", "weft-kg-mention"} & set(by_id[p].ext)]


async def test_re_indexing_a_changed_source_replaces_the_relations_its_layer_wrote(
    dsn: str, tmp_path: Path
) -> None:
    # Arrange
    corpus = _corpus(tmp_path)
    await _index(
        tmp_path, corpus, dsn, _reply(("Acme", "acquired", "Beta")), layers=(_GRAPH_LAYER,)
    )
    (corpus / "pumps.txt").write_text(_TEXT + " the tank holds the water.", encoding="utf-8")

    # Act
    await _index(
        tmp_path, corpus, dsn, _reply(("Acme", "supplies", "Gamma")), layers=(_GRAPH_LAYER,)
    )

    # Assert
    assert await _neighbours(dsn, "Acme") == {"Gamma"}
    assert await _entity_names(dsn, ["Beta"]) == set()


async def test_deleting_the_source_takes_the_graph_rows_its_layer_wrote(
    dsn: str, tmp_path: Path
) -> None:
    # Arrange
    corpus = _corpus(tmp_path)
    await _index(
        tmp_path, corpus, dsn, _reply(("Acme", "acquired", "Beta")), layers=(_GRAPH_LAYER,)
    )
    vector = PgVectorStore(PgVectorSettings(dsn=SecretStr(dsn)))
    graph = GraphStore(GraphSettings(dsn=SecretStr(dsn)))
    try:
        (record,) = await vector.list_sources()

        # Act
        await vector.delete_source(record.id)
        await graph.delete_source(record.id)
    finally:
        await vector.aclose()
        await graph.aclose()

    # Assert
    assert await _entity_names(dsn, ["Acme", "Beta"]) == set()


# --- what deleting one source leaves of the relations it stated ---------------------------------


def _fact(source: str, subject: str, predicate: str, target: str) -> Node:
    return Node.synthetic(
        content=f"{subject} {predicate} {target} ({source})",
        media_type=MediaType.TEXT,
        reason="the graph layer's relation-deletion test",
        sources=frozenset({SourceId(source)}),
    ).with_ext(
        ExtractedFact(
            source=subject,
            source_type="organisation",
            predicate=predicate,
            target=target,
            target_type="organisation",
        )
    )


async def test_a_relation_only_the_deleted_source_stated_is_unreachable_after_it(
    dsn: str,
) -> None:
    # Arrange — `doc-b`'s facts attach both of `doc-a`'s endpoints, so their aliases survive it.
    store = GraphStore(GraphSettings(dsn=SecretStr(dsn)))
    try:
        await store.add(
            [
                _fact("doc-a", "Acme", "acquired", "Gamma"),
                _fact("doc-b", "Acme", "supplies", "Beta"),
                _fact("doc-b", "Gamma", "employs", "Delta"),
            ]
        )
        assert await _neighbours(dsn, "Acme") == {"Beta", "Gamma"}

        # Act
        await store.delete_source(SourceId("doc-a"))
    finally:
        await store.aclose()

    # Assert
    assert await _neighbours(dsn, "Acme") == {"Beta"}
    assert await _neighbours(dsn, "Gamma") == {"Delta"}


async def test_a_relation_two_sources_stated_survives_deleting_one_of_them(dsn: str) -> None:
    # Arrange
    store = GraphStore(GraphSettings(dsn=SecretStr(dsn)))
    try:
        await store.add(
            [
                _fact("doc-a", "Acme", "supplies", "Beta"),
                _fact("doc-b", "Acme", "supplies", "Beta"),
            ]
        )

        # Act
        await store.delete_source(SourceId("doc-a"))
    finally:
        await store.aclose()

    # Assert
    assert await _neighbours(dsn, "Acme") == {"Beta"}


# --- Task 43.35: `weft_kg`'s connection prepares no statement and opens once under concurrent
# callers. `R43.39` made `PgVectorStore`'s connection unprepared (psycopg prepares on the fifth
# run, and a prepared `SELECT *` refuses to run once another handle changes the table under it);
# `weft_kg.store.resolve_target_connection` still used the default. And `GraphStore._connection`
# opened lazily with no lock, the race `43.27` closed for pgvector, one module over.


async def _backends_in(dsn: str) -> int:
    name = dsn.rsplit("/", 1)[1]
    async with await psycopg.AsyncConnection.connect(_DSN, autocommit=True) as admin:
        row = await (
            await admin.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", (name,))
        ).fetchone()
    return int(row[0]) if row else 0


async def test_concurrent_first_calls_on_one_graph_handle_open_one_connection(dsn: str) -> None:
    # Arrange
    store = GraphStore(GraphSettings(dsn=SecretStr(dsn)))
    before = await _backends_in(dsn)

    # Act
    try:
        await asyncio.gather(*(store.list_sources() for _ in range(4)))
        during = await _backends_in(dsn)
    finally:
        await store.aclose()

    # Assert
    assert (before, during) == (0, 1)


async def test_a_graph_read_survives_another_handle_adding_a_column_under_it(dsn: str) -> None:
    # Arrange — a read run past psycopg's preparation threshold on one handle.
    store = GraphStore(GraphSettings(dsn=SecretStr(dsn)))
    try:
        for _ in range(6):
            await store.list_sources()
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as other:
            await other.execute("ALTER TABLE kg_sources ADD COLUMN added_by_another_handle TEXT")

        # Act
        after = await store.list_sources()
    finally:
        await store.aclose()

    # Assert
    assert list(after) == []
