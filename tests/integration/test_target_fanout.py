"""A promote moves every participant that holds targets, and participants that disagree are
refused until a promote converges them — ledger task **34.11**, its fan-out half, with the blob
root joining `weft target drop` (`34.12`).

A project indexing through `index-with-cooccurrence` writes two stores: the node store and the
graph pack's store, each with its own live pointer (`34.1`, `34.11`). `weft target promote`,
`rollback` and `drop` act on both. A promote is atomic per participant, not across them (Q1: no
two-phase commit), so a crash between the two leaves them pointing at different targets. Every
read then refuses, naming each participant's live target, until the promote is run again, and a
re-run converges.
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

from weft_engine.api import Weft
from weft_engine.targets import TargetPointersDisagreeError
from weft_kg.store import GraphSettings, GraphStore
from weft_store.contract import DEFAULT_TARGET, Promotion
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


@pytest.fixture
async def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_fanout_{uuid4().hex[:12]}"
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = f"{_DSN.rsplit('/', 1)[0]}/{name}"
    monkeypatch.chdir(tmp_path)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "pumps.txt").write_text(
        "Acme Pumps build centrifugal pumps in Leeds.", encoding="utf-8"
    )
    (corpus / "valves.txt").write_text(
        "Leeds Valves supply Acme Pumps with gate valves.", encoding="utf-8"
    )
    blob_root = tmp_path / "blobs"
    (tmp_path / "weft.toml").write_text(
        f'[packs.store]\ndsn = "{dsn}"\n\n[packs.graph]\ndsn = "{dsn}"\n\n'
        f'[packs.blob]\nroot = "{blob_root}"\n'
    )
    try:
        yield tmp_path
    finally:
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


def _dsn(project: Path) -> str:
    return (project / "weft.toml").read_text().split('"')[1]


async def _live(project: Path) -> tuple[str, str]:
    nodes = PgVectorStore(PgVectorSettings(dsn=SecretStr(_dsn(project))))
    graph = GraphStore(GraphSettings(dsn=SecretStr(_dsn(project))))
    try:
        return (await nodes.target_catalogue()).live, (await graph.target_catalogue()).live
    finally:
        await nodes.aclose()
        await graph.aclose()


async def _index_both(w: Weft) -> None:
    await w.run("index", {"path": "corpus", "pipeline": "index-with-cooccurrence"})
    await w.run(
        "index", {"path": "corpus", "pipeline": "index-with-cooccurrence", "target": "w128"}
    )


async def test_promote_and_rollback_move_the_node_store_and_the_graph_together(
    project: Path,
) -> None:
    # Arrange
    async with Weft.open(project / "weft.toml") as w:
        await _index_both(w)

        # Act
        await w.run("target promote", {"name": "w128", "without_evidence": True}, yes=True)
        promoted = await _live(project)
        await w.run("target rollback", {}, yes=True)
        rolled_back = await _live(project)

    # Assert
    assert promoted == ("w128", "w128")
    assert rolled_back == (DEFAULT_TARGET, DEFAULT_TARGET)


async def test_participants_left_disagreeing_refuse_every_read_until_a_promote_converges(
    project: Path,
) -> None:
    # Arrange — the crash between participants: only the graph moved.
    async with Weft.open(project / "weft.toml") as w:
        await _index_both(w)
        graph = GraphStore(GraphSettings(dsn=SecretStr(_dsn(project))))
        await graph.promote(
            Promotion(
                target="w128", at=datetime.now(UTC), by="test", evidence=(), without_evidence=True
            )
        )
        await graph.aclose()

        # Act / Assert
        with pytest.raises(TargetPointersDisagreeError) as caught:
            await w.run("ask", {"question": "who builds pumps", "retrieve_only": True})
        message = str(caught.value)
        assert "w128" in message
        assert DEFAULT_TARGET in message

        await w.run("target promote", {"name": "w128", "without_evidence": True}, yes=True)
        answered = await w.run("ask", {"question": "who builds pumps", "retrieve_only": True})

    assert answered is not None
    assert await _live(project) == ("w128", "w128")
    nodes = PgVectorStore(PgVectorSettings(dsn=SecretStr(_dsn(project))))
    assert (await nodes.target_catalogue()).previous == DEFAULT_TARGET
    await nodes.aclose()


async def test_drop_removes_a_target_from_every_participant_and_its_blobs(project: Path) -> None:
    # Arrange — a candidate with a blob subtree of its own.
    candidate_blobs = project / "blobs" / ".targets" / "w256" / "tenant" / "doc"
    async with Weft.open(project / "weft.toml") as w:
        await w.run("index", {"path": "corpus", "pipeline": "index-with-cooccurrence"})
        await w.run(
            "index",
            {"path": "corpus", "pipeline": "index-with-cooccurrence", "target": "w256"},
        )
        candidate_blobs.mkdir(parents=True)
        (candidate_blobs / "0.png").write_bytes(b"figure")

        # Act
        await w.run("target drop", {"name": "w256"}, yes=True)

    # Assert
    nodes = PgVectorStore(PgVectorSettings(dsn=SecretStr(_dsn(project))))
    graph = GraphStore(GraphSettings(dsn=SecretStr(_dsn(project))))
    assert "w256" not in {record.name for record in (await nodes.target_catalogue()).targets}
    assert "w256" not in {record.name for record in (await graph.target_catalogue()).targets}
    await nodes.aclose()
    await graph.aclose()
    assert not (project / "blobs" / ".targets" / "w256").exists()
