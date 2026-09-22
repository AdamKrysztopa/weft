"""A store that holds nothing takes no part in a promote — carried repair **R34.5**.

Found running Phase 34's exit on Qdrant. The project configures pgvector too (`[packs.store] dsn`)
and indexes through a pipeline that replaces `index-text`'s pgvector store with Qdrant. Target
participants were `stores_in_use`, which deliberately reaches every store a project's documents
name, `index-text`'s pgvector included, for delete and reconcile. So an empty pgvector refused the
promote (`"w128 (on 'pgvector')" is not a target this store holds`), and after one would have made
every read report the stores as disagreeing. A store that holds no source and no target beyond
`default` has nothing to move.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from weft_cli.commands import AskCommandResult
from weft_engine.api import Weft

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_QDRANT_URL = os.environ.get("WEFT_QDRANT_URL", "http://localhost:6333")


@pytest.fixture
async def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    client = AsyncQdrantClient(url=_QDRANT_URL, timeout=2)
    try:
        await client.info()
    except (OSError, ValueError, UnexpectedResponse, ResponseHandlingException) as exc:
        await client.close()
        pytest.skip(
            f"WEFT_QDRANT_URL ({_QDRANT_URL}) is unreachable: {exc}. `docker compose up -d`."
        )
    admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    name = f"weft_participants_{uuid4().hex[:12]}"
    collection = f"weft_participants_{uuid4().hex[:12]}"
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "pumps.txt").write_text("Pumps move water uphill.", encoding="utf-8")
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / "narrow.yaml").write_text(
        "name: narrow\nextends: index-text\nreplace:\n  - id: store\n    use: qdrant\n",
        encoding="utf-8",
    )
    dsn = f"{_DSN.rsplit('/', 1)[0]}/{name}"
    (tmp_path / "weft.toml").write_text(
        f'[packs.store]\ndsn = "{dsn}"\n\n[services]\nstore = "qdrant"\n\n'
        f'[packs.qdrant]\ncollection = "{collection}"\n'
    )
    try:
        yield tmp_path
    finally:
        for suffix in ("", "__sources", "__targets", "__t_w2", "__t_w2__sources"):
            if await client.collection_exists(collection + suffix):
                await client.delete_collection(collection + suffix)
        await client.close()
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


async def test_an_empty_store_neither_blocks_a_promote_nor_disagrees_after_it(
    project: Path,
) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        await w.run("index", {"path": "corpus", "pipeline": "narrow"})
        await w.run("index", {"path": "corpus", "pipeline": "narrow", "target": "w2"})

        # Act
        promoted = await w.run("target promote", {"name": "w2", "without_evidence": True}, yes=True)
        answered = await w.run("ask", {"question": "what moves water", "retrieve_only": True})

    # Assert
    assert promoted is not None
    assert isinstance(answered, AskCommandResult)
    assert answered.hits
