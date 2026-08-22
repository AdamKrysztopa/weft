"""`GraphBuildCommand` and `GraphShowCommand` against a real Postgres — see `test_store.py`'s
own module docstring for the reachability-probe convention this file follows.
"""

import os
from typing import cast

import psycopg
import pytest
from pydantic import SecretStr
from weft_example_graph.commands import (
    GraphBuildArgs,
    GraphBuildCommand,
    GraphBuildResult,
    GraphShowArgs,
    GraphShowCommand,
    GraphShowResult,
)
from weft_example_graph.extraction import extract_graph_data
from weft_example_graph.payload import Entity, GraphData
from weft_example_graph.store import GraphSettings, GraphStore

from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced, SourceId

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
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def test_permission_classes_are_declared_and_distinct() -> None:
    # `docs/03-cli.md` -> *Permissions*: "weft graph build rebuilding a graph belongs in
    # overwrite exactly as a core command would."

    assert GraphBuildCommand.permission_class is PermissionClass.OVERWRITE
    assert GraphShowCommand.permission_class is PermissionClass.READ
    assert GraphBuildCommand.help
    assert GraphShowCommand.help


async def test_build_recomputes_from_stored_content() -> None:
    # Arrange
    settings = GraphSettings(dsn=SecretStr(_DSN))
    store = GraphStore(settings)
    stale = GraphData(entities=(Entity(name="Old Name"),), relations=())
    node = Node.synthetic(
        content="New Name is what the text says now.",
        media_type=MediaType.TEXT,
        reason="command test",
        sources=frozenset({SourceId("command-doc-1")}),
    ).with_ext(stale)
    await store.add([node])
    command = GraphBuildCommand(settings)

    # Act
    outcome = await command.run(GraphBuildArgs(), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = cast(GraphBuildResult, outcome.value)
    assert result.examined >= 1
    (fetched,) = await store.get([node.id])
    data = fetched.ext_as(GraphData)
    assert data is not None
    assert {entity.name for entity in data.entities} == {"New Name"}


async def test_show_without_an_entity_returns_a_corpus_summary() -> None:
    # Arrange
    settings = GraphSettings(dsn=SecretStr(_DSN))
    store = GraphStore(settings)
    node = Node.synthetic(
        content="Contoso Ltd appears in this corpus.",
        media_type=MediaType.TEXT,
        reason="command test",
        sources=frozenset({SourceId("command-doc-2")}),
    ).with_ext(GraphData(entities=(Entity(name="Contoso Ltd"),), relations=()))
    await store.add([node])
    command = GraphShowCommand(settings)

    # Act
    outcome = await command.run(GraphShowArgs(), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = cast(GraphShowResult, outcome.value)
    assert result.nodes_with_graph_data >= 1
    assert result.distinct_entities >= 1
    assert result.entity is None
    assert any(item.name == "Contoso Ltd" for item in result.top_entities)


async def test_show_with_an_entity_returns_its_neighbours() -> None:
    # Arrange
    settings = GraphSettings(dsn=SecretStr(_DSN))
    store = GraphStore(settings)
    node = Node.synthetic(
        content="Wayne Enterprises partners with Stark Industries.",
        media_type=MediaType.TEXT,
        reason="command test",
        sources=frozenset({SourceId("command-doc-3")}),
    )

    entities, relations = extract_graph_data(node.content)
    node = node.with_ext(GraphData(entities=entities, relations=relations))
    await store.add([node])
    command = GraphShowCommand(settings)

    # Act
    outcome = await command.run(GraphShowArgs(entity="Wayne Enterprises"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = cast(GraphShowResult, outcome.value)
    assert result.entity == "Wayne Enterprises"
    assert any(n.name == "Stark Industries" for n in result.neighbors)
