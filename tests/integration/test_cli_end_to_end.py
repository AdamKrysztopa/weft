"""The Phase 0 step 9 exit test: `weft index` then `weft ask`, against the real container.

`docs/06-phase-0-build.md` step 9 — "Makes true: the product runs end to
end." This is that end-to-end: `weft_cli.registry_bootstrap.build_dependencies`
discovers the real, installed packs; `weft_cli.ingest.run_index` indexes a
small directory of text files into pgvector; `weft_cli.ask.run_ask` retrieves
the passage that answers a question about that same content, by hash-vector
distance — not by any real semantic understanding, see
`weft_embed.hash_embedder`'s own docstring for why that is honestly labelled
rather than merely reused.

Against the real container — `docs/06-phase-0-build.md`: "Integration tests
must run against the real container, not a mock, and must be skipped with a
clear reason — never silently passed — when it is absent." The skip
discipline mirrors `tests/integration/test_ingest_pipeline.py` and
`tests/unit/weft_store/test_pgvector_store.py` exactly, repeated here rather
than shared for the same reason: this is the one test that should read as a
single, self-contained scenario proving the CLI's own composition, not the
kernel's.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr

from weft_cli.ask import run_ask
from weft_cli.ingest import run_index
from weft_cli.registry_bootstrap import build_dependencies
from weft_kernel.context import Context
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def _database_reachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await conn.close()
    return None


@pytest.fixture
async def clean_database() -> AsyncIterator[None]:
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    # Schema creation is lazy, on a store's first real connection (weft_store.pgvector_store) —
    # so a database nothing has touched yet has neither table. Force it through the public API
    # before truncating, exactly as tests/integration/test_ingest_pipeline.py's own fixture does.
    schema_forcer = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await schema_forcer.count()
    await schema_forcer.aclose()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield


async def test_index_then_ask_retrieves_the_indexed_passage(
    clean_database: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del clean_database
    # Arrange — a small directory of source documents, one of them distinctive. WEFT_DATABASE_URL
    # is set explicitly rather than relied upon from the shell: weft_cli.registry_bootstrap's
    # `pack_settings_from_environment` only references it (`${env:WEFT_DATABASE_URL}`) when it
    # is present — so this is what makes 'weft-store' resolve to an ACTIVE pack at all.
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    (tmp_path / "fox.txt").write_text("The quick brown fox jumps over the lazy dog.")
    (tmp_path / "notes.md").write_text("# Notes\n\nWeft is a microkernel RAG engine.")
    deps = build_dependencies(config_path=tmp_path / "weft.toml")  # no config file — open posture

    # Act
    index_result = await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    results = await run_ask(
        "The quick brown fox jumps over the lazy dog.", registry=deps.registry, ctx=_ctx(), top_k=1
    )

    # Assert — indexing produced stored nodes, and asking the exact indexed sentence finds it
    # as the single nearest match: HashEmbedder is deterministic, so identical content hashes
    # to an identical vector and distance-to-self is the closest any result can be.
    assert index_result.summary.produced == 1
    assert index_result.stored_count is not None
    assert index_result.stored_count > 0
    assert len(results) == 1
    assert "quick brown fox" in results[0].value.content
