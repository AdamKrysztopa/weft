"""`weft_kg`'s graph store holds generations — ledger task **43.39**.

Phase 43f's owner answer: all four shipped layers stack on the graph base, and a corpus-scoped
layer refuses any store that cannot hold generations. So the graph store holds them. It searches
nothing, so the generation checks it answers are the ones that read through `NodeStore` and the
catalogue, and its own reads are the graph's: an entity a generation's node names is absent from
the traversal until the generation is published, and gone once it is retracted.

Every test owns a database, created and dropped by exact name.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr

from weft_kernel.payload import MediaType, Node, SourceId
from weft_kernel.registry import DuplicateRegistrationError
from weft_kg.payload import MentionedEntity
from weft_kg.store import GraphSettings, GraphStore
from weft_kg.traversal import GraphWalk
from weft_store.conformance import checks_for, register_conformance_ext_models
from weft_store.contract import GenerationCarrying, GenerationHolding, GenerationWithdrawing
from weft_store.rehydrate import register_ext_model

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

register_conformance_ext_models()
# A `weft` process registers this at discovery; a store test that builds no registry does it here.
with contextlib.suppress(DuplicateRegistrationError):
    register_ext_model(MentionedEntity)


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_graph_generations_{uuid4().hex[:12]}"
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


def _offered() -> list[Callable[..., Awaitable[None]]]:
    return list(checks_for(_graph("postgresql://unused/unused")))


def test_the_graph_store_holds_generations() -> None:
    # Assert
    assert isinstance(_graph("postgresql://unused/unused"), GenerationHolding)
    assert "check_a_generation_record_round_trips_and_an_unknown_one_is_refused_by_name" in {
        check.__name__ for check in _offered()
    }


@pytest.mark.parametrize("check", _offered(), ids=lambda check: check.__name__)
async def test_every_published_check_offered_holds_on_the_graph_store(
    dsn: str, check: Callable[..., Awaitable[None]]
) -> None:
    # Arrange
    store = _graph(dsn)

    # Act / Assert
    try:
        await check(store)
    finally:
        await store.aclose()


def _mention(name: str) -> Node:
    chunk = Node.synthetic(
        content=f"A passage naming {name}.",
        media_type=MediaType.TEXT,
        reason="43.39",
        sources=frozenset({SourceId("doc-generations")}),
    )
    return chunk.derive(content=name, ordinal=0).with_ext(
        MentionedEntity(name=name, entity_type="thing")
    )


async def _entities(dsn: str, name: str) -> list[str]:
    walk = GraphWalk(GraphSettings(dsn=SecretStr(dsn)))
    try:
        return [entity.name for entity in await walk.entities_by_name([name])]
    finally:
        await walk.aclose()


async def test_an_entity_a_generation_names_is_absent_until_it_is_published(dsn: str) -> None:
    # Arrange
    store = _graph(dsn)
    generation = await store.open_generation("summaries")
    writer = await store.bind_generation(generation.id)
    await writer.add([_mention("Pump")])

    # Act
    before = await _entities(dsn, "Pump")
    await store.publish_generation(generation.id)
    after = await _entities(dsn, "Pump")
    await store.aclose()

    # Assert
    assert before == []
    assert after == ["Pump"]


async def test_retracting_a_generation_takes_the_entities_only_it_named(dsn: str) -> None:
    # Arrange
    store = _graph(dsn)
    await store.add([_mention("Valve")])
    generation = await store.open_generation("summaries")
    await (await store.bind_generation(generation.id)).add([_mention("Pump")])
    await store.publish_generation(generation.id)

    # Act
    await store.retract_generation(generation.id)
    pump, valve = await _entities(dsn, "Pump"), await _entities(dsn, "Valve")
    await store.aclose()

    # Assert
    assert pump == []
    assert valve == ["Valve"]


async def test_a_node_the_base_also_wrote_survives_retracting_the_generation(dsn: str) -> None:
    """A node written unbound and then by a generation is the base's too; retract keeps it."""
    # Arrange
    store = _graph(dsn)
    shared = _mention("Pump")
    await store.add([shared])
    generation = await store.open_generation("summaries")
    await (await store.bind_generation(generation.id)).add([shared])
    await store.publish_generation(generation.id)

    # Act
    await store.retract_generation(generation.id)
    kept = await store.get([shared.id])
    pump = await _entities(dsn, "Pump")
    await store.aclose()

    # Assert
    assert [node.id for node in kept] == [shared.id]
    assert pump == ["Pump"]


def test_the_graph_store_withdraws_and_carries_generations() -> None:
    """Ledger 43.40: a corpus layer over the graph base supersedes, reclaims and joins."""
    # Assert
    store = _graph("postgresql://unused/unused")
    assert isinstance(store, GenerationWithdrawing)
    assert isinstance(store, GenerationCarrying)
    assert "check_withdrawing_an_unknown_or_unpublished_generation_is_refused_by_name" in {
        check.__name__ for check in _offered()
    }


async def test_a_withdrawn_generation_leaves_the_graph_and_its_nodes_wait_for_reclaim(
    dsn: str,
) -> None:
    # Arrange
    store = _graph(dsn)
    pump = _mention("Pump")
    generation = await store.open_generation("summaries")
    await (await store.bind_generation(generation.id)).add([pump])
    await store.publish_generation(generation.id)

    # Act
    await store.withdraw_generation(generation.id)
    after_withdraw = await _entities(dsn, "Pump"), await store.get([pump.id])
    await store.reclaim_withdrawn("summaries")
    after_reclaim = await store.get([pump.id])
    await store.aclose()

    # Assert
    assert after_withdraw[0] == []
    assert [node.id for node in after_withdraw[1]] == [pump.id]
    assert after_reclaim == ()


async def test_a_carried_node_keeps_its_entity_when_the_generation_it_left_is_withdrawn(
    dsn: str,
) -> None:
    # Arrange
    store = _graph(dsn)
    pump, valve, gear = _mention("Pump"), _mention("Valve"), _mention("Gear")
    old = await store.open_generation("summaries")
    await (await store.bind_generation(old.id)).add([pump, valve])
    await store.publish_generation(old.id)
    new = await store.open_generation("summaries")
    await store.carry_forward(new.id, [pump.id])
    await (await store.bind_generation(new.id)).add([gear])
    await store.publish_generation(new.id)

    # Act
    await store.withdraw_generation(old.id)
    seen = {name: await _entities(dsn, name) for name in ("Pump", "Valve", "Gear")}
    await store.reclaim_withdrawn("summaries")
    kept = {node.id for node in await store.get([pump.id, valve.id, gear.id])}
    await store.aclose()

    # Assert
    assert seen == {"Pump": ["Pump"], "Valve": [], "Gear": ["Gear"]}
    assert kept == {pump.id, gear.id}
