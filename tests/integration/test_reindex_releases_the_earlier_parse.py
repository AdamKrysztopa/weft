"""Re-indexing a document releases the nodes its previous parse left — ledger task **27.2**.

`L9.37`'s half of the one cause Phase 27 exists to fix, and the direction opposite to `27.1`'s.
There, two documents produced the *same* node id and one took the other's nodes. Here, one
document produces *different* ids on a second parse — node ids are content digests, so a changed
document or a changed pipeline yields a wholly new set, `ON CONFLICT (id)` never fires, and both
parses' nodes sit in the store together, both retrievable, while the single `SourceRecord` is
overwritten so nothing records that the corpus was built two ways. Not *"the first parse wins"* —
**both win and the evidence is gone**.

**It was measured before it was fixed, twice.** `weft_cli.ingest.changes_against_records` says so
in its own docstring — *"It reports; it removes nothing… that is `L9.37`'s finding and it owes a
task of its own"* — and Phase 11's exit run counted the drift: **23 nodes and 5 relations before
four `weft eval` invocations, 42 and 11 after** (`L11.46`), because that harness always indexes
and the pipeline it ran called a model, which rephrases on every pass.

**Release before the run, not after, and that is not `supersede`'s hazard.** `02` §1 settles the
opposite ordering for `supersede` — write the new node, delete the old, because an interruption
must leave a *duplicate* that `reconcile` can find rather than a *hole* that nothing can. The
reasoning does not transfer, because the two failures are not comparable: a superseded node's
`BlobRef` points at bytes no longer reachable from anywhere, while a document released and not
re-indexed still exists **on disk**, has no `SourceRecord`, and is therefore `NEW` to the next
`weft index` over the same directory, which rebuilds it. The corpus is derived data and the
directory is the truth, so the crash window self-heals on the next run. Releasing *after* the run
would need the set of ids this pass produced, and `RunSummary` carries counts, not ids.

**Only a document that actually changed is released.** `NEW` has nothing to release and
`UNCHANGED` must not be touched — re-indexing an unchanged corpus is the common path, `02` §1
calls its idempotence the point of content-addressed ids, and a release-and-rewrite there would
churn every node in the store to arrive back where it started.

**An integration test against the real store rather than a unit test with a double**, for the
reason `test_ingest_records_sources.py` gives at length: the defect this repairs lived for phases
behind a corpus double that answered a question the running system could not (`L6.14`). The
subject is the actual ingest path writing to an actual `PgVectorStore`, read back through the
published contract.

**The container skip below is this directory's own convention, not a new escape hatch.** Every
module here opens with the identical `_database_reachable`/`pytest.skip(reason)` pair, and the
wording is load-bearing: `tests/conftest.py` matches the substring `is unreachable` to fail a run
whose `WEFT_DATABASE_URL` claims a database that then turns out not to answer, so a container
brought down mid-run cannot quietly shrink the suite (`L7.8`). A skip that did not say this would
be the silent pass that rule exists to prevent.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr

from weft_cli.ingest import run_index
from weft_cli.registry_bootstrap import build_dependencies
from weft_kernel.context import Context
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

_FIRST_PARSE = "The quick brown fox jumps over the lazy dog."
_SECOND_PARSE = "A wholly different sentence, sharing not one clause with the first."


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def _database_reachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`."
    await conn.close()
    return None


@pytest.fixture
async def clean_database() -> AsyncIterator[None]:
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    schema_forcer = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await schema_forcer.count()
    await schema_forcer.aclose()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources, weft_node_productions")
    await conn.close()
    yield


@pytest.fixture
async def store() -> AsyncIterator[PgVectorStore]:
    instance = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    yield instance
    await instance.aclose()


async def _contents(store: PgVectorStore) -> frozenset[str]:
    """Every stored node's content, read through the published contract rather than by SQL."""
    return frozenset(node.content for node in (await store.scan()).items)


async def test_a_changed_document_leaves_none_of_its_earlier_parse_behind(
    clean_database: None,
    store: PgVectorStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`L9.37` stated as a property: after re-indexing, the old parse is not retrievable.

    The assertion is on **content**, not on a count. A count can be right while the wrong nodes
    are present — two parses of one document happen to produce one node each here, so
    `count() == 1` would pass against a store holding only the stale one.
    """
    # Arrange
    del clean_database
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    document = tmp_path / "fox.txt"
    document.write_text(_FIRST_PARSE)
    deps = build_dependencies(config_path=tmp_path / "weft.toml")
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    assert _FIRST_PARSE in await _contents(store), "the fixture must index before it re-indexes"

    # Act
    document.write_text(_SECOND_PARSE)
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())

    # Assert
    stored = await _contents(store)
    assert _SECOND_PARSE in stored
    assert _FIRST_PARSE not in stored, (
        "the earlier parse is still retrievable — node ids are content digests, so the new "
        "parse never overwrote the old one and both are in the store"
    )


async def test_re_indexing_an_unchanged_document_releases_nothing(
    clean_database: None,
    store: PgVectorStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The negative case, and the one a release-everything repair would break silently.

    Asserted on the node **ids**, not on the count: a release-and-rewrite arrives back at the
    same count and the same content, because the ids are digests of that content. What it must
    not do is churn — and the only way to see that from outside is that the identical ids are
    still there, never having been deleted.
    """
    # Arrange
    del clean_database
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    (tmp_path / "fox.txt").write_text(_FIRST_PARSE)
    deps = build_dependencies(config_path=tmp_path / "weft.toml")
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    before = frozenset(node.id for node in (await store.scan()).items)
    assert before, "the fixture must index something for this to be about anything"

    # Act
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())

    # Assert
    assert frozenset(node.id for node in (await store.scan()).items) == before
    [record] = await store.list_sources()
    assert record.id.endswith("fox.txt")


async def test_releasing_a_changed_document_leaves_a_node_another_one_still_produces(
    clean_database: None,
    store: PgVectorStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`27.2` meeting `27.1`, and neither half is safe without the other.

    Two byte-identical documents share one node with two productions (`27.1`). Changing one of
    them must release *its* production and leave the node standing for the other — a release
    that deleted by source would take a passage the untouched document still holds, which is the
    exact loss `27.1` was built to stop, reintroduced one layer up on the ingest path.
    """
    # Arrange — identical bytes at two paths, then one of them edited.
    del clean_database
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    alpha, beta = tmp_path / "alpha.txt", tmp_path / "beta.txt"
    alpha.write_text(_FIRST_PARSE)
    beta.write_text(_FIRST_PARSE)
    deps = build_dependencies(config_path=tmp_path / "weft.toml")
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    assert await store.count() == 1, "the fixture must exercise the collision, not avoid it"

    # Act
    alpha.write_text(_SECOND_PARSE)
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())

    # Assert — both parses are present, and the shared node now belongs to `beta` alone.
    stored = {node.content: node for node in (await store.scan()).items}
    assert frozenset(stored) == frozenset({_FIRST_PARSE, _SECOND_PARSE})
    assert stored[_FIRST_PARSE].lineage.sources == frozenset({str(beta)})
    assert stored[_SECOND_PARSE].lineage.sources == frozenset({str(alpha)})
