"""Filtered-search harness for Phase 29 task **29.7**.

recall@10 against the exact scan, rows returned, and p50/p95, for HNSW on a typed column at
selectivities 50%, 10%, 1% and 0.1%, under `hnsw.iterative_scan` = `off`, `relaxed_order` and
`strict_order`, with each arm's `EXPLAIN` plan. The filter is a bucket written into `ext` under a
namespace this harness owns, nested by construction so a narrower filter is always a subset of a
wider one, and rendered through the store's own `eq`-on-extension shape
(`weft_store.pgvector_store._extension_predicate`, `_holds`) rather than a hand-written condition a
reviewer would have to trust matched it — `tests/integration/test_bench_filtered_statement.py`
checks that against `PgVectorStore.search_vector` itself, over one table.

This module's pure functions (the buckets, the two statements, recall, truncation, the plan
reader, pgvector's iterative-scan spellings) are pinned by
`tests/unit/scripts/test_bench_filtered.py`. `main` is not unit-tested — it drives a real
database, and is exercised by actually running it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

import bench_latency
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

_TOP_K: Final[int] = 10

BENCH_NAMESPACE: Final[str] = "weft-bench"


class Selectivity(StrEnum):
    """The share of rows a filtered arm keeps, as its label in the record."""

    HALF = "50%"
    TENTH = "10%"
    ONE_PERCENT = "1%"
    TENTH_OF_A_PERCENT = "0.1%"

    @property
    def fraction(self) -> float:
        """The share of rows as a number in `(0, 1]`."""
        return {
            Selectivity.HALF: 0.5,
            Selectivity.TENTH: 0.1,
            Selectivity.ONE_PERCENT: 0.01,
            Selectivity.TENTH_OF_A_PERCENT: 0.001,
        }[self]

    @property
    def key(self) -> str:
        """The bucket's key under `BENCH_NAMESPACE` in a row's `ext`."""
        return {
            Selectivity.HALF: "s50",
            Selectivity.TENTH: "s10",
            Selectivity.ONE_PERCENT: "s1",
            Selectivity.TENTH_OF_A_PERCENT: "s01",
        }[self]


def bucket_rank(node_id: str) -> int:
    """A deterministic rank in `[0, 100_000)`, stable across runs on the same id."""
    return int.from_bytes(hashlib.sha256(node_id.encode()).digest()[:8], "big") % 100_000


def in_bucket(node_id: str, selectivity: Selectivity) -> bool:
    """Buckets are nested by construction: every narrower selectivity's rank cutoff is smaller."""
    return bucket_rank(node_id) < round(selectivity.fraction * 100_000)


def bench_ext(node_id: str) -> str:
    """The JSON patch written into a row's `ext` column under `BENCH_NAMESPACE`."""
    return json.dumps({BENCH_NAMESPACE: {s.key: in_bucket(node_id, s) for s in Selectivity}})


def bucket_predicate(selectivity: Selectivity) -> sql.Composed:
    """Render this harness's bucket through the store's own `eq`-on-extension shape.

    The store's shape is `pgvector_store.py` `_extension_predicate`, `_holds`, applied against
    this harness's own bucket, so the filter this script times is exactly the filter a caller
    would write with `Filter(op=eq, field="ext.weft-bench.<key>", value=True)`.
    """
    path = sql.Literal([BENCH_NAMESPACE, selectivity.key])
    stored = sql.SQL("(ext #> {})").format(path)
    elements = sql.SQL(
        "(CASE WHEN jsonb_typeof({stored}) = 'array' THEN {stored} "
        "ELSE jsonb_build_array({stored}) END)"
    ).format(stored=stored)
    return sql.SQL("({e} @> 'true'::jsonb)").format(e=elements)


_STATEMENT_TEMPLATE = sql.SQL(
    "SELECT id, embedding <=> %(vector)s AS distance FROM weft_nodes "
    "WHERE embedding IS NOT NULL AND {predicate} "
    "ORDER BY embedding <=> %(vector)s LIMIT %(top_k)s"
)


def unfiltered_statement() -> sql.Composed:
    """Build the top-k query with no filter, taking `vector` and `top_k` parameters."""
    return _STATEMENT_TEMPLATE.format(predicate=sql.SQL("TRUE"))


def filtered_statement(selectivity: Selectivity) -> sql.Composed:
    """Build the top-k query restricted to one selectivity bucket.

    Args:
        selectivity: The bucket the query must stay inside.

    Returns:
        The statement, taking `vector` and `top_k` parameters.
    """
    return _STATEMENT_TEMPLATE.format(predicate=bucket_predicate(selectivity))


def recall_at_k(truth: Sequence[str], found: Sequence[str], *, k: int = 10) -> float:
    """Measure the share of the exact top-k that an approximate answer recovered.

    Args:
        truth: The exact scan's ids, best first.
        found: The measured arm's ids, best first.
        k: How many of each to compare.

    Returns:
        The recalled fraction of `truth[:k]`.

    Raises:
        ValueError: `truth` is empty.
    """
    if not truth:
        raise ValueError("no ground truth to measure recall against")
    wanted = set(truth[:k])
    return len(wanted & set(found[:k])) / len(wanted)


def truncate_renormalise(values: Sequence[float], width: int) -> tuple[float, ...]:
    """The first `width` components, rescaled back to unit length."""
    if width > len(values):
        raise ValueError(
            f"cannot truncate to width {width}: the vector has {len(values)} components"
        )
    truncated = values[:width]
    norm = math.sqrt(sum(v * v for v in truncated))
    if norm == 0.0:
        raise ValueError("cannot renormalise a zero vector")
    return tuple(v / norm for v in truncated)


class PlanShape(StrEnum):
    """What an arm's `EXPLAIN` plan reads as, coarsely."""

    INDEX_SCAN = "index scan"
    SEQ_SCAN = "sequential scan"
    OTHER = "other"


def classify_plan(lines: Sequence[str], *, index_name: str) -> PlanShape:
    """Read an `EXPLAIN` plan's lines as an index scan, a sequential scan or something else.

    Args:
        lines: The plan, one line per row `EXPLAIN` returned.
        index_name: The index whose use counts as an index scan.

    Returns:
        The plan's shape.
    """
    if any(f"Index Scan using {index_name}" in line for line in lines):
        return PlanShape.INDEX_SCAN
    if any("Seq Scan" in line for line in lines):
        return PlanShape.SEQ_SCAN
    return PlanShape.OTHER


class IterativeScan(StrEnum):
    """pgvector's `hnsw.iterative_scan` settings, spelled as the server takes them."""

    OFF = "off"
    RELAXED_ORDER = "relaxed_order"
    STRICT_ORDER = "strict_order"


# ---------------------------------------------------------------------------------------------
# The driving half: not unit-tested, run against a real database by the dispatcher.
# ---------------------------------------------------------------------------------------------


class SelectivityCount(BaseModel):
    """How many rows one selectivity bucket matched."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selectivity: Selectivity
    rows: int


class FilteredArmResult(BaseModel):
    """Recall, rows returned, latency and plan of one iterative-scan mode at one selectivity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selectivity: Selectivity | None
    iterative_scan: IterativeScan
    queries: int
    returned_min: int
    returned_mean: float
    recall_at_10: float
    p50_ms: float
    p95_ms: float
    plan: PlanShape
    rows_before: int
    rows_after: int


class FilteredRun(BaseModel):
    """The whole run as written to `--record`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: bench_latency.Machine
    database: str
    vector_set: str
    rows: int
    width: int
    pgvector_version: str
    server_version: str
    alter_seconds: float
    index_build_seconds: float
    index_bytes: int
    ef_search: str
    max_scan_tuples: str
    matching_rows: tuple[SelectivityCount, ...]
    results: tuple[FilteredArmResult, ...]
    taken_at: datetime


def _database_name(width: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"weft_bench_filtered_{width}_{stamp}"


def _drop_database(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def _row_count(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM weft_nodes")
        row = cur.fetchone()
        if row is None:
            raise bench_latency.MeasurementRefusedError("weft_nodes reported no row count")
        return int(row[0])


def _load(admin_dsn: str, database: str, vector_set: Path, rows: int | None) -> None:
    command = [
        sys.executable,
        str(Path(__file__).with_name("bench_vectors.py")),
        "load",
        "--set",
        str(vector_set),
        "--database",
        database,
        "--admin-dsn",
        admin_dsn,
    ]
    if rows is not None:
        command += ["--rows", str(rows)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        raise bench_latency.MeasurementRefusedError(
            f"bench_vectors.py load exited {result.returncode}: {result.stderr}"
        )


def _type_column(conn: psycopg.Connection, *, width: int) -> float:
    rows_before = _row_count(conn)
    with conn.cursor() as cur:
        started = time.monotonic()
        cur.execute(
            sql.SQL(
                "ALTER TABLE weft_nodes ALTER COLUMN embedding TYPE vector({}) "
                "USING l2_normalize(subvector(embedding, 1, {}))"
            ).format(sql.Literal(width), sql.Literal(width))
        )
        elapsed = time.monotonic() - started
    conn.commit()
    rows_after = _row_count(conn)
    bench_latency.assert_rows(label="typed", expected=rows_before, found=rows_after)
    print(f"typed embedding as vector({width}) from the native width: ALTER took {elapsed:.2f} s")
    return elapsed


def _write_buckets(conn: psycopg.Connection, ids: Sequence[str]) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE bench_buckets (id text PRIMARY KEY, patch jsonb)")
        with cur.copy("COPY bench_buckets (id, patch) FROM STDIN") as copy:
            for node_id in ids:
                copy.write_row((node_id, Jsonb(json.loads(bench_ext(node_id)))))
        cur.execute(
            "UPDATE weft_nodes n SET ext = n.ext || t.patch FROM bench_buckets t WHERE n.id = t.id"
        )
        bench_latency.assert_rows(label="buckets", expected=len(ids), found=cur.rowcount)
    conn.commit()


def _matching_rows(conn: psycopg.Connection) -> tuple[SelectivityCount, ...]:
    counts: list[SelectivityCount] = []
    with conn.cursor() as cur:
        for selectivity in Selectivity:
            cur.execute(
                sql.SQL("SELECT count(*) FROM weft_nodes WHERE {p}").format(
                    p=bucket_predicate(selectivity)
                )
            )
            row = cur.fetchone()
            if row is None:
                raise bench_latency.MeasurementRefusedError(
                    f"selectivity {selectivity.value} reported no row count"
                )
            n = int(row[0])
            print(f"selectivity {selectivity.value}: {n:,} matching rows")
            if n == 0:
                raise bench_latency.MeasurementRefusedError(
                    f"selectivity {selectivity.value} matches 0 rows; refusing an empty filter"
                )
            counts.append(SelectivityCount(selectivity=selectivity, rows=n))
    return tuple(counts)


def _fetch_vectors(conn: psycopg.Connection, sample: Sequence[str]) -> dict[str, object]:
    fetched: dict[str, object] = {}
    with conn.cursor() as cur:
        for node_id in sample:
            cur.execute("SELECT embedding FROM weft_nodes WHERE id = %s", (node_id,))
            row = cur.fetchone()
            if row is None:
                raise bench_latency.MeasurementRefusedError(
                    f"sampled id {node_id!r} is no longer in the table"
                )
            fetched[node_id] = row[0]
    return fetched


def _ground_truth(
    conn: psycopg.Connection, sample: Sequence[str], fetched: dict[str, object]
) -> dict[Selectivity | None, dict[str, tuple[str, ...]]]:
    truth: dict[Selectivity | None, dict[str, tuple[str, ...]]] = {}
    with conn.cursor() as cur:
        for selectivity in (None, *Selectivity):
            statement = (
                unfiltered_statement() if selectivity is None else filtered_statement(selectivity)
            )
            per_query: dict[str, tuple[str, ...]] = {}
            for node_id in sample:
                cur.execute(statement, {"vector": fetched[node_id], "top_k": _TOP_K})
                per_query[node_id] = tuple(str(row[0]) for row in cur.fetchall())
            truth[selectivity] = per_query
    return truth


def _build_index(conn: psycopg.Connection) -> tuple[float, int, str, str]:
    with conn.cursor() as cur:
        started = time.monotonic()
        cur.execute(
            "CREATE INDEX bench_hnsw ON weft_nodes USING hnsw (embedding vector_cosine_ops)"
        )
        elapsed = time.monotonic() - started
        cur.execute("ANALYZE weft_nodes")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT pg_relation_size('bench_hnsw')")
        size_row = cur.fetchone()
        cur.execute("SHOW hnsw.ef_search")
        ef_row = cur.fetchone()
        cur.execute("SHOW hnsw.max_scan_tuples")
        mst_row = cur.fetchone()
    if size_row is None or ef_row is None or mst_row is None:
        raise bench_latency.MeasurementRefusedError(
            "the database reported no index size or hnsw settings after CREATE INDEX"
        )
    index_bytes, ef_search, max_scan_tuples = int(size_row[0]), str(ef_row[0]), str(mst_row[0])
    print(f"index bench_hnsw: {index_bytes:,} bytes, built in {elapsed:.2f} s")
    print(f"hnsw.ef_search = {ef_search}  hnsw.max_scan_tuples = {max_scan_tuples}")
    return elapsed, index_bytes, ef_search, max_scan_tuples


def _explain_plan(conn: psycopg.Connection, statement: sql.Composed, vector: object) -> PlanShape:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("EXPLAIN {}").format(statement), {"vector": vector, "top_k": _TOP_K})
        lines = [str(row[0]) for row in cur.fetchall()]
    return classify_plan(lines, index_name="bench_hnsw")


def _run_arm(
    conn: psycopg.Connection,
    *,
    mode: IterativeScan,
    selectivity: Selectivity | None,
    sample: Sequence[str],
    fetched: dict[str, object],
    truth: dict[Selectivity | None, dict[str, tuple[str, ...]]],
) -> FilteredArmResult:
    statement = unfiltered_statement() if selectivity is None else filtered_statement(selectivity)
    plan = _explain_plan(conn, statement, fetched[sample[0]])

    rows_before = _row_count(conn)
    returned_counts: list[int] = []
    recalls: list[float] = []
    seconds: list[float] = []
    with conn.cursor() as cur:
        for node_id in sample:
            started = time.monotonic()
            cur.execute(statement, {"vector": fetched[node_id], "top_k": _TOP_K})
            found_rows = cur.fetchall()
            seconds.append(time.monotonic() - started)
            found_ids = tuple(str(row[0]) for row in found_rows)
            returned_counts.append(len(found_ids))
            recalls.append(recall_at_k(truth[selectivity][node_id], found_ids, k=_TOP_K))
    rows_after = _row_count(conn)
    bench_latency.assert_rows(label="after", expected=rows_before, found=rows_after)

    milliseconds = [value * 1000 for value in seconds]
    result = FilteredArmResult(
        selectivity=selectivity,
        iterative_scan=mode,
        queries=len(sample),
        returned_min=min(returned_counts),
        returned_mean=statistics.fmean(returned_counts),
        recall_at_10=statistics.fmean(recalls),
        p50_ms=bench_latency.percentile(milliseconds, 0.50),
        p95_ms=bench_latency.percentile(milliseconds, 0.95),
        plan=plan,
        rows_before=rows_before,
        rows_after=rows_after,
    )
    print(
        f"filter: {selectivity.value if selectivity is not None else 'unfiltered'}  "
        f"iterative: {mode.value}  returned: min {result.returned_min} "
        f"mean {result.returned_mean:.1f}  recall@10: {result.recall_at_10:.3f}  "
        f"p50: {result.p50_ms:.1f} ms  p95: {result.p95_ms:.1f} ms  plan: {plan.value}  "
        f"before: {rows_before:,} rows  after: {rows_after:,} rows"
    )
    return result


_FAILURES: Final = (
    bench_latency.MeasurementRefusedError,
    bench_latency.RowCountMismatchError,
    ValueError,
    psycopg.Error,
    OSError,
)


def _refuse_existing(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as admin, admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if cur.fetchone() is not None:
            raise bench_latency.MeasurementRefusedError(
                f"database {name!r} already exists; refusing to reuse or drop it"
            )


def _measure_and_record(
    arguments: argparse.Namespace, *, admin_dsn: str, name: str, machine: bench_latency.Machine
) -> None:
    _load(admin_dsn, name, arguments.vector_set, arguments.rows)
    database_dsn = make_conninfo(admin_dsn, dbname=name)

    with psycopg.connect(database_dsn) as conn:
        register_vector(conn)
        rows = _row_count(conn)

        with conn.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            extension_row = cur.fetchone()
            cur.execute("SHOW server_version")
            server_row = cur.fetchone()
        if extension_row is None or server_row is None:
            raise bench_latency.MeasurementRefusedError(
                "the database reported no pgvector extension or server version"
            )
        pgvector_version, server_version = str(extension_row[0]), str(server_row[0])

        alter_seconds = _type_column(conn, width=arguments.width)

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM weft_nodes ORDER BY id")
            ids = [str(row[0]) for row in cur.fetchall()]
        _write_buckets(conn, ids)
        matching_rows = _matching_rows(conn)

        sample = bench_latency.query_sample(ids, arguments.queries)
        fetched = _fetch_vectors(conn, sample)
        truth = _ground_truth(conn, sample, fetched)

        index_build_seconds, index_bytes, ef_search, max_scan_tuples = _build_index(conn)

        results: list[FilteredArmResult] = []
        for mode in IterativeScan:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("SET hnsw.iterative_scan = {}").format(sql.Literal(mode.value)))
            for selectivity in (None, *Selectivity):
                results.append(
                    _run_arm(
                        conn,
                        mode=mode,
                        selectivity=selectivity,
                        sample=sample,
                        fetched=fetched,
                        truth=truth,
                    )
                )

    if arguments.record is not None:
        run = FilteredRun(
            machine=machine,
            database=name,
            vector_set=arguments.vector_set.name,
            rows=rows,
            width=arguments.width,
            pgvector_version=pgvector_version,
            server_version=server_version,
            alter_seconds=alter_seconds,
            index_build_seconds=index_build_seconds,
            index_bytes=index_bytes,
            ef_search=ef_search,
            max_scan_tuples=max_scan_tuples,
            matching_rows=matching_rows,
            results=tuple(results),
            taken_at=datetime.now(UTC),
        )
        arguments.record.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    if arguments.keep:
        print(f"kept: {name}")
    else:
        _drop_database(admin_dsn, name)


def main(argv: list[str] | None = None) -> int:
    """Run the filtered-search measurement in a fresh database and drop it unless `--keep`.

    Args:
        argv: Command-line arguments; `None` reads `sys.argv`.

    Returns:
        0 on a completed run, 2 when the measurement was refused or failed.
    """
    bench_latency.line_buffer_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--set", dest="vector_set", type=Path, required=True, help="a 29.6 vector set directory"
    )
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--admin-dsn", default=None)
    parser.add_argument("--record", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.width > 2000:
        print(
            f"--width {arguments.width} exceeds HNSW's 2,000-dimension ceiling",
            file=sys.stderr,
        )
        return 2

    admin_dsn = arguments.admin_dsn or os.environ.get("WEFT_DATABASE_URL")
    if not admin_dsn:
        print("no admin DSN: pass --admin-dsn or set WEFT_DATABASE_URL", file=sys.stderr)
        return 2

    machine = bench_latency.host_machine()
    print(f"machine: {machine.label}")

    name = _database_name(arguments.width)

    try:
        _refuse_existing(admin_dsn, name)
    except _FAILURES as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        _measure_and_record(arguments, admin_dsn=admin_dsn, name=name, machine=machine)
    except _FAILURES as exc:
        print(str(exc), file=sys.stderr)
        if not arguments.keep:
            _drop_database(admin_dsn, name)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
