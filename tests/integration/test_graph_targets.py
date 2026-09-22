"""The graph pack holds targets the way the node store does — ledger task **34.11**, its store half.

A promote over a project whose graph pack is active has to move the graph with the nodes, or the
graph answers from one corpus while the vectors answer from another. So `GraphStore` satisfies
`TargetHolding` with a Postgres schema per target on its own `[packs.graph] dsn`, the pgvector
store's shape (`34.1`), with its catalogue in `kg_targets` and `kg_live_target` beside the
pre-target `kg_*` tables that are `default`. `GraphWalk`, the query-time traversal on its own
connection, reads whichever graph target is live when it opens. `kg_active_schema`'s one row
becomes one row per target because each target's tables are its own, which is the collection key
`S13` recorded (`weft_kg/store.py`, `kg_active_schema`).

Every test owns a database, created and dropped by exact name.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr

from weft_kernel.payload import MediaType, Node
from weft_kg.store import GraphSettings, GraphStore
from weft_kg.traversal import GraphWalk
from weft_store.conformance import checks_for, register_conformance_ext_models
from weft_store.contract import Promotion, TargetHolding, target_name

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

register_conformance_ext_models()


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_graph_targets_{uuid4().hex[:12]}"
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


def _graph(dsn: str) -> GraphStore:
    return GraphStore(GraphSettings(dsn=SecretStr(dsn)))


def _target_checks() -> list[Callable[..., Awaitable[None]]]:
    probe = GraphStore(GraphSettings(dsn=SecretStr("postgresql://unused/unused")))
    return [
        check
        for check in checks_for(probe)
        if check.__annotations__.get("store") == "TargetHoldingStore"
    ]


def test_the_graph_store_holds_targets_and_is_offered_every_target_check() -> None:
    # Assert
    assert isinstance(GraphStore(GraphSettings()), TargetHolding)
    assert len(_target_checks()) == 13


@pytest.mark.parametrize("check", _target_checks(), ids=lambda check: check.__name__)
async def test_the_published_target_checks_hold_on_the_graph_store(
    dsn: str, check: Callable[..., Awaitable[None]]
) -> None:
    # Arrange
    store = _graph(dsn)

    # Act / Assert
    try:
        await check(store)
    finally:
        await store.aclose()


async def test_the_traversal_reads_the_graph_target_that_is_live_when_it_opens(dsn: str) -> None:
    # Arrange — an entity only the candidate's graph holds.
    live = _graph(dsn)
    candidate = await live.bind_target(target_name("w128"))
    node = Node.synthetic(content="Pumps move water.", media_type=MediaType.TEXT, reason="graph")
    await candidate.add([node])
    await candidate.put_entity(name="Pump", nodes=[node.id])
    await candidate.aclose()
    before = GraphWalk(GraphSettings(dsn=SecretStr(dsn)))

    # Act
    found_before = await before.entities_by_name(["Pump"])
    await before.aclose()
    await live.promote(
        Promotion(
            target="w128", at=datetime.now(UTC), by="test", evidence=(), without_evidence=True
        )
    )
    after = GraphWalk(GraphSettings(dsn=SecretStr(dsn)))
    found_after = await after.entities_by_name(["Pump"])
    await after.aclose()
    await live.aclose()

    # Assert
    assert found_before == ()
    assert [entity.name for entity in found_after] == ["Pump"]
