"""After a candidate built by a configured embedder is live, `weft ask` answers from it once
`[services.embed_config]` states that configuration — carried repair **R34.4**, end to end."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from weft_cli.commands import AskCommandResult
from weft_engine.api import Weft
from weft_engine.targets import EmbeddingIdentityMismatchError

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_embed_config_{uuid4().hex[:12]}"
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


async def test_a_wide_index_is_asked_once_the_query_embedder_is_configured_to_match(
    dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — an index built at width 128 through a pipeline document.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "pumps.txt").write_text("Pumps move water uphill.", encoding="utf-8")
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / "wide.yaml").write_text(
        "name: wide\nextends: index-text\nset:\n  - id: embed\n    with: {dimension: 128}\n",
        encoding="utf-8",
    )
    plain = f'[packs.store]\ndsn = "{dsn}"\n'
    (tmp_path / "weft.toml").write_text(plain)
    async with Weft.open(tmp_path / "weft.toml") as w:
        await w.run("index", {"path": "corpus", "pipeline": "wide"})
        with pytest.raises(EmbeddingIdentityMismatchError):
            await w.run("ask", {"question": "what moves water", "retrieve_only": True})

    # Act
    (tmp_path / "weft.toml").write_text(plain + "\n[services.embed_config]\ndimension = 128\n")
    async with Weft.open(tmp_path / "weft.toml") as w:
        answered = await w.run("ask", {"question": "what moves water", "retrieve_only": True})

    # Assert
    assert isinstance(answered, AskCommandResult)
    assert answered.hits
