"""A promote committed during another command never mixes two targets in one operation.

A promote committed during another command never mixes two targets inside one operation —
ledger task **34.10**, owner decision Q-C.

The live pointer is read once, when an operation's store opens, and held for that operation. An
ingest therefore finishes into the target it opened against even if another process promotes
between two of its batches, and says so. An embedded `Weft` session re-reads the pointer on its
next operation, so it follows a promote without being reopened.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr

from weft_cli.commands import AskCommandResult, IndexCommandResult, SourcesListCommandResult
from weft_engine.api import Weft
from weft_store.contract import DEFAULT_TARGET, Promotion
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


@pytest.fixture
async def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_one_target_{uuid4().hex[:12]}"
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = f"{_DSN.rsplit('/', 1)[0]}/{name}"
    monkeypatch.chdir(tmp_path)
    for directory, files in {
        "corpus": {
            "a.txt": "Pumps move water.",
            "b.txt": "Valves stop flow.",
            "c.txt": "Gears turn.",
        },
        "other": {"z.txt": "Bearings reduce friction between rotating parts."},
    }.items():
        (tmp_path / directory).mkdir()
        for file_name, text in files.items():
            (tmp_path / directory / file_name).write_text(text, encoding="utf-8")
    (tmp_path / "weft.toml").write_text(f'[packs.store]\ndsn = "{dsn}"\n')
    try:
        yield tmp_path
    finally:
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


def _store(project: Path) -> PgVectorStore:
    return PgVectorStore(
        PgVectorSettings(dsn=SecretStr((project / "weft.toml").read_text().split('"')[1]))
    )


async def _promote(project: Path, target: str) -> None:
    store = _store(project)
    await store.promote(
        Promotion(
            target=target, at=datetime.now(UTC), by="test", evidence=(), without_evidence=True
        )
    )
    await store.aclose()


async def test_an_ingest_finishes_into_the_target_it_opened_against_and_says_it_stopped_being_live(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a candidate to promote to, and a hook that promotes it after the first batch.
    async with Weft.open(project / "weft.toml") as w:
        await w.index(project / "other", target="w128")
        import weft_cli.ingest as ingest_module

        real = vars(ingest_module)["_record_sources"]
        calls: list[int] = []

        async def promote_after_first_batch(*args: object, **kwargs: object) -> object:
            result = await real(*args, **kwargs)
            calls.append(1)
            if len(calls) == 2:
                await _promote(project, "w128")
            return result

        monkeypatch.setattr("weft_cli.ingest._record_sources", promote_after_first_batch)

        # Act
        indexed = await w.run("index", {"path": "corpus", "batch_size": 1})
        monkeypatch.undo()
        live_sources = await w.run("sources list", {"target": DEFAULT_TARGET})

    # Assert
    assert isinstance(indexed, IndexCommandResult)
    assert isinstance(live_sources, SourcesListCommandResult)
    assert len(live_sources.sources) == 3
    assert indexed.target == DEFAULT_TARGET
    assert indexed.target_stopped_being_live


async def test_an_embedded_session_follows_a_promote_on_its_next_operation(project: Path) -> None:
    # Arrange — default holds `corpus`, w128 holds only `other`.
    async with Weft.open(project / "weft.toml") as w:
        await w.index(project / "corpus")
        await w.index(project / "other", target="w128")
        before = await w.run("ask", {"question": "what reduces friction", "retrieve_only": True})

        # Act
        await _promote(project, "w128")
        after = await w.run("ask", {"question": "what reduces friction", "retrieve_only": True})

    # Assert
    assert isinstance(before, AskCommandResult)
    assert isinstance(after, AskCommandResult)
    assert "Bearings" not in " ".join(hit.content for hit in before.hits)
    assert "Bearings" in " ".join(hit.content for hit in after.hits)
