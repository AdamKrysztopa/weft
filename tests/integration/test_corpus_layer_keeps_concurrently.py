"""Guards `raptor`'s concurrent checkpoints against interleaving transactions on one handle.

Carried repair **R43.40** — a corpus-scoped build that keeps two or more summaries at once
publishes its tree on pgvector.

`raptor` summarises its clusters concurrently and keeps each through `LayerCheckpoints` as it
finishes, and every `keep` ran the layer's store stage on one bound `PgVectorStore` handle, so two
`add` transactions interleaved on its one connection and `weft index` exited 1 with
`OutOfOrderTransactionNesting`. `02` §1 promises a `Lifetime.RUN` plugin no thread-safety
obligation, so the checkpoint service, not the store, owes the serialisation.

**One fresh database per test**, created and dropped by its exact recorded name (`L8.30`,
`L22.47`); `hash` embeds and `scripted` answers, so nothing leaves the machine. An absent container
skips with the reason.
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

from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_engine.registry_bootstrap import Dependencies, build_dependencies
from weft_index.payload import RaptorFacts
from weft_kernel.context import Context
from weft_kernel.payload import Node
from weft_store.contract import Cursor, GenerationStatus
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_LAYER = "enrich-with-raptor-corpus"
_DOCUMENTS = 8
#: `raptor.cluster_size: 2` over `_DOCUMENTS` one-chunk documents, with a threshold every pair
#: clears, so the build keeps this many summaries under `raptor`'s default in-flight bound of 8.
_SUMMARIES = 4


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    try:
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    name = f"weft_r4340_{uuid4().hex[:12]}"
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


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / f"{_LAYER}.yaml").write_text(
        f"name: {_LAYER}\n"
        "extends: enrich-with-raptor\n"
        "vars:\n"
        "  layer.scope: corpus\n"
        "  raptor.cluster_size: 2\n"
        "  raptor.similarity_threshold: -1.0\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(_DOCUMENTS):
        (docs / f"doc{i}.md").write_text(
            f"# Note {i}\n\nDocument number {i} says something of its own.\n", encoding="utf-8"
        )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def _index(project: Path, dsn: str, **flags: object) -> render.Rendered:
    config = project / "weft.toml"
    config.write_text(
        f'[packs.store]\ndsn = "{dsn}"\n\n'
        '[llm.roles.index]\nprovider = "scripted"\n\n'
        '[llm.roles.generate]\nprovider = "scripted"\n',
        encoding="utf-8",
    )
    ctx = _ctx()
    ctx.services.add(Dependencies, build_dependencies(config_path=config))
    outcome = await commands.IndexCommand().run(
        commands.IndexArgs.model_validate({"path": str(project / "docs"), **flags}), ctx
    )
    return render.render_outcome(outcome)


async def _rows(dsn: str) -> int:
    conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM weft_nodes")
            row = await cur.fetchone()
    finally:
        await conn.close()
    assert row is not None
    return int(row[0])


async def _published_summaries(dsn: str) -> list[Node]:
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(dsn)))
    nodes: list[Node] = []
    cursor: Cursor | None = None
    try:
        while True:
            page = await store.scan(cursor)
            nodes.extend(node for node in page.items if node.ext_as(RaptorFacts) is not None)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        generations = await store.generations()
    finally:
        await store.aclose()
    assert [(g.layer, g.status) for g in generations] == [(_LAYER, GenerationStatus.PUBLISHED)]
    return nodes


async def test_a_corpus_build_keeping_several_summaries_at_once_publishes_on_pgvector(
    project: Path, dsn: str
) -> None:
    # Arrange
    base = await _index(project, dsn)
    assert base.exit_code is ExitCode.SUCCESS, base.stderr
    leaves = await _rows(dsn)
    assert leaves == _DOCUMENTS

    # Act
    rendered = await _index(project, dsn, layers=_LAYER, reprocess=True)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert len(await _published_summaries(dsn)) == _SUMMARIES
    assert await _rows(dsn) == leaves + _SUMMARIES
