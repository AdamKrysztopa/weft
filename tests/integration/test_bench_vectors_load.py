"""Phase 29 task **29.5** — a vector set reloads into a throwaway database at its own width.

`29.6`'s exit says the set is *"reloadable into any throwaway database with no API call"*, and it
was proven so before `29.3` landed. `29.3` then made the store commit `weft_nodes.embedding` to
`vector(n)` at the first embedded node — and `load` provisions its schema by running
`weft index --pipeline index-text`, which embeds through the default `hash` embedder at width 64.
The column is therefore already committed to 64 when the `COPY` of a wider set arrives, `TRUNCATE`
does not untype a column, and the reload is refused by the very mechanism `29.3` added.

Found by running the binary, not by the suite: `load` has no unit test, because
`tests/unit/scripts/test_bench_vectors.py` opens by promising no database, and the subcommands are
documented as *"checked by running them"* (`L22.35` is that gap firing once already).

What this pins is the property, not the SQL: after a reload the committed width is the **set's**
width, so the database is indistinguishable from one the store itself filled at that width.

Nothing here skips. `tests/integration/` reaches a container by construction, and `poe ci-checks`
already fails a run whose `WEFT_DATABASE_URL` names an unreachable database — so a second
reachability guard of this module's own would only convert that failure into a silent pass, which
is `L7.8` exactly.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import bench_vectors
import numpy as np
import psycopg
import pytest
from psycopg.conninfo import make_conninfo

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

#: Not 64, which is what `hash` — and so `load`'s own provisioning step — commits the column to.
_WIDTH = 3

_NODE_COLUMNS = ("id", "parents", "sources", "content", "media_type", "ext")
_SOURCE_COLUMNS = (
    "id",
    "uri",
    "content_hash",
    "indexed_at",
    "pipeline",
    "status",
    "pipeline_identity",
)


def _tables(source_id: str) -> tuple[bench_vectors.TableDump, ...]:
    return (
        bench_vectors.TableDump(
            name="weft_nodes",
            columns=_NODE_COLUMNS,
            rows=(
                ("n1", "{}", f"{{{source_id}}}", "first chunk", "text/plain", "{}"),
                ("n2", "{}", f"{{{source_id}}}", "second chunk", "text/plain", "{}"),
            ),
        ),
        bench_vectors.TableDump(
            name="weft_sources",
            columns=_SOURCE_COLUMNS,
            # Real column types, unlike the unit fixtures: these rows reach Postgres.
            rows=(
                (
                    source_id,
                    f"file://{source_id}",
                    "h",
                    "2026-09-16T00:00:00+00:00",
                    "index-text",
                    "active",
                    "i",
                ),
            ),
        ),
    )


@pytest.fixture
def throwaway_database() -> Iterator[str]:
    """A database name that does not exist yet, dropped again however the test ends."""
    name = "weft_bench_load_reload"
    with psycopg.connect(_DSN, autocommit=True, connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {name}")
    yield name
    with psycopg.connect(_DSN, autocommit=True, connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {name}")


def test_a_reloaded_set_commits_the_column_to_the_sets_own_width(
    tmp_path: Path, throwaway_database: str
) -> None:
    # Arrange — a set three components wide, while provisioning will embed at 64.
    source_id = str(tmp_path / "paper.pdf")
    vectors = np.array([[0.5, -0.25, 1.0], [0.125, 0.0, -1.0]], dtype=np.float32)
    written = bench_vectors.write_vector_set(
        tmp_path,
        input_digest="a" * 64,
        model=bench_vectors.EmbeddingModel.LARGE,
        width=_WIDTH,
        day=date(2026, 9, 16),
        billed_tokens=0,
        pdfs=1,
        tables=_tables(source_id),
        vectors=vectors,
    )

    # Act — the subcommand an operator runs, through the parser they type at.
    exit_code = bench_vectors.main(
        [
            "load",
            "--set",
            str(tmp_path / written.meta.name),
            "--database",
            throwaway_database,
            "--admin-dsn",
            _DSN,
        ]
    )

    # Assert — it loaded, and the column carries the set's width rather than provisioning's 64.
    assert exit_code == 0
    dsn = make_conninfo(_DSN, dbname=throwaway_database)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM weft_nodes")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 2
        cur.execute(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = to_regclass('weft_nodes') AND attname = 'embedding'"
        )
        typmod = cur.fetchone()
        assert typmod is not None
        assert typmod[0] == _WIDTH
