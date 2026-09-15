"""Quantised HNSW rescoring harness for Phase 29 task **29.8**.

halfvec and binary-quantised HNSW expression indexes, rescored at full precision from an
oversampled candidate set (`fix-plans/07` 29.8; Q2 settled). Build time, index size, recall@10
against the exact scan, and p95, at oversampling 1, 2, 4 and 10, unfiltered and at 1%. The inner
ordering is the quantised expression's own distance operator, limited to the candidate set; the
outer ordering is the store's own `<=>` on the full-precision column, so the rescoring can never
rank a candidate the store itself would rank differently
(`tests/integration/test_bench_quantised_statement.py`).

This module's pure functions (the sweep points, the candidate arithmetic, the two statement
builders) are pinned by `tests/unit/scripts/test_bench_quantised.py`. `main` is not unit-tested —
it drives a real database, and is exercised by actually running it.
"""

from __future__ import annotations

import argparse
import json
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

import bench_filtered
import bench_latency
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

_TOP_K: Final[int] = 10

OVERSAMPLING: Final[tuple[int, ...]] = (1, 2, 4, 10)

_INDEX_CEILING: Final[dict[str, int]] = {"halfvec": 4000, "bit": 64000}


class Quantisation(StrEnum):
    HALFVEC = "halfvec"
    BINARY = "binary"


def candidates(oversampling: int, *, top_k: int) -> int:
    if oversampling < 1:
        raise ValueError(f"oversampling must be at least 1 (got {oversampling})")
    return oversampling * top_k


def index_statement(quantisation: Quantisation, *, width: int, index_name: str) -> sql.Composed:
    name = sql.Identifier(index_name)
    literal_width = sql.Literal(width)
    if quantisation is Quantisation.HALFVEC:
        ceiling = _INDEX_CEILING["halfvec"]
        if width > ceiling:
            raise ValueError(
                f"halfvec indexes at most {ceiling} dimensions; width {width} is past it"
            )
        return sql.SQL(
            "CREATE INDEX {name} ON weft_nodes USING hnsw "
            "((embedding::halfvec({width})) halfvec_cosine_ops)"
        ).format(name=name, width=literal_width)
    ceiling = _INDEX_CEILING["bit"]
    if width > ceiling:
        raise ValueError(f"binary indexes at most {ceiling} dimensions; width {width} is past it")
    return sql.SQL(
        "CREATE INDEX {name} ON weft_nodes USING hnsw "
        "((binary_quantize(embedding)::bit({width})) bit_hamming_ops)"
    ).format(name=name, width=literal_width)


def rescored_statement(
    quantisation: Quantisation,
    *,
    width: int,
    selectivity: bench_filtered.Selectivity | None,
) -> sql.Composed:
    predicate = (
        sql.SQL("TRUE") if selectivity is None else bench_filtered.bucket_predicate(selectivity)
    )
    literal_width = sql.Literal(width)
    if quantisation is Quantisation.HALFVEC:
        expression = sql.SQL("embedding::halfvec({width})").format(width=literal_width)
        operator = sql.SQL("<=>")
        query = sql.SQL("%(vector)s::halfvec({width})").format(width=literal_width)
    else:
        expression = sql.SQL("binary_quantize(embedding)::bit({width})").format(width=literal_width)
        operator = sql.SQL("<~>")
        query = sql.SQL("binary_quantize(%(vector)s)::bit({width})").format(width=literal_width)
    return sql.SQL(
        "SELECT id, embedding <=> %(vector)s AS distance FROM ("
        "SELECT id, embedding FROM weft_nodes WHERE embedding IS NOT NULL AND {predicate} "
        "ORDER BY {expression} {operator} {query} LIMIT %(candidates)s"
        ") AS candidates ORDER BY embedding <=> %(vector)s LIMIT %(top_k)s"
    ).format(predicate=predicate, expression=expression, operator=operator, query=query)


# ---------------------------------------------------------------------------------------------
# The driving half: not unit-tested, run against a real database by the dispatcher.
# ---------------------------------------------------------------------------------------------


class IndexBuild(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    quantisation: Quantisation
    build_seconds: float
    index_bytes: int


class QuantisedArmResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    quantisation: Quantisation
    selectivity: bench_filtered.Selectivity | None
    oversampling: int
    queries: int
    returned_min: int
    recall_at_10: float
    p50_ms: float
    p95_ms: float
    plan: bench_filtered.PlanShape
    rows_before: int
    rows_after: int


class QuantisedRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: bench_latency.Machine
    database: str
    vector_set: str
    rows: int
    width: int
    pgvector_version: str
    server_version: str
    alter_seconds: float
    builds: tuple[IndexBuild, ...]
    results: tuple[QuantisedArmResult, ...]
    taken_at: datetime


def _database_name(width: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"weft_bench_quantised_{width}_{stamp}"


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
    rows_after = _row_count(conn)
    bench_latency.assert_rows(label="typed", expected=rows_before, found=rows_after)
    print(f"typed embedding as vector({width}) from the native width: ALTER took {elapsed:.2f} s")
    return elapsed


def _write_buckets(conn: psycopg.Connection, ids: Sequence[str]) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE bench_buckets (id text PRIMARY KEY, patch jsonb)")
        with cur.copy("COPY bench_buckets (id, patch) FROM STDIN") as copy:
            for node_id in ids:
                copy.write_row((node_id, Jsonb(json.loads(bench_filtered.bench_ext(node_id)))))
        cur.execute(
            "UPDATE weft_nodes n SET ext = n.ext || t.patch FROM bench_buckets t WHERE n.id = t.id"
        )
        bench_latency.assert_rows(label="buckets", expected=len(ids), found=cur.rowcount)


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
) -> dict[bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]]:
    truth: dict[bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]] = {}
    with conn.cursor() as cur:
        for selectivity in (None, bench_filtered.Selectivity.ONE_PERCENT):
            statement = (
                bench_filtered.unfiltered_statement()
                if selectivity is None
                else bench_filtered.filtered_statement(selectivity)
            )
            per_query: dict[str, tuple[str, ...]] = {}
            for node_id in sample:
                cur.execute(statement, {"vector": fetched[node_id], "top_k": _TOP_K})
                per_query[node_id] = tuple(str(row[0]) for row in cur.fetchall())
            truth[selectivity] = per_query
    return truth


def _build_index(conn: psycopg.Connection, quantisation: Quantisation, *, width: int) -> IndexBuild:
    with conn.cursor() as cur:
        started = time.monotonic()
        cur.execute(index_statement(quantisation, width=width, index_name="bench_quantised"))
        elapsed = time.monotonic() - started
        cur.execute("ANALYZE weft_nodes")
        cur.execute("SELECT pg_relation_size('bench_quantised')")
        size_row = cur.fetchone()
    if size_row is None:
        raise bench_latency.MeasurementRefusedError(
            "the database reported no index size after CREATE INDEX"
        )
    index_bytes = int(size_row[0])
    print(
        f"quantisation: {quantisation.value}  index bench_quantised: {index_bytes:,} bytes, "
        f"built in {elapsed:.2f} s"
    )
    return IndexBuild(quantisation=quantisation, build_seconds=elapsed, index_bytes=index_bytes)


def _drop_index(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP INDEX bench_quantised")


def _explain_plan(
    conn: psycopg.Connection, statement: sql.Composed, params: dict[str, object]
) -> bench_filtered.PlanShape:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("EXPLAIN {}").format(statement), params)
        lines = [str(row[0]) for row in cur.fetchall()]
    return bench_filtered.classify_plan(lines, index_name="bench_quantised")


def _run_arm(
    conn: psycopg.Connection,
    *,
    quantisation: Quantisation,
    width: int,
    selectivity: bench_filtered.Selectivity | None,
    oversampling: int,
    sample: Sequence[str],
    fetched: dict[str, object],
    truth: dict[bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]],
) -> QuantisedArmResult:
    statement = rescored_statement(quantisation, width=width, selectivity=selectivity)
    candidate_count = candidates(oversampling, top_k=_TOP_K)
    first_params = {
        "vector": fetched[sample[0]],
        "top_k": _TOP_K,
        "candidates": candidate_count,
    }
    plan = _explain_plan(conn, statement, first_params)

    rows_before = _row_count(conn)
    returned_counts: list[int] = []
    recalls: list[float] = []
    seconds: list[float] = []
    with conn.cursor() as cur:
        for node_id in sample:
            params = {"vector": fetched[node_id], "top_k": _TOP_K, "candidates": candidate_count}
            started = time.monotonic()
            cur.execute(statement, params)
            found_rows = cur.fetchall()
            seconds.append(time.monotonic() - started)
            found_ids = tuple(str(row[0]) for row in found_rows)
            returned_counts.append(len(found_ids))
            recalls.append(
                bench_filtered.recall_at_k(truth[selectivity][node_id], found_ids, k=_TOP_K)
            )
    rows_after = _row_count(conn)
    bench_latency.assert_rows(label="after", expected=rows_before, found=rows_after)

    milliseconds = [value * 1000 for value in seconds]
    result = QuantisedArmResult(
        quantisation=quantisation,
        selectivity=selectivity,
        oversampling=oversampling,
        queries=len(sample),
        returned_min=min(returned_counts),
        recall_at_10=statistics.fmean(recalls),
        p50_ms=bench_latency.percentile(milliseconds, 0.50),
        p95_ms=bench_latency.percentile(milliseconds, 0.95),
        plan=plan,
        rows_before=rows_before,
        rows_after=rows_after,
    )
    print(
        f"quantisation: {quantisation.value}  "
        f"filter: {selectivity.value if selectivity is not None else 'unfiltered'}  "
        f"oversampling: {oversampling}  returned: min {result.returned_min}  "
        f"recall@10: {result.recall_at_10:.3f}  "
        f"p50: {result.p50_ms:.1f} ms  p95: {result.p95_ms:.1f} ms  plan: {plan.value}  "
        f"before: {rows_before:,} rows  after: {rows_after:,} rows"
    )
    return result


def main(argv: list[str] | None = None) -> int:
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

    admin_dsn = arguments.admin_dsn or os.environ.get("WEFT_DATABASE_URL")
    if not admin_dsn:
        print("no admin DSN: pass --admin-dsn or set WEFT_DATABASE_URL", file=sys.stderr)
        return 2

    machine = bench_latency.host_machine()
    print(f"machine: {machine.label}")

    name = _database_name(arguments.width)
    created = False

    try:
        with psycopg.connect(admin_dsn, autocommit=True) as admin, admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            if cur.fetchone() is not None:
                raise bench_latency.MeasurementRefusedError(
                    f"database {name!r} already exists; refusing to reuse or drop it"
                )
        created = True
        _load(admin_dsn, name, arguments.vector_set, arguments.rows)
        database_dsn = make_conninfo(admin_dsn, dbname=name)

        with psycopg.connect(database_dsn, autocommit=True) as conn:
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

            sample = bench_latency.query_sample(ids, arguments.queries)
            fetched = _fetch_vectors(conn, sample)
            truth = _ground_truth(conn, sample, fetched)

            builds: list[IndexBuild] = []
            results: list[QuantisedArmResult] = []
            for quantisation in Quantisation:
                builds.append(_build_index(conn, quantisation, width=arguments.width))
                for selectivity in (None, bench_filtered.Selectivity.ONE_PERCENT):
                    for factor in OVERSAMPLING:
                        results.append(
                            _run_arm(
                                conn,
                                quantisation=quantisation,
                                width=arguments.width,
                                selectivity=selectivity,
                                oversampling=factor,
                                sample=sample,
                                fetched=fetched,
                                truth=truth,
                            )
                        )
                _drop_index(conn)

        if arguments.record is not None:
            run = QuantisedRun(
                machine=machine,
                database=name,
                vector_set=arguments.vector_set.name,
                rows=rows,
                width=arguments.width,
                pgvector_version=pgvector_version,
                server_version=server_version,
                alter_seconds=alter_seconds,
                builds=tuple(builds),
                results=tuple(results),
                taken_at=datetime.now(UTC),
            )
            arguments.record.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        if arguments.keep:
            print(f"kept: {name}")
        else:
            _drop_database(admin_dsn, name)
        return 0
    except (
        bench_latency.MeasurementRefusedError,
        bench_latency.RowCountMismatchError,
        ValueError,
        psycopg.Error,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        if created and not arguments.keep:
            _drop_database(admin_dsn, name)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
