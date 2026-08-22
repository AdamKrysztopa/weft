"""`GraphWalkRetriever` against a real Postgres — see `test_store.py`'s own module docstring
for the reachability-probe convention this file follows.
"""

import os

import psycopg
import pytest
from pydantic import SecretStr
from weft_example_graph.payload import Entity, GraphData, Relation
from weft_example_graph.retriever import GraphWalkConfig, GraphWalkRetriever
from weft_example_graph.store import GraphSettings, GraphStore

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_retrieve.payload import Query, QuerySet

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


def _query_set(text: str) -> QuerySet:
    query = Query(text=text)
    return QuerySet(origin=query, queries=(query,))


async def test_a_query_naming_no_known_entity_gets_an_empty_ranked_list() -> None:
    # Arrange
    retriever = GraphWalkRetriever(GraphSettings(dsn=SecretStr(_DSN)))

    # Act
    outcome = await retriever.run(_query_set("lowercase question, no proper nouns"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    (ranked,) = outcome.value.lists
    assert ranked.hits == ()


async def test_a_query_naming_a_known_entity_finds_its_node_and_neighbours() -> None:
    # Arrange — one store to seed data, a fresh retriever reading the same database.
    store = GraphStore(GraphSettings(dsn=SecretStr(_DSN)))
    data = GraphData(
        entities=(Entity(name="Acme Corp"), Entity(name="Globex Inc")),
        relations=(Relation(source="Acme Corp", target="Globex Inc"),),
    )
    node = Node.synthetic(
        content="Acme Corp partners with Globex Inc.",
        media_type=MediaType.TEXT,
        reason="retriever test",
        sources=frozenset({SourceId("retriever-doc")}),
    ).with_ext(data)
    other = Node.synthetic(
        content="Globex Inc alone, mentioned elsewhere.",
        media_type=MediaType.TEXT,
        reason="retriever test",
        sources=frozenset({SourceId("retriever-doc-2")}),
    ).with_ext(GraphData(entities=(Entity(name="Globex Inc"),), relations=()))
    await store.add([node, other])
    retriever = GraphWalkRetriever(GraphSettings(dsn=SecretStr(_DSN)), GraphWalkConfig(hops=1))

    # Act — the query names "Acme Corp" directly; "Globex Inc" is one hop away.
    outcome = await retriever.run(_query_set("What does Acme Corp do?"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    (ranked,) = outcome.value.lists
    found_ids = {hit.scored.value.id for hit in ranked.hits}
    assert node.id in found_ids
    assert other.id in found_ids
    # The seed node (distance 0) outranks the one-hop node (distance 1).
    by_id = {hit.scored.value.id: hit.scored.score for hit in ranked.hits}
    assert by_id[node.id] > by_id[other.id]


async def test_hops_zero_finds_only_the_seed_entitys_own_nodes() -> None:
    # Arrange
    store = GraphStore(GraphSettings(dsn=SecretStr(_DSN)))
    data = GraphData(
        entities=(Entity(name="Initrode"), Entity(name="Umbrella Corp")),
        relations=(Relation(source="Initrode", target="Umbrella Corp"),),
    )
    node = Node.synthetic(
        content="Initrode meets Umbrella Corp.",
        media_type=MediaType.TEXT,
        reason="retriever test",
        sources=frozenset({SourceId("retriever-doc-3")}),
    ).with_ext(data)
    await store.add([node])
    retriever = GraphWalkRetriever(GraphSettings(dsn=SecretStr(_DSN)), GraphWalkConfig(hops=0))

    # Act
    outcome = await retriever.run(_query_set("Tell me about Initrode."), _ctx())

    # Assert — the one node mentioning the seed is found; nothing wider is walked to.
    assert isinstance(outcome, Produced)
    (ranked,) = outcome.value.lists
    assert {hit.scored.value.id for hit in ranked.hits} == {node.id}
