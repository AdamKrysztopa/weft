"""`weft ask` embedding differently from `weft index` is refused before any comparison.

`weft index` records the embedding identity it wrote with, and `weft ask` embedding any other
way is refused before a vector is compared — ledger task **34.4**, through the real paths.

The case is a width change, because `hash` is the one embedder that runs offline. G22 would also
refuse it, later and in the store's words (`VectorWidthMismatchError`); the identity check must
run first, so the error an operator reads names both identities and the target.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr

from weft_cli.ask import run_ask
from weft_cli.ingest import run_index
from weft_embed import HashEmbedderConfig
from weft_engine.registry_bootstrap import build_dependencies
from weft_engine.targets import EmbeddingIdentityMismatchError
from weft_kernel.context import Context
from weft_store.contract import DEFAULT_TARGET, EmbeddingIdentity
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    """A database of this test's own, created and dropped by exact name (`L22.47`)."""
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_identity_{uuid4().hex[:12]}"
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


async def test_an_index_records_its_identity_and_a_differently_embedded_ask_is_refused(
    dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("WEFT_DATABASE_URL", dsn)
    (tmp_path / "pumps.txt").write_text("Pumps move water uphill using a rotating impeller.")
    deps = build_dependencies(config_path=tmp_path / "weft.toml")
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(dsn)))
    catalogue = await store.target_catalogue()
    await store.aclose()

    # Act / Assert — the identity was recorded by the write, per target.
    by_name = {record.name: record for record in catalogue.targets}
    assert by_name[DEFAULT_TARGET].embedding == EmbeddingIdentity(
        plugin="hash", distribution="weft-rag", model="hash", width=64
    )
    agreeing = await run_ask("what moves water", registry=deps.registry, ctx=_ctx(), top_k=1)
    assert len(agreeing) == 1
    with pytest.raises(EmbeddingIdentityMismatchError) as caught:
        await run_ask(
            "what moves water",
            registry=deps.registry,
            ctx=_ctx(),
            top_k=1,
            embedder_config=HashEmbedderConfig(dimension=128),
        )
    message = str(caught.value)
    assert "width 64" in message
    assert "width 128" in message
    assert "'default'" in message
