"""StreamingDiskANN harness for Phase 29 task **29.9**.

Build time, index size, recall@10 and p95 for `vectorscale`'s `diskann` index on a typed
`vector(n)` column in `timescale/timescaledb-ha:pg17`, against an exact scan re-taken in the same
image, at the four selectivities `bench_filtered` already owns (50%, 10%, 1%, 0.1%) — filtered two
ways: through the store's own JSONB post-filter (`bench_filtered.bucket_predicate`) and through a
`smallint[]` label column the extension plans as an index condition (`fix-plans/07` Finding 3;
position 5, measured and not proposed). It also probes whether an expression `diskann` index over
a bare, undimensioned `vector` column can be built and queried on the vectorscale version the run
finds, since that ability is version-dependent and not assumed.

This module's pure functions (the selectivity-to-label mapping, a row's labels, the two index
statements, the label-filtered statement) are pinned by
`tests/unit/scripts/test_bench_diskann.py`. `main` is not unit-tested — it drives a real database
on a different image than the rest of this suite's `WEFT_DATABASE_URL`, and is exercised by
actually running it.
"""

from __future__ import annotations

import argparse
import json
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
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

_TOP_K: Final[int] = 10
_REQUIRED_IMAGE: Final[str] = "timescale/timescaledb-ha:pg17"


def label_of(selectivity: bench_filtered.Selectivity) -> int:
    return {
        bench_filtered.Selectivity.HALF: 1,
        bench_filtered.Selectivity.TENTH: 2,
        bench_filtered.Selectivity.ONE_PERCENT: 3,
        bench_filtered.Selectivity.TENTH_OF_A_PERCENT: 4,
    }[selectivity]


def labels_for(node_id: str) -> tuple[int, ...]:
    return tuple(
        sorted(
            label_of(selectivity)
            for selectivity in bench_filtered.Selectivity
            if bench_filtered.in_bucket(node_id, selectivity)
        )
    )


def index_statement(*, index_name: str, with_labels: bool) -> sql.Composed:
    """`vectorscale--0.9.1.sql`: `vector_cosine_ops` is `DEFAULT` for `diskann`, and
    `vector_smallint_label_ops` is `DEFAULT FOR TYPE smallint[]`, so `labels` needs no class named.
    """
    columns = (
        sql.SQL("embedding vector_cosine_ops, labels")
        if with_labels
        else sql.SQL("embedding vector_cosine_ops")
    )
    return sql.SQL("CREATE INDEX {name} ON weft_nodes USING diskann ({columns})").format(
        name=sql.Identifier(index_name), columns=columns
    )


def label_filtered_statement(selectivity: bench_filtered.Selectivity) -> sql.Composed:
    return sql.SQL(
        "SELECT id, embedding <=> %(vector)s AS distance FROM weft_nodes "
        "WHERE embedding IS NOT NULL AND labels && ARRAY[{label}]::smallint[] "
        "ORDER BY embedding <=> %(vector)s LIMIT %(top_k)s"
    ).format(label=sql.Literal(label_of(selectivity)))


class DiskannArm(StrEnum):
    JSONB_POST_FILTER = "jsonb post-filter"
    LABEL_COLUMN = "label column"


class IndexBuild(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    build_seconds: float
    index_bytes: int


class ExpressionProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    built: bool
    queryable: bool
    error: str | None


class DiskannArmResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: DiskannArm
    selectivity: bench_filtered.Selectivity | None
    queries: int
    returned_min: int
    recall_at_10: float
    p50_ms: float
    p95_ms: float
    plan: bench_filtered.PlanShape
    rows_before: int
    rows_after: int


class DiskannRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: bench_latency.Machine
    database: str
    vector_set: str
    rows: int
    width: int
    server_version: str
    pgvector_version: str
    vectorscale_version: str
    query_rescore: str
    query_search_list_size: str
    plain_build: IndexBuild
    labelled_build: IndexBuild
    matching_rows: tuple[bench_filtered.SelectivityCount, ...]
    results: tuple[DiskannArmResult, ...]
    expression_probe: ExpressionProbe
    taken_at: datetime


# ---------------------------------------------------------------------------------------------
# The driving half: not unit-tested, run against a real database by the dispatcher.
# ---------------------------------------------------------------------------------------------


def _database_name(width: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"weft_bench_diskann_{width}_{stamp}"


def _drop_database(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def _preflight(admin_dsn: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SHOW server_version_num")
        version_row = cur.fetchone()
        if version_row is None or int(version_row[0]) < 170_000:
            raise bench_latency.MeasurementRefusedError(
                f"the admin DSN's server is not PostgreSQL 17 or later; "
                f"this harness requires {_REQUIRED_IMAGE}"
            )
        cur.execute(
            "SELECT default_version FROM pg_available_extensions WHERE name = 'vectorscale'"
        )
        if cur.fetchone() is None:
            raise bench_latency.MeasurementRefusedError(
                f"the admin DSN's server has no vectorscale extension available; "
                f"this harness requires {_REQUIRED_IMAGE}"
            )


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


def _truncate_column(conn: psycopg.Connection, *, width: int) -> float:
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
    bench_latency.assert_rows(label="truncated", expected=rows_before, found=rows_after)
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


def _write_labels(conn: psycopg.Connection, ids: Sequence[str]) -> None:
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE weft_nodes ADD COLUMN labels smallint[]")
        cur.execute("CREATE TEMP TABLE bench_labels (id text PRIMARY KEY, labels smallint[])")
        with cur.copy("COPY bench_labels (id, labels) FROM STDIN") as copy:
            for node_id in ids:
                copy.write_row((node_id, list(labels_for(node_id))))
        cur.execute(
            "UPDATE weft_nodes n SET labels = t.labels FROM bench_labels t WHERE n.id = t.id"
        )
        bench_latency.assert_rows(label="labels", expected=len(ids), found=cur.rowcount)


def _matching_rows(conn: psycopg.Connection) -> tuple[bench_filtered.SelectivityCount, ...]:
    counts: list[bench_filtered.SelectivityCount] = []
    with conn.cursor() as cur:
        for selectivity in bench_filtered.Selectivity:
            cur.execute(
                sql.SQL("SELECT count(*) FROM weft_nodes WHERE {p}").format(
                    p=bench_filtered.bucket_predicate(selectivity)
                )
            )
            jsonb_row = cur.fetchone()
            cur.execute(
                sql.SQL(
                    "SELECT count(*) FROM weft_nodes WHERE labels && ARRAY[{label}]::smallint[]"
                ).format(label=sql.Literal(label_of(selectivity)))
            )
            label_row = cur.fetchone()
            if jsonb_row is None or label_row is None:
                raise bench_latency.MeasurementRefusedError(
                    f"selectivity {selectivity.value} reported no row count"
                )
            jsonb_count, label_count = int(jsonb_row[0]), int(label_row[0])
            if jsonb_count != label_count:
                raise bench_latency.MeasurementRefusedError(
                    f"selectivity {selectivity.value}: the jsonb bucket matches {jsonb_count:,} "
                    f"rows but label {label_of(selectivity)} matches {label_count:,} rows"
                )
            if jsonb_count == 0:
                raise bench_latency.MeasurementRefusedError(
                    f"selectivity {selectivity.value} matches 0 rows; refusing an empty filter"
                )
            print(f"selectivity {selectivity.value}: {jsonb_count:,} matching rows")
            counts.append(
                bench_filtered.SelectivityCount(selectivity=selectivity, rows=jsonb_count)
            )
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
) -> dict[bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]]:
    truth: dict[bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]] = {}
    with conn.cursor() as cur:
        for selectivity in (None, *bench_filtered.Selectivity):
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


def _build_index(conn: psycopg.Connection, *, index_name: str, with_labels: bool) -> IndexBuild:
    with conn.cursor() as cur:
        started = time.monotonic()
        cur.execute(index_statement(index_name=index_name, with_labels=with_labels))
        elapsed = time.monotonic() - started
        cur.execute("ANALYZE weft_nodes")
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT pg_relation_size({})").format(sql.Literal(index_name)))
        size_row = cur.fetchone()
    if size_row is None:
        raise bench_latency.MeasurementRefusedError(
            f"the database reported no index size for {index_name} after CREATE INDEX"
        )
    index_bytes = int(size_row[0])
    print(
        f"index {index_name} (labels={with_labels}): {index_bytes:,} bytes, "
        f"built in {elapsed:.2f} s"
    )
    return IndexBuild(build_seconds=elapsed, index_bytes=index_bytes)


def _explain_plan(
    conn: psycopg.Connection, statement: sql.Composed, vector: object, *, index_name: str
) -> bench_filtered.PlanShape:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("EXPLAIN {}").format(statement), {"vector": vector, "top_k": _TOP_K})
        lines = [str(row[0]) for row in cur.fetchall()]
    return bench_filtered.classify_plan(lines, index_name=index_name)


def _run_arm(
    conn: psycopg.Connection,
    *,
    arm: DiskannArm,
    selectivity: bench_filtered.Selectivity | None,
    statement: sql.Composed,
    sample: Sequence[str],
    fetched: dict[str, object],
    truth: dict[bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]],
) -> DiskannArmResult:
    plan = _explain_plan(conn, statement, fetched[sample[0]], index_name="bench_diskann")

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
            recalls.append(
                bench_filtered.recall_at_k(truth[selectivity][node_id], found_ids, k=_TOP_K)
            )
    rows_after = _row_count(conn)
    bench_latency.assert_rows(label="after", expected=rows_before, found=rows_after)

    milliseconds = [value * 1000 for value in seconds]
    result = DiskannArmResult(
        arm=arm,
        selectivity=selectivity,
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
        f"arm: {arm.value}  "
        f"filter: {selectivity.value if selectivity is not None else 'unfiltered'}  "
        f"returned: min {result.returned_min}  recall@10: {result.recall_at_10:.3f}  "
        f"p50: {result.p50_ms:.1f} ms  p95: {result.p95_ms:.1f} ms  plan: {plan.value}  "
        f"before: {rows_before:,} rows  after: {rows_after:,} rows"
    )
    return result


def _expression_probe(conn: psycopg.Connection) -> ExpressionProbe:
    built = False
    queryable = False
    error: str | None = None

    with conn.cursor() as cur:
        cur.execute("CREATE TABLE bench_bare (id int PRIMARY KEY, embedding vector)")
        with cur.copy("COPY bench_bare (id, embedding) FROM STDIN") as copy:
            for i in range(200):
                copy.write_row((i, PgVector(list(bench_latency.synthetic_vector(str(i), 8)))))

    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE INDEX bench_bare_diskann ON bench_bare "
                "USING diskann ((embedding::vector(8)) vector_cosine_ops)"
            )
        built = True
    except psycopg.Error as exc:
        error = str(exc)

    try:
        with conn.cursor() as cur:
            probe_vector = PgVector(list(bench_latency.synthetic_vector("0", 8)))
            cur.execute(
                "SELECT id FROM bench_bare ORDER BY embedding::vector(8) <=> %(v)s::vector(8) "
                "LIMIT 10",
                {"v": probe_vector},
            )
            cur.fetchall()
        queryable = True
    except psycopg.Error as exc:
        if error is None:
            error = str(exc)

    return ExpressionProbe(built=built, queryable=queryable, error=error)


def _print_probe(version: str, probe: ExpressionProbe) -> None:
    built = "yes" if probe.built else "no"
    queryable = "yes" if probe.queryable else "no"
    suffix = f" ({probe.error})" if probe.error is not None else ""
    print(
        f"vectorscale {version}  expression index over bare column: "
        f"built = {built}  queryable = {queryable}{suffix}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--set", dest="vector_set", type=Path, required=True, help="a 29.6 vector set directory"
    )
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument(
        "--admin-dsn",
        required=True,
        help=f"a PostgreSQL 17 server with vectorscale available ({_REQUIRED_IMAGE})",
    )
    parser.add_argument("--record", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    arguments = parser.parse_args(argv)

    admin_dsn = arguments.admin_dsn
    name = _database_name(arguments.width)
    created = False

    try:
        _preflight(admin_dsn)

        machine = bench_latency.host_machine()
        print(f"machine: {machine.label}")

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
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE")

            rows = _row_count(conn)
            with conn.cursor() as cur:
                cur.execute("SHOW server_version")
                server_row = cur.fetchone()
                cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                vector_row = cur.fetchone()
                cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vectorscale'")
                vectorscale_row = cur.fetchone()
            if server_row is None or vector_row is None or vectorscale_row is None:
                raise bench_latency.MeasurementRefusedError(
                    "the database reported no server version or extension versions"
                )
            server_version = str(server_row[0])
            pgvector_version = str(vector_row[0])
            vectorscale_version = str(vectorscale_row[0])
            print(
                f"rows: {rows:,}  server: {server_version}  "
                f"pgvector: {pgvector_version}  vectorscale: {vectorscale_version}"
            )

            _truncate_column(conn, width=arguments.width)

            with conn.cursor() as cur:
                cur.execute("SELECT id FROM weft_nodes ORDER BY id")
                ids = [str(row[0]) for row in cur.fetchall()]
            _write_buckets(conn, ids)
            _write_labels(conn, ids)
            matching_rows = _matching_rows(conn)

            sample = bench_latency.query_sample(ids, arguments.queries)
            fetched = _fetch_vectors(conn, sample)
            truth = _ground_truth(conn, sample, fetched)

            results: list[DiskannArmResult] = []

            plain_build = _build_index(conn, index_name="bench_diskann", with_labels=False)
            with conn.cursor() as cur:
                cur.execute("SHOW diskann.query_rescore")
                rescore_row = cur.fetchone()
                cur.execute("SHOW diskann.query_search_list_size")
                search_list_row = cur.fetchone()
            if rescore_row is None or search_list_row is None:
                raise bench_latency.MeasurementRefusedError(
                    "the database reported no diskann.query_rescore or query_search_list_size"
                )
            query_rescore = str(rescore_row[0])
            query_search_list_size = str(search_list_row[0])
            print(
                f"diskann.query_rescore = {query_rescore}  "
                f"diskann.query_search_list_size = {query_search_list_size}"
            )

            for selectivity in (None, *bench_filtered.Selectivity):
                statement = (
                    bench_filtered.unfiltered_statement()
                    if selectivity is None
                    else bench_filtered.filtered_statement(selectivity)
                )
                results.append(
                    _run_arm(
                        conn,
                        arm=DiskannArm.JSONB_POST_FILTER,
                        selectivity=selectivity,
                        statement=statement,
                        sample=sample,
                        fetched=fetched,
                        truth=truth,
                    )
                )
            with conn.cursor() as cur:
                cur.execute("DROP INDEX bench_diskann")

            labelled_build = _build_index(conn, index_name="bench_diskann", with_labels=True)
            for selectivity in bench_filtered.Selectivity:
                results.append(
                    _run_arm(
                        conn,
                        arm=DiskannArm.LABEL_COLUMN,
                        selectivity=selectivity,
                        statement=label_filtered_statement(selectivity),
                        sample=sample,
                        fetched=fetched,
                        truth=truth,
                    )
                )
            with conn.cursor() as cur:
                cur.execute("DROP INDEX bench_diskann")

            probe = _expression_probe(conn)
            _print_probe(vectorscale_version, probe)

        if arguments.record is not None:
            run = DiskannRun(
                machine=machine,
                database=name,
                vector_set=arguments.vector_set.name,
                rows=rows,
                width=arguments.width,
                server_version=server_version,
                pgvector_version=pgvector_version,
                vectorscale_version=vectorscale_version,
                query_rescore=query_rescore,
                query_search_list_size=query_search_list_size,
                plain_build=plain_build,
                labelled_build=labelled_build,
                matching_rows=matching_rows,
                results=tuple(results),
                expression_probe=probe,
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
