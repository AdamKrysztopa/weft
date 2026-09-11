"""The level is a **stored** fact a filter can select on — ledger task **10.6**.

The unit tests beside `weft_index.raptor` prove a summary *states* its level. That is half the
property and the easy half: a field on a frozen model in memory is not a fact a query rung can
act on. What 10.6 asks for is that the level survive the round trip into a real store and come
back as something `MetadataFilter.matching` can narrow by, because that is what 10.7 will filter
on to build each level from the previous level's nodes alone, and what a query rung would filter
on to ask for abstractions and not passages.

**Why this cannot be a unit test.** `ext` is written as JSONB and read back through
`weft_store.rehydrate`, which reconstructs a pack's own model only if that pack registered it
(`add_ext_model`). A stub store that hands the object back untouched proves nothing about either
half, and `docs/internal/lessons.md` L6.14 is this project's own worked example of a hand-written
double answering a question the running system could not.

**Container, no credential, no network** — `hash` and `scripted`, `similarity_threshold: 0.0` so
one cluster forms deterministically, exactly as `test_raptor_cascade_delete.py` argues for its
own arrangement. An absent container skips with its reason printed rather than passing silently.
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
from weft_kernel.payload import ExtModel, MediaType, Node, Produced, SourceId
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
_SOURCE = SourceId("/corpus/levels.txt")

#: The dotted path a pipeline document would write. `raptor-and-leaves-rrf.yaml` already filters
#: on `ext.weft-index.technique`, so this is the same grammar one namespace over — which is the
#: point of keeping the level *beside* `Representation` rather than inside it.
_LEVEL_FIELD = f"ext.{RaptorFacts.__namespace__}.level"


def _ensure_rehydrates(*models: type[ExtModel]) -> None:
    """Register `models` for read-back, as `weft_index.register`'s own `add_ext_model` calls do
    once discovery has run.

    This test composes a slice of stages by hand rather than discovering the pack, so nothing has
    told `weft_store.rehydrate` which class owns which namespace — and without that a stored
    `ext` value comes back as a plain mapping. `test_raptor_pipeline.py` carries the identical
    helper for the identical reason. The failure it prevents is worth naming: the first draft of
    this file omitted it and `store.get` raised `UnknownPluginError` naming the namespace, which
    is the registration seam refusing loudly rather than handing back JSON nobody owns.
    """
    reports = tuple(
        PackReport(
            pack=model.__namespace__,
            distribution=model.__namespace__,
            status=PackStatus.ACTIVE,
            ext_models=(model,),
        )
        for model in models
    )
    register_from_reports(reports)


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


async def _indexed(store: PgVectorStore) -> Sequence[Node]:
    """Two leaves and the one summary over them, embedded and stored — a real ingest's shape."""
    root = Node.synthetic(
        content="one",
        media_type=MediaType.TEXT,
        reason="the document root a text extractor produces",
        sources=frozenset({_SOURCE}),
    )
    leaves = (
        root.derive(content="Conditional mutual information is defined here.", ordinal=0),
        root.derive(content="The optimisation problem the method solves.", ordinal=1),
    )
    _ensure_rehydrates(RaptorFacts, Representation)
    services = _services()
    embedded = await HashEmbedder().run(leaves, _ctx(services))
    assert isinstance(embedded, Produced)
    outcome = await RaptorSummarizer(
        RaptorConfig(cluster_size=4, min_cluster_size=2, similarity_threshold=0.0)
    ).run(embedded.value, _ctx(services))
    assert isinstance(outcome, Produced), outcome
    await store.add(outcome.value)
    await store.flush()
    return outcome.value


async def test_the_level_selects_the_summary_and_nothing_else(store: PgVectorStore) -> None:
    """`ext.weft-index-raptor.level == 1` narrows a real store to the abstractions."""
    # Arrange
    produced = await _indexed(store)
    summaries = [node for node in produced if len(node.lineage.parents) > 1]
    assert len(summaries) == 1
    assert await store.count() == 3, "two leaves and one summary should be in the store"

    # Act
    page = await store.matching(Filter(op=FilterOp.EQ, field=_LEVEL_FIELD, value=1))

    # Assert
    assert [node.id for node in page.items] == [summaries[0].id], (
        f"filtering on '{_LEVEL_FIELD} == 1' returned {len(page.items)} node(s). The level is "
        f"only an interface if a filter can select on it after a round trip through a store; in "
        f"memory it is a field on a frozen model and 10.7 cannot use it."
    )


async def test_the_level_comes_back_as_the_pack_s_own_model(store: PgVectorStore) -> None:
    """Read back, not merely written. `weft_store.rehydrate` reconstructs a pack's `ExtModel`
    only for a namespace some pack registered through `add_ext_model`; without that registration
    the value returns as a plain mapping and every reader downstream has to know it. Asserting
    the *type* is what checks the registration, which is the half a write-only test misses
    (`docs/internal/lessons.md` L6.14's shape).
    """
    # Arrange
    produced = await _indexed(store)
    summary = next(node for node in produced if len(node.lineage.parents) > 1)

    # Act
    fetched = await store.get([summary.id])

    # Assert
    assert len(fetched) == 1
    facts = fetched[0].ext_as(RaptorFacts)
    assert facts is not None, (
        f"'{RaptorFacts.__namespace__}' did not rehydrate into {RaptorFacts.__name__}. The pack "
        f"registers it through `add_ext_model`; without that the level is JSON nobody owns."
    )
    assert facts.level == 1
    assert facts.members == 2
