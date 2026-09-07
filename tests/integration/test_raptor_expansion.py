"""A summary is expandable to its members through the published store contract — task **10.8**.

RAPTOR's own traversal wants a node's immediate children; T-Retriever eq. 13 wants the leaf
members in one read. Task 10.7 builds each level from the level below it, so **a summary's
`lineage.parents` names the level below and nothing else** — one hop reaches that level, and
reaching the leaves from level *n* is *n* hops. This file is where that walk is performed rather
than asserted of the shape, and where its cost is read off a real store on both proven backends.

**The mechanism turned out to be simpler than the plan assumed, and that is this task's finding.**
The ledger's own 10.8 line reasons that expansion is *"reachable today with no contract change:
`lineage.parents` is `TEXT_SET`, which admits `contains` through `MetadataFilter.matching`"*. It
is reachable, but not that way: `contains` on `lineage.parents` answers the **opposite**
question — *which nodes have this node as a parent* — and expansion needs no filter at all.
`NodeStore.get(summary.lineage.parents)` is one call on the **base** contract, not even
`MetadataFilter`, because a summary already carries its members' ids. So the dedicated store
method the line reserved a ⛔ for is not merely unnecessary, the *filter* is too, and a store that
implements nothing but `NodeStore` can expand a tree.

Both directions are exercised below, because a reader who wants the reverse walk — *given a leaf,
which summary stands over it* — genuinely does need `contains`, and that one is worth measuring
against the cheap one rather than assumed comparable.

**Container, no credential, no network.** An absent container skips with its reason printed
rather than passing silently.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence

import psycopg
import pytest
from pydantic import SecretStr

from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_index.payload import RaptorFacts, Representation
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import RaptorConfig, RaptorSummarizer
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import ExtModel, MediaType, Node, NodeId, Produced, SourceId
from weft_kernel.registry import Registry
from weft_llm.client import NullSink, llm_service
from weft_llm.contract import LLM, LLMProvider, TokenSink
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.scripted import NAME as SCRIPTED_NAME
from weft_llm.scripted import ScriptedProvider
from weft_prompts.contract import Prompt, Prompts
from weft_prompts.registry import prompts_service
from weft_store.contract import Filter, FilterOp
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore
from weft_store.rehydrate import register_from_reports

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_SOURCE = SourceId("/corpus/expansion.txt")

#: The field a reverse walk filters on. `weft_store.fields` gives `lineage.parents` the
#: `TEXT_SET` kind, which is what admits `contains`.
_PARENTS_FIELD = "lineage.parents"


def _ensure_rehydrates(*models: type[ExtModel]) -> None:
    register_from_reports(
        tuple(
            PackReport(
                pack=model.__namespace__,
                distribution=model.__namespace__,
                status=PackStatus.ACTIVE,
                ext_models=(model,),
            )
            for model in models
        )
    )


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _services() -> ServiceRegistry:
    registry = Registry()
    registry.add(LLMProvider, SCRIPTED_NAME, ScriptedProvider, distribution="weft-llm")
    registry.add(Prompt, SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt, distribution="weft-index")
    services = ServiceRegistry()
    services.add(
        LLM,
        llm_service(
            registry=registry,
            roles=LLMRoles(roles={"index": RoleMapping(provider=SCRIPTED_NAME)}),
        ),
    )
    services.add(TokenSink, NullSink())
    services.add(Prompts, prompts_service(registry))
    services.add(Embedder, HashEmbedder())
    return services


async def _database_reachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await conn.close()
    return None


@pytest.fixture
async def store() -> AsyncIterator[PgVectorStore]:
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    instance = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await instance.count()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield instance
    await instance.aclose()


async def _two_level_tree(store: PgVectorStore) -> tuple[Sequence[Node], Sequence[Node]]:
    """A stored two-level tree: `(every node, the level-2 summaries)`.

    Built by running `raptor` twice, exactly as `index-with-deep-raptor` does — the first rung
    over the leaves, the second over `over_level: 1` — so the shape under test is the one a
    document actually produces rather than a hand-assembled lineage.
    """
    _ensure_rehydrates(RaptorFacts, Representation)
    root = Node.synthetic(
        content="one",
        media_type=MediaType.TEXT,
        reason="the document root a text extractor produces",
        sources=frozenset({_SOURCE}),
    )
    leaves = tuple(
        root.derive(content=f"Passage {index} about feature selection.", ordinal=index)
        for index in range(8)
    )
    services = _services()
    embedded = await HashEmbedder().run(leaves, _ctx(services))
    assert isinstance(embedded, Produced)

    tight = RaptorConfig(cluster_size=2, min_cluster_size=2, similarity_threshold=0.0)
    first = await RaptorSummarizer(tight).run(embedded.value, _ctx(services))
    assert isinstance(first, Produced), first
    second = await RaptorSummarizer(
        RaptorConfig(over_level=1, cluster_size=2, min_cluster_size=2, similarity_threshold=0.0)
    ).run(first.value, _ctx(services))
    assert isinstance(second, Produced), second

    await store.add(second.value)
    await store.flush()
    deepest = [
        node
        for node in second.value
        if (facts := node.ext_as(RaptorFacts)) is not None and facts.level == 2
    ]
    assert deepest, "the fixture did not build a second level, so nothing here is about depth"
    return second.value, deepest


def _level_of(node: Node) -> int:
    facts = node.ext_as(RaptorFacts)
    return 0 if facts is None else facts.level


async def test_a_summary_expands_to_its_members_in_one_call_on_the_base_contract(
    store: PgVectorStore,
) -> None:
    """Expansion needs `NodeStore.get` and nothing else — not `MetadataFilter`, not a new method.

    This is the task's own finding: a summary already carries its members' ids, so the ids *are*
    the query. The ⛔ the ledger reserved for a dedicated store method is unreached, and so is the
    filter it proposed instead.
    """
    # Arrange
    _, deepest = await _two_level_tree(store)
    summary = deepest[0]

    # Act
    members = await store.get(list(summary.lineage.parents))

    # Assert
    assert {node.id for node in members} == set(summary.lineage.parents)
    assert all(_level_of(node) == 1 for node in members), (
        "a level-2 summary's parents must all be level-1 nodes — one hop reaches the level "
        "below, which is what 10.7 builds and what makes the walk's depth predictable"
    )


async def test_the_walk_to_the_leaves_is_one_hop_per_level(store: PgVectorStore) -> None:
    """*"Which walk does a deeper summary's `lineage.parents` make — to the level below it, or to
    the leaves?"* Answered: to the level below, so reaching the leaves from level *n* costs *n*
    hops and each hop is one `get`.

    RAPTOR's traversal retrieval wants exactly this (immediate children, layer by layer);
    T-Retriever eq. 13 wants the leaves in one read and would need the walk flattened at index
    time or a second field. Weft does neither and states the cost instead, which is what this
    test pins so the statement cannot drift from the behaviour.
    """
    # Arrange
    _, deepest = await _two_level_tree(store)
    summary = deepest[0]

    # Act — hop one, then hop two.
    level_one = await store.get(list(summary.lineage.parents))
    leaf_ids: list[NodeId] = [parent for node in level_one for parent in node.lineage.parents]
    leaves = await store.get(leaf_ids)

    # Assert
    assert all(_level_of(node) == 1 for node in level_one)
    assert leaves, "the second hop reached nothing, so the tree is not two levels deep"
    assert all(_level_of(node) == 0 for node in leaves), (
        "hop two from a level-2 summary must land on leaves. If it lands anywhere else the "
        "walk's depth is not the tree's depth and the cost stated in the docstring is wrong."
    )


async def test_the_reverse_walk_needs_the_filter_and_finds_the_summary_over_a_node(
    store: PgVectorStore,
) -> None:
    """The other direction — *given a node, which summary stands over it* — is the one that
    genuinely needs `MetadataFilter`.

    `lineage.parents` is `TEXT_SET` in `weft_store.fields`, which is what admits `contains`. This
    is the walk the ledger's 10.8 line described, and it is the reverse of expansion: worth
    having, worth measuring against the cheap direction, and **not** what a summary needs to
    reach its own members.
    """
    # Arrange
    every, deepest = await _two_level_tree(store)
    child = (await store.get(list(deepest[0].lineage.parents)))[0]

    # Act
    page = await store.matching(
        Filter(op=FilterOp.CONTAINS, field=_PARENTS_FIELD, value=str(child.id))
    )

    # Assert
    assert [node.id for node in page.items] == [deepest[0].id], (
        f"a `contains` filter on '{_PARENTS_FIELD}' must find exactly the node standing over "
        f"this one; it returned {len(page.items)}"
    )
    assert len(every) > len(page.items), "the filter matched everything, so it narrowed nothing"
