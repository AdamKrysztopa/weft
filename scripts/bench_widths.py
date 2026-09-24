"""Width-sweep recall harness for Phase 29 task **29.10**.

Exact-scan and HNSW recall@10 at widths 256, 512, 1024, 1536 and 2000, each against the
native-width exact ranking, so that truncation error (narrowing the vector) and index error
(searching it with HNSW) are two separate numbers rather than one conflated one. Alongside that,
whether truncating and renormalising a native vector reproduces what the embedding API itself
returns at that `dimensions` value, on a sample — so a truncation-based sweep is checked against
the thing it is standing in for before its numbers are trusted.

This module's pure functions (the sweep widths, the cosine floor, and the comparison that decides
"reproduces") are pinned by `tests/unit/scripts/test_bench_widths.py`. `main` is not
unit-tested — it drives a real database and the OpenAI API, and is exercised by actually running
it.
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import bench_filtered
import bench_latency
import bench_vectors
import openai
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, ConfigDict

WIDTHS: Final[tuple[int, ...]] = (256, 512, 1024, 1536, 2000)
MIN_COSINE: Final[float] = 0.9999

_TOP_K: Final[int] = 10


class TruncationComparison(BaseModel):
    """Whether a native vector, truncated and renormalised, matches what the API returned."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: int
    cosine: float
    reproduces: bool


def compare_truncation(native: Sequence[float], api: Sequence[float]) -> TruncationComparison:
    """Check whether truncating the native vector reproduces what the API returns at that width.

    Args:
        native: The full-width vector as stored.
        api: The vector the API returned when asked for a narrower width.

    Returns:
        The cosine between the two, and whether it clears `MIN_COSINE`.

    Raises:
        ValueError: `api` is wider than `native`, or is a zero vector.
    """
    if len(api) > len(native):
        message = (
            f"cannot compare at width {len(api)}: the native vector has {len(native)} components"
        )
        raise ValueError(message)
    truncated = bench_filtered.truncate_renormalise(native, len(api))
    norm = math.sqrt(sum(v * v for v in api))
    if norm == 0.0:
        raise ValueError("cannot normalise a zero API vector")
    normalised_api = tuple(v / norm for v in api)
    cosine = sum(t * a for t, a in zip(truncated, normalised_api, strict=True))
    return TruncationComparison(width=len(api), cosine=cosine, reproduces=cosine >= MIN_COSINE)


# ---------------------------------------------------------------------------------------------
# The driving half: not unit-tested, run against a real database and the OpenAI API.
# ---------------------------------------------------------------------------------------------


class ApiComparison(BaseModel):
    """One width's truncation-vs-API agreement, over the whole `--sample`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: int
    samples: int
    min_cosine: float
    mean_cosine: float
    reproduces: bool


class WidthResult(BaseModel):
    """One width's exact-scan and HNSW recall against the native exact ranking."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    width: int
    exact_recall_vs_native: float
    hnsw_recall_vs_native: float
    hnsw_recall_vs_exact: float
    exact_p95_ms: float
    hnsw_p95_ms: float
    index_build_seconds: float
    index_bytes: int
    rows_before: int
    rows_after: int


class WidthsRun(BaseModel):
    """The one JSON record `--record` writes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: bench_latency.Machine
    database: str
    vector_set: str
    rows: int
    native_width: int
    pgvector_version: str
    server_version: str
    api: tuple[ApiComparison, ...]
    results: tuple[WidthResult, ...]
    taken_at: datetime


def _count_tokens(contents: Sequence[str]) -> int:
    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")
    return sum(len(encoding.encode(content)) for content in contents)


def _sampled_rows(
    vector_set_dir: Path, vector_set: bench_vectors.VectorSet, *, sample: int
) -> tuple[tuple[str, ...], list[str], list[tuple[float, ...]]]:
    nodes_table = next(table for table in vector_set.tables if table.name == "weft_nodes")
    id_index = nodes_table.columns.index("id")
    content_index = nodes_table.columns.index("content")
    vectors = bench_vectors.open_vectors(vector_set_dir, vector_set.meta)

    ids = tuple(str(row[id_index]) for row in nodes_table.rows)
    sampled_ids = bench_latency.query_sample(ids, sample)
    row_by_id = {str(row[id_index]): position for position, row in enumerate(nodes_table.rows)}

    contents: list[str] = []
    natives: list[tuple[float, ...]] = []
    for node_id in sampled_ids:
        position = row_by_id[node_id]
        content = nodes_table.rows[position][content_index]
        if content is None:
            raise bench_latency.MeasurementRefusedError(
                f"sampled id {node_id!r} has no content to embed"
            )
        contents.append(str(content))
        natives.append(tuple(float(component) for component in vectors[position]))
    return sampled_ids, contents, natives


def _compare_against_api(
    vector_set_dir: Path,
    vector_set: bench_vectors.VectorSet,
    *,
    sample: int,
    yes: bool,
) -> tuple[ApiComparison, ...] | None:
    """`None` means the run was refused for lack of `--yes` — already explained on stderr."""
    sampled_ids, contents, natives = _sampled_rows(vector_set_dir, vector_set, sample=sample)

    tokens = _count_tokens(contents)
    bench_vectors.print_sketch(
        bench_vectors.sketch_cost(
            pdfs=0,
            chunks=len(sampled_ids) * len(WIDTHS),
            tokens=tokens * len(WIDTHS),
            model=vector_set.meta.model,
        )
    )
    if not yes:
        print("pass --yes to spend this", file=sys.stderr)
        return None

    if not os.environ.get("OPENAI_API_KEY"):
        raise bench_latency.MeasurementRefusedError(
            "OPENAI_API_KEY is not set; refusing to build an OpenAI client to spend against"
        )

    client = openai.OpenAI()
    return tuple(
        _compare_width(
            client,
            model=vector_set.meta.model.value,
            width=width,
            contents=contents,
            natives=natives,
        )
        for width in WIDTHS
    )


def _compare_width(
    client: openai.OpenAI,
    *,
    model: str,
    width: int,
    contents: Sequence[str],
    natives: Sequence[tuple[float, ...]],
) -> ApiComparison:
    per_row: list[TruncationComparison] = []
    for content, native in zip(contents, natives, strict=True):
        response = client.embeddings.create(model=model, input=[content], dimensions=width)
        api_vector = tuple(float(component) for component in response.data[0].embedding)
        per_row.append(compare_truncation(native, api_vector))
    cosines = [comparison.cosine for comparison in per_row]
    result = ApiComparison(
        width=width,
        samples=len(per_row),
        min_cosine=min(cosines),
        mean_cosine=statistics.fmean(cosines),
        reproduces=all(comparison.reproduces for comparison in per_row),
    )
    print(
        f"api width {width}: samples {result.samples}  min cosine {result.min_cosine:.6f}  "
        f"mean cosine {result.mean_cosine:.6f}  reproduces {result.reproduces}"
    )
    return result


def _database_name() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"weft_bench_widths_{stamp}"


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


def _native_truth(
    conn: psycopg.Connection, sample: Sequence[str]
) -> tuple[dict[str, object], dict[str, tuple[str, ...]]]:
    fetched: dict[str, object] = {}
    truth: dict[str, tuple[str, ...]] = {}
    with conn.cursor() as cur:
        for node_id in sample:
            cur.execute("SELECT embedding FROM weft_nodes WHERE id = %s", (node_id,))
            row = cur.fetchone()
            if row is None:
                raise bench_latency.MeasurementRefusedError(
                    f"sampled id {node_id!r} is no longer in the table"
                )
            fetched[node_id] = row[0]
            cur.execute(
                "SELECT id FROM weft_nodes WHERE embedding IS NOT NULL "
                "ORDER BY embedding <=> %(vector)s LIMIT %(top_k)s",
                {"vector": row[0], "top_k": _TOP_K},
            )
            truth[node_id] = tuple(str(found[0]) for found in cur.fetchall())
    return fetched, truth


def _measure_width(
    conn: psycopg.Connection,
    *,
    width: int,
    sample: Sequence[str],
    fetched: dict[str, object],
    truth: dict[str, tuple[str, ...]],
    expected_rows: int,
) -> WidthResult:
    column_name = f"emb_{width}"
    column = sql.Identifier(column_name)
    index_name = f"bench_hnsw_{width}"

    rows_before = _row_count(conn)
    bench_latency.assert_rows(
        label=f"width {width} before", expected=expected_rows, found=rows_before
    )

    with conn.cursor() as cur:
        started = time.monotonic()
        cur.execute(
            sql.SQL("ALTER TABLE weft_nodes ADD COLUMN {col} vector({width})").format(
                col=column, width=sql.Literal(width)
            )
        )
        cur.execute(
            sql.SQL(
                "UPDATE weft_nodes SET {col} = l2_normalize(subvector(embedding, 1, {width}))"
            ).format(col=column, width=sql.Literal(width))
        )
        populate_seconds = time.monotonic() - started
    print(f"width {width}: typed and populated {column_name} in {populate_seconds:.2f} s")

    ranking_statement = sql.SQL(
        "SELECT id FROM weft_nodes ORDER BY {col} <=> l2_normalize(subvector(%(vector)s, 1, "
        "{width})) LIMIT %(top_k)s"
    ).format(col=column, width=sql.Literal(width))

    exact_seconds: list[float] = []
    exact_result: dict[str, tuple[str, ...]] = {}
    with conn.cursor() as cur:
        for node_id in sample:
            started = time.monotonic()
            cur.execute(ranking_statement, {"vector": fetched[node_id], "top_k": _TOP_K})
            found_rows = cur.fetchall()
            exact_seconds.append(time.monotonic() - started)
            exact_result[node_id] = tuple(str(found[0]) for found in found_rows)

    with conn.cursor() as cur:
        started = time.monotonic()
        cur.execute(
            sql.SQL("CREATE INDEX {idx} ON weft_nodes USING hnsw ({col} vector_cosine_ops)").format(
                idx=sql.Identifier(index_name), col=column
            )
        )
        index_build_seconds = time.monotonic() - started
        cur.execute("ANALYZE weft_nodes")
        cur.execute(sql.SQL("SELECT pg_relation_size({})").format(sql.Literal(index_name)))
        size_row = cur.fetchone()
    if size_row is None:
        raise bench_latency.MeasurementRefusedError(
            f"the database reported no index size for {index_name} after CREATE INDEX"
        )
    index_bytes = int(size_row[0])
    print(
        f"width {width}: index {index_name} {index_bytes:,} bytes, "
        f"built in {index_build_seconds:.2f} s"
    )

    hnsw_seconds: list[float] = []
    hnsw_result: dict[str, tuple[str, ...]] = {}
    with conn.cursor() as cur:
        for node_id in sample:
            started = time.monotonic()
            cur.execute(ranking_statement, {"vector": fetched[node_id], "top_k": _TOP_K})
            found_rows = cur.fetchall()
            hnsw_seconds.append(time.monotonic() - started)
            hnsw_result[node_id] = tuple(str(found[0]) for found in found_rows)

    exact_recalls = [
        bench_filtered.recall_at_k(truth[node_id], exact_result[node_id], k=_TOP_K)
        for node_id in sample
    ]
    hnsw_vs_native_recalls = [
        bench_filtered.recall_at_k(truth[node_id], hnsw_result[node_id], k=_TOP_K)
        for node_id in sample
    ]
    hnsw_vs_exact_recalls = [
        bench_filtered.recall_at_k(exact_result[node_id], hnsw_result[node_id], k=_TOP_K)
        for node_id in sample
    ]

    rows_after = _row_count(conn)
    bench_latency.assert_rows(
        label=f"width {width} after", expected=expected_rows, found=rows_after
    )

    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP INDEX {}").format(sql.Identifier(index_name)))
        cur.execute(sql.SQL("ALTER TABLE weft_nodes DROP COLUMN {}").format(column))

    exact_ms = [seconds * 1000 for seconds in exact_seconds]
    hnsw_ms = [seconds * 1000 for seconds in hnsw_seconds]
    result = WidthResult(
        width=width,
        exact_recall_vs_native=statistics.fmean(exact_recalls),
        hnsw_recall_vs_native=statistics.fmean(hnsw_vs_native_recalls),
        hnsw_recall_vs_exact=statistics.fmean(hnsw_vs_exact_recalls),
        exact_p95_ms=bench_latency.percentile(exact_ms, 0.95),
        hnsw_p95_ms=bench_latency.percentile(hnsw_ms, 0.95),
        index_build_seconds=index_build_seconds,
        index_bytes=index_bytes,
        rows_before=rows_before,
        rows_after=rows_after,
    )
    print(
        f"width: {width}  exact vs native: {result.exact_recall_vs_native:.3f}  "
        f"hnsw vs native: {result.hnsw_recall_vs_native:.3f}  "
        f"hnsw vs exact: {result.hnsw_recall_vs_exact:.3f}  "
        f"exact p95: {result.exact_p95_ms:.1f} ms  hnsw p95: {result.hnsw_p95_ms:.1f} ms  "
        f"before: {rows_before:,} rows  after: {rows_after:,} rows"
    )
    return result


_FAILURES: Final = (
    bench_latency.MeasurementRefusedError,
    bench_latency.RowCountMismatchError,
    ValueError,
    psycopg.Error,
    OSError,
    openai.OpenAIError,
)


def _prepare(
    arguments: argparse.Namespace, *, admin_dsn: str, name: str
) -> tuple[bench_vectors.VectorSet, tuple[ApiComparison, ...]] | None:
    """`None` means the run was refused for lack of `--yes` — already explained on stderr."""
    vector_set = bench_vectors.read_vector_set(arguments.vector_set)
    api = _compare_against_api(
        arguments.vector_set, vector_set, sample=arguments.sample, yes=arguments.yes
    )
    if api is None:
        return None

    with psycopg.connect(admin_dsn, autocommit=True) as admin, admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if cur.fetchone() is not None:
            raise bench_latency.MeasurementRefusedError(
                f"database {name!r} already exists; refusing to reuse or drop it"
            )
    return vector_set, api


def _measure_and_record(
    arguments: argparse.Namespace,
    *,
    admin_dsn: str,
    name: str,
    machine: bench_latency.Machine,
    vector_set: bench_vectors.VectorSet,
    api: tuple[ApiComparison, ...],
) -> None:
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

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM weft_nodes ORDER BY id")
            ids = [str(row[0]) for row in cur.fetchall()]
        sample = bench_latency.query_sample(ids, arguments.queries)
        fetched, truth = _native_truth(conn, sample)

        results = tuple(
            _measure_width(
                conn,
                width=width,
                sample=sample,
                fetched=fetched,
                truth=truth,
                expected_rows=rows,
            )
            for width in WIDTHS
        )

    if arguments.record is not None:
        run = WidthsRun(
            machine=machine,
            database=name,
            vector_set=arguments.vector_set.name,
            rows=rows,
            native_width=vector_set.meta.width,
            pgvector_version=pgvector_version,
            server_version=server_version,
            api=api,
            results=results,
            taken_at=datetime.now(UTC),
        )
        arguments.record.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    if arguments.keep:
        print(f"kept: {name}")
    else:
        _drop_database(admin_dsn, name)


def main(argv: list[str] | None = None) -> int:
    """Compare truncated widths against the API, then measure each width in a fresh database.

    The database is dropped afterwards unless `--keep`.

    Args:
        argv: Command-line arguments; `None` reads `sys.argv`.

    Returns:
        0 on a completed run, 2 when the run was refused, unconfirmed by `--yes`, or failed.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--set", dest="vector_set", type=Path, required=True, help="a 29.6 vector set directory"
    )
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--admin-dsn", default=None)
    parser.add_argument("--record", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--yes", action="store_true")
    arguments = parser.parse_args(argv)

    admin_dsn = arguments.admin_dsn or os.environ.get("WEFT_DATABASE_URL")
    if not admin_dsn:
        print("no admin DSN: pass --admin-dsn or set WEFT_DATABASE_URL", file=sys.stderr)
        return 2

    machine = bench_latency.host_machine()
    print(f"machine: {machine.label}")

    name = _database_name()

    try:
        prepared = _prepare(arguments, admin_dsn=admin_dsn, name=name)
    except _FAILURES as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if prepared is None:
        return 2
    vector_set, api = prepared

    try:
        _measure_and_record(
            arguments,
            admin_dsn=admin_dsn,
            name=name,
            machine=machine,
            vector_set=vector_set,
            api=api,
        )
    except _FAILURES as exc:
        print(str(exc), file=sys.stderr)
        if not arguments.keep:
            _drop_database(admin_dsn, name)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
