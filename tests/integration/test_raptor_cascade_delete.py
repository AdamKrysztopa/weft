"""The proof `10` §1.2's own correction block said was owed — ledger task **10.1**.

That block claims the defect task 2.32 closed: *"RAPTOR summaries built without genealogy
tracking carried `relationships={}` and no deletion path could ever reach them"*, repaired by
building every summary through `Node.combine`, whose `Lineage.sources` is the union of its
members'. Until 2026-09-06 the block also said that was *"proven against a real corpus, real
embeddings and a real store in `tests/integration/test_raptor_pipeline.py`, not merely asserted
of the type"*. It was not: that file asserts the **precondition** — a summary's `sources` equals
the union of its members' — and never deletes anything (`grep -c delete` over it → `0`). The
overclaim was withdrawn (`docs/lessons.md` `L9.38`) and the proof was left owed. This file is it.

**Why a precondition is not the proof, said plainly.** *"A summary's `sources` is the union of
its members'"* and *"deleting a member's source removes the summary"* are two claims joined by a
store's own delete semantics — `weft_store.pgvector_store` deletes a node whose `sources` array
*contains* the id, which is what makes the union sufficient. Nothing in this tree asserted that
join, and a store that deleted on `sources = ARRAY[id]` instead would satisfy the first claim and
fail the second silently. *By construction* is exactly what "not merely asserted of the type"
promised to exceed, and the only way to exceed it is to delete something and look.

**The cluster deliberately spans two documents**, which is the case the claim is actually about:
a summary built from three chunks of `alpha` and one of `beta` names both, so deleting `alpha`
must take the summary with it even though `beta` is untouched — the summary describes content
that is now partly gone, and a partly-true summary left retrievable is the same failure as a
wholly-stale one. `beta`'s own leaf must survive, or the test would pass for the wrong reason.

**Container, no credential, no network.** `hash` for the embedder and `scripted` for the model:
the property under test is the store's cascade over a `Node.combine` lineage, and neither a real
embedding nor a real summary changes it. `similarity_threshold: 0.0` is what puts every node in
one cluster deterministically — the identical device, and the identical reason,
`test_raptor_pipeline.py`'s own docstring gives for it. This test therefore runs in the ordinary
gate, which is where a proof the catalogue cites belongs: the file it cites must be one that
actually ran. An absent container skips with its reason printed rather than passing silently —
`docs/06-phase-0-build.md`'s own rule, repeated here as every module in this directory repeats
it, because each is meant to read as one self-contained scenario.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence

import psycopg
import pytest
from pydantic import SecretStr

from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import NAME as RAPTOR_NAME
from weft_index.raptor import RaptorConfig, RaptorSummarizer
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_kernel.registry import Registry
from weft_llm.client import NullSink, llm_service
from weft_llm.contract import LLM, LLMProvider, TokenSink
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.scripted import NAME as SCRIPTED_NAME
from weft_llm.scripted import ScriptedProvider
from weft_prompts.contract import Prompt, Prompts
from weft_prompts.registry import prompts_service
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

#: The two documents the one cluster is built across. `alpha` is the one deleted.
_ALPHA = SourceId("/corpus/alpha.txt")
_BETA = SourceId("/corpus/beta.txt")


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _leaves(source: SourceId, *contents: str) -> tuple[Node, ...]:
    """`source`'s chunks, built the way a real ingest builds them.

    `Node.synthetic` is the document root an `Extractor` produces — the one place `sources` is
    stated rather than derived — and `derive` is what a `Chunker` calls, which is what carries
    `sources` down to every leaf. Constructing a `Node(...)` directly instead would be refused:
    a parentless node with no `SyntheticOrigin` is exactly the unreachable shape the model
    invariant exists to forbid, and building the fixture through the real factories is what
    keeps this test about the store rather than about a hand-made lineage.
    """
    root = Node.synthetic(
        content="\n\n".join(contents),
        media_type=MediaType.TEXT,
        reason=f"the document root a text extractor produces for {source}",
        sources=frozenset({source}),
    )
    return tuple(
        root.derive(content=content, ordinal=index) for index, content in enumerate(contents)
    )


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
    await instance.count()  # forces schema creation, as every module in this directory does
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield instance
    await instance.aclose()


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


async def _summarised(leaves: Sequence[Node]) -> tuple[Sequence[Node], Node]:
    """Every node a real `raptor` run produced over `leaves`, and the one summary among them."""
    # `similarity_threshold: 0.0` and a `cluster_size` covering the whole slice put every node in
    # one cluster whatever `hash` happens to say about their similarity — see the module
    # docstring. `min_cluster_size: 2` is the shipped default and is kept.
    summariser = RaptorSummarizer(
        RaptorConfig(cluster_size=4, min_cluster_size=2, similarity_threshold=0.0)
    )
    outcome = await summariser.run(leaves, _ctx(_services()))
    assert isinstance(outcome, Produced), f"'{RAPTOR_NAME}' produced nothing to store: {outcome}"
    summaries = [node for node in outcome.value if len(node.lineage.parents) > 1]
    assert len(summaries) == 1, (
        f"this test needs exactly one cluster summary to delete; the run produced "
        f"{len(summaries)}. A threshold of 0.0 against one open cluster is what makes that "
        f"deterministic — if it stopped being, the arrangement is what changed, not the property."
    )
    return outcome.value, summaries[0]


async def test_deleting_one_members_source_removes_the_summary_built_over_it(
    store: PgVectorStore,
) -> None:
    """`10` §1.2's own claim, performed rather than asserted of the type."""
    # Arrange
    produced, summary = await _summarised(
        (
            *_leaves(
                _ALPHA,
                "Alpha opens with a definition of conditional mutual information.",
                "Alpha then states the optimisation problem the method solves.",
                "Alpha closes with the cross-validation procedure it evaluates under.",
            ),
            *_leaves(_BETA, "Beta surveys related global feature selectors and their costs."),
        )
    )
    assert {str(source) for source in summary.lineage.sources} == {str(_ALPHA), str(_BETA)}, (
        "the summary must name both documents, or deleting one of them proves nothing about "
        "the cross-document case this claim is actually about"
    )
    await store.add(produced)
    await store.flush()
    beta_leaf = next(node for node in produced if set(node.lineage.sources) == {_BETA})

    # Act
    removed = await store.delete_source(_ALPHA)

    # Assert
    assert await store.get([summary.id]) == (), (
        f"the summary survived `delete_source({_ALPHA})`. Its `Lineage.sources` names that "
        f"document, so a store deleting on containment must reach it — this is the class of "
        f"node `04` category A found unreachable by every deletion path, and the repair is only "
        f"real if the store's own semantics complete it."
    )
    assert removed.node_count >= 1, (
        f"`delete_source` reported removing {removed.node_count} node(s), so nothing says the "
        f"cascade did any work at all"
    )
    survivors = await store.get([beta_leaf.id])
    assert [node.id for node in survivors] == [beta_leaf.id], (
        "beta's own leaf was deleted too. Cascade must reach the summary because it names "
        "alpha, and must not reach a node that only names beta — a delete that removed "
        "everything would pass the assertion above for the wrong reason."
    )


async def test_a_summary_whose_only_source_is_deleted_leaves_nothing_behind(
    store: PgVectorStore,
) -> None:
    """The single-document case, and the store's own count as the second reading.

    `store.count()` is asked rather than `get` alone because `get` answers about ids this test
    already holds, and the failure `04` category A describes is a node **nobody holds an id
    for**: a summary left behind after its documents are gone is exactly the row a caller can
    no longer name. A count of zero is the only assertion that can see it.
    """
    # Arrange
    produced, _ = await _summarised(
        _leaves(
            _ALPHA,
            "Alpha opens with a definition of conditional mutual information.",
            "Alpha then states the optimisation problem the method solves.",
        )
    )
    await store.add(produced)
    await store.flush()
    assert await store.count() == len(produced)

    # Act
    await store.delete_source(_ALPHA)

    # Assert
    assert await store.count() == 0, (
        "deleting the one document every node came from left rows in the store. A summary that "
        "outlives every document it describes is `04` category A's own failure, and no caller "
        "holds an id to find it with."
    )
