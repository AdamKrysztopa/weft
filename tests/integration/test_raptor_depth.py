"""A tree deeper than one level, built by a shipped pipeline document — ledger task **10.7**.

`10` §1.2 and `weft_index.raptor`'s own docstring have said since task 2.32 that chaining
`raptor` stages *"does not yet build a correct deeper tree"*, because the linear runner threads
each stage's whole output into the next and nothing filtered: a second stage would cluster a leaf
together with the summary already built from it. `index-with-raptor.yaml` recorded that depth
would be *"demonstrated by a new derived document rather than by restoring this sentence"*, and
this file is where that document is demonstrated.

**Why an integration test and not three unit tests.** The unit tests beside `weft_index.raptor`
prove the plugin selects one level and stops on a thin one. What they cannot show is that a
**document** an operator can actually write produces the tree — that the second rung's payload is
what the first rung returned, that no `embed` stage is needed between them (since task 10.4 the
plugin embeds its own summaries, so one would re-bill every node), and that both levels land in a
store where a filter can tell them apart. That is a claim about the runner, the resolution model
and the store together, and only a real run makes it.

**Container, no credential, no network** — `hash` and `scripted`, with `similarity_threshold: 0.0`
so clustering is deterministic and both levels form reliably. An absent container skips with its
reason printed rather than passing silently.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr

from weft_cli.compile import contracts_for
from weft_cli.ingest import run_index
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.registry_bootstrap import build_dependencies
from weft_index.payload import RaptorFacts
from weft_kernel.context import Context
from weft_kernel.resolution import resolve
from weft_store.contract import Filter, FilterOp
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

#: The shipped document this task adds. Named here so the test fails loudly if it is renamed
#: rather than silently testing whatever else happens to resolve.
_DEEP = "index-with-deep-raptor"

#: The document the *end-to-end* test actually runs — `_DEEP` derived, with thresholds widened
#: so that `hash` vectors cluster at all.
#:
#: **The demonstration values live here and not in the shipped rung, on purpose.** `_DEEP`
#: inherits `similarity_threshold: 0.75` from its parent, which no `hash` vector clears, so it
#: builds nothing under the default embedder — the same honest silence `index-with-raptor.yaml`
#: measured and recorded. Widening it to `0.0` makes everything cluster with everything, which is
#: what this test needs and is the last thing a *shipped* rung should do by default: it would
#: produce confident summaries over meaningless groupings the first time anyone ran it flagless
#: (`docs/lessons.md` L9.64), which is the failure ledger task 10.9's degeneracy check exists to
#: refuse. A derived document is exactly what an operator would write, so the test writes one.
_DEMO = "deep-raptor-demonstration"
_LEVEL_FIELD = f"ext.{RaptorFacts.__namespace__}.level"


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


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _corpus(directory: Path) -> None:
    """Six short passages in two clearly separate topics, so both levels form deterministically.

    Content matters here in a way it usually does not: `hash` vectors carry no semantic
    similarity, so `similarity_threshold: 0.0` in the deep document is what makes clustering
    depend on nothing but the arrangement. Six chunks at `cluster_size: 2` give three level-1
    summaries, which are enough for a level-2 rung to have something to cluster.
    """
    for index in range(6):
        (directory / f"passage-{index}.txt").write_text(
            f"Passage {index}. " + "Conditional mutual information and feature selection. " * 40,
            encoding="utf-8",
        )


async def test_a_shipped_document_builds_two_levels_a_filter_can_tell_apart(
    store: PgVectorStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Exit's own first clause, at the smallest scale that can show it.

    What the store is asked is not *"is there a deeper node"* but *"can a filter select the
    levels apart"* — because that is what 10.8 and any query rung need, and a level nothing can
    select on is a field rather than an interface. **One `embed` and two `raptor` rungs**: since
    task 10.4 the plugin embeds the summaries it writes, so a second `embed` between the rungs
    would re-embed every leaf and every level-1 summary, which is the doubled bill 10.4 removed.
    """
    # Arrange — a project-local derivation, found the way `weft` finds one: `pipelines/` relative
    # to the working directory (`weft_cli.pipeline_catalogue.DEFAULT_PIPELINES_DIR`).
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    monkeypatch.chdir(tmp_path)
    _corpus(tmp_path)
    (tmp_path / "weft.toml").write_text(
        '[llm.roles]\nindex = { provider = "scripted" }\n', encoding="utf-8"
    )
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / f"{_DEMO}.yaml").write_text(
        f"name: {_DEMO}\n"
        f"extends: {_DEEP}\n"
        "set:\n"
        # `max_cluster_chars` is small because the `scripted` provider echoes its own last user
        # turn back, and `weft_llm.loop_guard` refuses a completion whose content repeats — which
        # a deliberately repetitive corpus triggers unless the rendered cluster stays short.
        "  - {id: summarise, with: {cluster_size: 2, similarity_threshold: 0.0, "
        "max_cluster_chars: 100}}\n"
        "  - {id: summarise-deeper, with: {over_level: 1, cluster_size: 2, "
        "min_cluster_size: 2, similarity_threshold: 0.0, max_cluster_chars: 100}}\n",
        encoding="utf-8",
    )
    deps = build_dependencies(config_path=tmp_path / "weft.toml")

    # Act
    await run_index(
        tmp_path,
        registry=deps.registry,
        ctx=_ctx(),
        pipeline=_DEMO,
        reports=deps.reports,
        llm=deps.llm,
        sink=deps.token_sink,
        services=deps.services,
        roles=deps.roles,
    )

    # Assert — both levels exist, and a filter tells them apart.
    level_one = await store.matching(Filter(op=FilterOp.EQ, field=_LEVEL_FIELD, value=1))
    level_two = await store.matching(Filter(op=FilterOp.EQ, field=_LEVEL_FIELD, value=2))
    assert level_one.items, "the first rung built no level at all"
    assert level_two.items, (
        "no level-2 node exists, so this document builds one level and 10.7 is not done. The "
        "second rung consumes `over_level: 1`; if the first rung produced fewer than "
        "`min_cluster_size` summaries there was nothing for it to cluster, which is the stop "
        "rule working rather than the tree failing — enlarge the corpus, do not weaken this."
    )
    assert not ({node.id for node in level_one.items} & {node.id for node in level_two.items})
    for node in level_two.items:
        parents = {parent for parent in node.lineage.parents}
        assert parents <= {item.id for item in level_one.items}, (
            "a level-2 summary names a parent that is not a level-1 node — the second rung "
            "clustered something other than the level below it, which is the defect this "
            "document exists to not have"
        )


def test_the_deep_document_resolves_to_two_raptor_rungs_and_one_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The document's own shape, before anything runs it.

    **One `embed`, two `raptor` stages** — not `embed, raptor, embed, raptor`. Since task 10.4
    `raptor` embeds the summaries it writes, so a second `embed` between the rungs would re-embed
    every leaf and every level-1 summary: neither shipped `Embedder` skips a node that already
    carries a vector, so that is the doubled bill 10.4 removed, reintroduced. The catalogue's own
    illustrative chain said otherwise until 10.6 corrected it.
    """
    # Arrange — the same two calls `weft pipeline show` makes, so this reads the document the
    # way an operator's own invocation does rather than by parsing the file. The DSN is set
    # because the `store` pack refuses to register without one and `pgvector` would then be an
    # unknown plugin name; nothing here connects, so this test needs no container.
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    deps = build_dependencies(config_path=Path("weft.toml"))
    catalogue = full_catalogue(reports=deps.reports)
    pipeline = catalogue[_DEEP]

    # Act
    resolved = resolve(
        pipeline,
        registry=deps.registry,
        contracts=contracts_for(
            pipeline,
            registry=deps.registry,
            parents=catalogue,
            contributions=deps.contributions,
        ),
        parents=catalogue,
        contributions=deps.contributions,
    )

    # Assert
    uses = [stage.use for stage in resolved.stages]
    assert uses.count("raptor") == 2, f"expected two `raptor` rungs, got {uses}"
    assert uses.count("hash") == 1, (
        f"expected exactly one embed stage — a second would re-bill every node — got {uses}"
    )
    # `ResolvedStage.config` is typed `object` by kernel design — it holds any plugin's own
    # config model — so the value is read through `getattr` into an explicitly typed list rather
    # than off an attribute pyright cannot know about. A `# type: ignore` on the access line does
    # not reach the comprehension's own assignment, which is where strict mode objects.
    levels: list[object] = [
        getattr(stage.config, "over_level", None)
        for stage in resolved.stages
        if stage.use == "raptor"
    ]
    assert levels == [0, 1], (
        f"the rungs must consume level 0 then level 1, in that order; got {levels}"
    )
