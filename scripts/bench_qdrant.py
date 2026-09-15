"""Qdrant filtered-search harness for Phase 29 task **29.11**.

recall@10 against pgvector's exact ranking, rows returned, and p50/p95, for Qdrant at the same four
selectivities `bench_filtered.py` measures against HNSW, with no payload index and with one built
over every bucket field before ingest. The condition itself is the store's own public translator,
`weft_qdrant.store.to_qdrant_filter`, over a `Filter` this harness builds from `bench_filtered`'s
own bucket vocabulary — so a caller who filters through `weft_store.contract.Filter` is measured,
never a hand-written Qdrant condition a reviewer would have to trust matched it.

This module's pure functions (the two arms, the bucket `Filter`, the point payload, the
payload-index field list) are pinned by `tests/unit/scripts/test_bench_qdrant.py`. `main` is not
unit-tested — it drives a real database and a real Qdrant deployment, and is exercised by actually
running it.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

import bench_filtered
import bench_latency
import numpy as np
import numpy.typing as npt
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from weft_qdrant.store import to_qdrant_filter
from weft_store.contract import Filter, FilterOp

_TOP_K: Final[int] = 10


class PayloadIndexing(StrEnum):
    NONE = "no payload index"
    BEFORE_INGEST = "payload index before ingest"


#: Short, filesystem/collection-name-safe slugs for the two arms — not published, since a
#: collection name is this script's own bookkeeping and nothing reads `PayloadIndexing.value`
#: to derive one.
_COLLECTION_SLUG: Final[dict[PayloadIndexing, str]] = {
    PayloadIndexing.NONE: "noindex",
    PayloadIndexing.BEFORE_INGEST: "indexed",
}


def bucket_filter(selectivity: bench_filtered.Selectivity) -> Filter:
    """The `Filter` a caller would write to ask for this harness's bucket — the same shape
    `weft_qdrant.store.to_qdrant_filter` is measured against, so the condition this script
    times is exactly the one a real query would carry."""
    return Filter(
        op=FilterOp.EQ,
        field=f"ext.{bench_filtered.BENCH_NAMESPACE}.{selectivity.key}",
        value=True,
    )


def point_payload(node_id: str, *, content: str) -> dict[str, object]:
    """A point's payload, with every bucket nested exactly where `bucket_filter`'s dotted
    field looks — `bench_filtered.bench_ext` is the one place that patch is built."""
    return {
        "node_id": node_id,
        "content": content,
        "ext": json.loads(bench_filtered.bench_ext(node_id)),
    }


def payload_index_fields() -> tuple[str, ...]:
    """Every field a payload index is built over, in `Selectivity` order."""
    return tuple(
        f"ext.{bench_filtered.BENCH_NAMESPACE}.{s.key}" for s in bench_filtered.Selectivity
    )


# ---------------------------------------------------------------------------------------------
# The driving half: not unit-tested, run against a real database and Qdrant by the dispatcher.
# ---------------------------------------------------------------------------------------------


class IngestTime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    indexing: PayloadIndexing
    seconds: float


class QdrantArmResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    indexing: PayloadIndexing
    selectivity: bench_filtered.Selectivity | None
    queries: int
    returned_min: int
    recall_at_10: float
    p50_ms: float
    p95_ms: float
    points_before: int
    points_after: int


class QdrantRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: bench_latency.Machine
    database: str
    vector_set: str
    rows: int
    width: int
    qdrant_version: str
    pgvector_version: str
    server_version: str
    ingest_seconds: tuple[IngestTime, ...]
    results: tuple[QdrantArmResult, ...]
    taken_at: datetime


def _database_name(width: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"weft_bench_qdrant_{width}_{stamp}"


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
                copy.write_row((node_id, Jsonb(json.loads(bench_filtered.bench_ext(node_id)))))
        cur.execute(
            "UPDATE weft_nodes n SET ext = n.ext || t.patch FROM bench_buckets t WHERE n.id = t.id"
        )
        bench_latency.assert_rows(label="buckets", expected=len(ids), found=cur.rowcount)
    conn.commit()


def _fetch_vectors(
    conn: psycopg.Connection, sample: Sequence[str]
) -> dict[str, npt.NDArray[np.float32]]:
    fetched: dict[str, npt.NDArray[np.float32]] = {}
    with conn.cursor() as cur:
        for node_id in sample:
            cur.execute("SELECT embedding FROM weft_nodes WHERE id = %s", (node_id,))
            row = cur.fetchone()
            if row is None:
                raise bench_latency.MeasurementRefusedError(
                    f"sampled id {node_id!r} is no longer in the table"
                )
            fetched[node_id] = row[0].to_numpy()
    return fetched


def _ground_truth(
    conn: psycopg.Connection,
    sample: Sequence[str],
    fetched: Mapping[str, npt.NDArray[np.float32]],
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


def _ingest(dsn: str, client: QdrantClient, collection: str) -> float:
    """Stream every row and upsert it into `collection` in batches of 500, timed as one span —
    the same span whichever arm is ingesting, since the vectors and payloads are identical.

    Its own connection, and the one in this harness that is not `autocommit`: a server-side
    cursor is a `DECLARE`, which Postgres refuses outside a transaction. The caller's
    connection stays autocommit so the store's lazy DDL never waits on it (`L22.30`).
    """
    started = time.monotonic()
    batch: list[models.PointStruct] = []
    with psycopg.connect(dsn) as conn:
        # Without this the stream yields pgvector's text form, and `to_numpy` is not on `str`.
        register_vector(conn)
        with conn.cursor(name="bench_qdrant_ingest") as cur:
            cur.itersize = 2000
            cur.execute("SELECT id, content, embedding FROM weft_nodes ORDER BY id")
            for node_id, content, raw_embedding in cur:
                embedding = raw_embedding.to_numpy()
                batch.append(
                    models.PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, node_id)),
                        vector=embedding.tolist(),
                        payload=point_payload(node_id, content=content),
                    )
                )
                if len(batch) >= 500:
                    client.upsert(collection, points=batch, wait=True)
                    batch = []
            if batch:
                client.upsert(collection, points=batch, wait=True)
    return time.monotonic() - started


def _query_arm(
    client: QdrantClient,
    collection: str,
    *,
    selectivity: bench_filtered.Selectivity | None,
    sample: Sequence[str],
    fetched: Mapping[str, npt.NDArray[np.float32]],
    truth: Mapping[bench_filtered.Selectivity | None, Mapping[str, tuple[str, ...]]],
) -> tuple[list[int], list[float], list[float]]:
    query_filter = None if selectivity is None else to_qdrant_filter(bucket_filter(selectivity))
    returned_counts: list[int] = []
    recalls: list[float] = []
    seconds: list[float] = []
    for node_id in sample:
        vector = fetched[node_id]
        started = time.monotonic()
        answered = client.query_points(
            collection,
            query=vector.tolist(),
            query_filter=query_filter,
            limit=_TOP_K,
            with_payload=["node_id"],
        )
        seconds.append(time.monotonic() - started)
        found_ids = tuple(
            str(cast("Mapping[str, object]", point.payload or {})["node_id"])
            for point in answered.points
        )
        returned_counts.append(len(found_ids))
        recalls.append(bench_filtered.recall_at_k(truth[selectivity][node_id], found_ids, k=_TOP_K))
    return returned_counts, recalls, seconds


def _run_arm(
    conn: psycopg.Connection,
    dsn: str,
    client: QdrantClient,
    *,
    indexing: PayloadIndexing,
    stamp: str,
    width: int,
    rows: int,
    sample: Sequence[str],
    fetched: Mapping[str, npt.NDArray[np.float32]],
    truth: Mapping[bench_filtered.Selectivity | None, Mapping[str, tuple[str, ...]]],
    keep: bool,
) -> tuple[IngestTime, list[QdrantArmResult]]:
    collection = f"weft_bench_{_COLLECTION_SLUG[indexing]}_{stamp}"
    client.create_collection(
        collection,
        vectors_config=models.VectorParams(size=width, distance=models.Distance.COSINE),
    )
    if indexing is PayloadIndexing.BEFORE_INGEST:
        for field in payload_index_fields():
            client.create_payload_index(
                collection, field_name=field, field_schema=models.PayloadSchemaType.BOOL
            )

    seconds = _ingest(dsn, client, collection)

    points_before = client.count(collection, exact=True).count
    bench_latency.assert_rows(label="ingested", expected=rows, found=points_before)

    per_filter: list[
        tuple[bench_filtered.Selectivity | None, list[int], list[float], list[float]]
    ] = []
    for selectivity in (None, *bench_filtered.Selectivity):
        returned_counts, recalls, query_seconds = _query_arm(
            client,
            collection,
            selectivity=selectivity,
            sample=sample,
            fetched=fetched,
            truth=truth,
        )
        per_filter.append((selectivity, returned_counts, recalls, query_seconds))

    points_after = client.count(collection, exact=True).count
    bench_latency.assert_rows(label="after arm", expected=points_before, found=points_after)

    results: list[QdrantArmResult] = []
    for selectivity, returned_counts, recalls, query_seconds in per_filter:
        milliseconds = [value * 1000 for value in query_seconds]
        result = QdrantArmResult(
            indexing=indexing,
            selectivity=selectivity,
            queries=len(sample),
            returned_min=min(returned_counts),
            recall_at_10=statistics.fmean(recalls),
            p50_ms=bench_latency.percentile(milliseconds, 0.50),
            p95_ms=bench_latency.percentile(milliseconds, 0.95),
            points_before=points_before,
            points_after=points_after,
        )
        results.append(result)
        print(
            f"indexing: {indexing.value}  "
            f"filter: {selectivity.value if selectivity is not None else 'unfiltered'}  "
            f"returned: min {result.returned_min}  recall@10: {result.recall_at_10:.3f}  "
            f"p50: {result.p50_ms:.1f} ms  p95: {result.p95_ms:.1f} ms  "
            f"before: {points_before:,} points  after: {points_after:,} points"
        )

    if not keep:
        client.delete_collection(collection)

    return IngestTime(indexing=indexing, seconds=seconds), results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--set", dest="vector_set", type=Path, required=True, help="a 29.6 vector set directory"
    )
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--admin-dsn", default=None)
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--record", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    arguments = parser.parse_args(argv)

    admin_dsn = arguments.admin_dsn or os.environ.get("WEFT_DATABASE_URL")
    if not admin_dsn:
        print("no admin DSN: pass --admin-dsn or set WEFT_DATABASE_URL", file=sys.stderr)
        return 2
    qdrant_url = (
        arguments.qdrant_url or os.environ.get("WEFT_QDRANT_URL") or "http://localhost:6333"
    )

    machine = bench_latency.host_machine()
    print(f"machine: {machine.label}")

    name = _database_name(arguments.width)
    created = False
    client: QdrantClient | None = None

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

            _type_column(conn, width=arguments.width)

            with conn.cursor() as cur:
                cur.execute("SELECT id FROM weft_nodes ORDER BY id")
                ids = [str(row[0]) for row in cur.fetchall()]
            _write_buckets(conn, ids)

            sample = bench_latency.query_sample(ids, arguments.queries)
            fetched = _fetch_vectors(conn, sample)
            truth = _ground_truth(conn, sample, fetched)

            client = QdrantClient(url=qdrant_url)
            qdrant_version = client.info().version
            print(f"qdrant: {qdrant_version}")

            stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            ingest_seconds: list[IngestTime] = []
            results: list[QdrantArmResult] = []
            for indexing in PayloadIndexing:
                ingested, arm_results = _run_arm(
                    conn,
                    database_dsn,
                    client,
                    indexing=indexing,
                    stamp=stamp,
                    width=arguments.width,
                    rows=rows,
                    sample=sample,
                    fetched=fetched,
                    truth=truth,
                    keep=arguments.keep,
                )
                ingest_seconds.append(ingested)
                results.extend(arm_results)

        if arguments.record is not None:
            run = QdrantRun(
                machine=machine,
                database=name,
                vector_set=arguments.vector_set.name,
                rows=rows,
                width=arguments.width,
                qdrant_version=qdrant_version,
                pgvector_version=pgvector_version,
                server_version=server_version,
                ingest_seconds=tuple(ingest_seconds),
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
        UnexpectedResponse,
        ResponseHandlingException,
    ) as exc:
        print(str(exc), file=sys.stderr)
        if created and not arguments.keep:
            _drop_database(admin_dsn, name)
        return 2
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
