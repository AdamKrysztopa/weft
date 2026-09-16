"""Latency harness for Phase 29 task **29.1**.

The default store's p50/p95 query latency at 10,000 and 100,000 chunks, at widths 64 and 1536, on
a throwaway database named so it cannot be confused with the one a test suite is using
(`CLAUDE.md`'s `L8.30`: a measurement asserts its own row count immediately before *and* after,
and nothing else touches the database while it runs). Three arms — the store's own
`search_vector` statement (`weft_store.pgvector_store.PgVectorStore.search_vector`), `weft ask
--retrieve-only` as a subprocess, and eight such processes at once — followed by a throwaway
`ALTER COLUMN` timing at the width this run asked for.

**Width 1536 cannot drive the two CLI arms.** `weft ask` embeds the query through `[services]
embed`, which is `hash` at its default width 64; `hash` refuses any `with:` block, so there is no
way to ask it for 1536 dimensions. Only the store-statement arm runs at that width, over synthetic
unit vectors written directly into the throwaway column — see `synthetic_vector`.

This module's pure functions (the percentile rule, the two counters, the synthetic vectors, the
query sample, the machine label and the result line) are pinned by
`tests/unit/scripts/test_bench_latency.py`. `main` is not unit-tested — it drives a real
database and the shipped binary, and is exercised by actually running it.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import psycopg
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, ConfigDict, ValidationError

from weft_cli.ask import AskResult

_TOP_K = 10
_NODES_STORED_RE = re.compile(r"nodes now stored: (\d+)\.")


class CountNotReportedError(ValueError):
    """`weft index`'s stdout carried no `nodes now stored: N.` count to read."""


class RowCountMismatchError(ValueError):
    """A table a measurement depends on held a different row count than expected."""


class MeasurementRefusedError(RuntimeError):
    """A precondition for a trustworthy measurement did not hold."""


def percentile(samples: Sequence[float], q: float) -> float:
    """Nearest rank: `sorted_samples[ceil(q * n) - 1]`."""
    if not samples:
        raise ValueError("no samples to take a percentile of")
    if not (0 < q <= 1):
        raise ValueError(f"q must be in (0, 1], got {q}")
    ordered = sorted(samples)
    index = math.ceil(q * len(ordered)) - 1
    return ordered[index]


def parse_nodes_stored(stdout: str) -> int:
    """The count `weft_cli/render.py:601 "nodes now stored: {stored}."` prints."""
    match = _NODES_STORED_RE.search(stdout)
    if match is not None:
        return int(match.group(1))
    lines = [line for line in stdout.splitlines() if line.strip()]
    last = lines[-1] if lines else ""
    raise CountNotReportedError(
        f"stdout carries no 'nodes now stored: N.' count; last line: {last!r}"
    )


def assert_rows(*, label: str, expected: int, found: int) -> None:
    """Refuse a measurement whose table moved under it (`CLAUDE.md`'s `L8.30`)."""
    if expected != found:
        raise RowCountMismatchError(
            f"{label}: expected {expected:,} rows, found {found:,} — the measurement is abandoned"
        )


def synthetic_vector(seed: str, width: int) -> tuple[float, ...]:
    """A deterministic, unit-length vector of `width` components, from `sha256(f"{seed}:{i}")`.

    No `random` (ruff `S311`): a benchmark vector has to be reproducible across runs on the same
    seed, which a seeded PRNG can be made to do but a hash already does for free.
    """
    if width < 1:
        raise ValueError(f"width must be at least 1 (got {width})")
    components: list[float] = []
    for i in range(width):
        digest = hashlib.sha256(f"{seed}:{i}".encode()).digest()
        raw = int.from_bytes(digest[:8], "big")
        components.append((raw / 2**64) * 2 - 1)
    norm = math.sqrt(sum(v * v for v in components))
    return tuple(v / norm for v in components)


def query_sample(ids: Sequence[str], n: int) -> tuple[str, ...]:
    """The first `n` of `ids`, ordered by `sha256(id)` — deterministic, independent of order."""
    if n > len(ids):
        raise ValueError(f"{n} queries asked for, but the table holds {len(ids)} rows")
    ordered = sorted(ids, key=lambda node_id: hashlib.sha256(node_id.encode()).hexdigest())
    return tuple(ordered[:n])


class Machine(BaseModel):
    """The machine a measurement ran on — so a number is never read without its hardware."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chip: str
    memory_gib: int
    cpus: int
    os_version: str

    @property
    def label(self) -> str:
        return f"{self.chip}, {self.memory_gib} GiB, {self.cpus} CPUs, macOS {self.os_version}"


def describe_machine(*, chip: str, memory_bytes: int, cpus: int, os_version: str) -> Machine:
    return Machine(chip=chip, memory_gib=memory_bytes // 2**30, cpus=cpus, os_version=os_version)


class Arm(StrEnum):
    STORE_STATEMENT = "store statement"
    CLI_RETRIEVE_ONLY = "weft ask --retrieve-only"
    CLI_CONCURRENT = "8 parallel weft ask processes"


class LatencyResult(BaseModel):
    """One arm's outcome at one chunk count and width."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: Arm
    chunks: int
    width: int
    queries: int
    p50_ms: float
    p95_ms: float
    rows_before: int
    rows_after: int


def summarise(
    *,
    arm: Arm,
    chunks: int,
    width: int,
    samples_seconds: Sequence[float],
    rows_before: int,
    rows_after: int,
) -> LatencyResult:
    """Refuses first (`assert_rows`), and only then converts seconds to milliseconds."""
    assert_rows(label="after", expected=rows_before, found=rows_after)
    milliseconds = [seconds * 1000 for seconds in samples_seconds]
    return LatencyResult(
        arm=arm,
        chunks=chunks,
        width=width,
        queries=len(samples_seconds),
        p50_ms=percentile(milliseconds, 0.50),
        p95_ms=percentile(milliseconds, 0.95),
        rows_before=rows_before,
        rows_after=rows_after,
    )


def format_result(result: LatencyResult) -> str:
    return (
        f"chunks: {result.chunks:,}  width: {result.width}  arm: {result.arm.value}  "
        f"p50: {result.p50_ms:.1f} ms  p95: {result.p95_ms:.1f} ms  queries: {result.queries}  "
        f"top_k: {_TOP_K}  before: {result.rows_before:,} rows  after: {result.rows_after:,} rows"
    )


class LatencyRun(BaseModel):
    """The one JSON record `--record` writes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: Machine
    database: str
    pgvector_version: str
    server_version: str
    chunks: int
    width: int
    synthetic_vectors: bool
    alter_seconds: float
    results: tuple[LatencyResult, ...]
    taken_at: datetime


# ---------------------------------------------------------------------------------------------
# The driving half: not unit-tested, run against a real database by the dispatcher.
# ---------------------------------------------------------------------------------------------

#: The statement `weft_store/pgvector_store.py:1379 "embedding <=> %(vector)s AS distance"`
#: sends for `search_vector` with `filter=None`, which `_predicate_or_true` renders as `TRUE`.
_SEARCH_VECTOR_SQL = sql.SQL(
    "SELECT *, embedding <=> %(vector)s AS distance "
    "FROM weft_nodes "
    "WHERE embedding IS NOT NULL AND TRUE "
    "ORDER BY embedding <=> %(vector)s "
    "LIMIT %(top_k)s"
)


def _weft_binary() -> Path:
    binary = Path(sys.executable).parent / "weft"
    if not binary.exists():
        raise MeasurementRefusedError(
            f"no `weft` binary beside this interpreter at {binary}; install this project first"
        )
    return binary


def _run_text(command: Sequence[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=True)  # noqa: S603
    return result.stdout


def host_machine() -> Machine:
    chip = _run_text(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
    memory_bytes = int(_run_text(["sysctl", "-n", "hw.memsize"]).strip())
    cpus = int(_run_text(["sysctl", "-n", "hw.ncpu"]).strip())
    os_version = _run_text(["sw_vers", "-productVersion"]).strip()
    return describe_machine(chip=chip, memory_bytes=memory_bytes, cpus=cpus, os_version=os_version)


def _database_name(*, chunks: int, width: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"weft_bench_lat_{chunks}_{width}_{stamp}"


def _create_database(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if cur.fetchone() is not None:
            raise MeasurementRefusedError(f"database {name!r} already exists; refusing to reuse it")
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def _drop_database(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def _row_count(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM weft_nodes")
        row = cur.fetchone()
        return int(row[0]) if row is not None else 0


def _weft_env(database_dsn: str) -> dict[str, str]:
    return {**os.environ, "WEFT_DATABASE_URL": database_dsn}


def _run_index(binary: Path, corpus: Path, database_dsn: str, chunks: int, workdir: Path) -> None:
    result = subprocess.run(  # noqa: S603
        [str(binary), "index", str(corpus.resolve()), "--pipeline", "index-text"],
        cwd=workdir,
        env=_weft_env(database_dsn),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MeasurementRefusedError(f"`weft index` exited {result.returncode}: {result.stderr}")
    stored = parse_nodes_stored(result.stdout)
    if stored != chunks:
        raise MeasurementRefusedError(
            f"`weft index` reported {stored:,} nodes stored, expected {chunks:,}"
        )


def _versions(conn: psycopg.Connection) -> tuple[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        extension = cur.fetchone()
        cur.execute("SHOW server_version")
        server = cur.fetchone()
    if extension is None or server is None:
        raise MeasurementRefusedError("the database reported no pgvector extension or version")
    return str(extension[0]), str(server[0])


def _debare_column_type(conn: psycopg.Connection) -> None:
    """29.3's store now commits `embedding` to `vector(64)` at first write; strip the width back
    to bare so this harness's own timed ALTER still measures a bare->typed rewrite, not a no-op."""
    with conn.cursor() as cur:
        cur.execute(sql.SQL("ALTER TABLE weft_nodes ALTER COLUMN embedding TYPE vector"))
    conn.commit()


def _replace_with_synthetic(conn: psycopg.Connection, *, width: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM weft_nodes ORDER BY id")
        ids = [str(row[0]) for row in cur.fetchall()]
        cur.execute("CREATE TEMP TABLE bench_synthetic (id text PRIMARY KEY, embedding vector)")
        with cur.copy(sql.SQL("COPY bench_synthetic (id, embedding) FROM STDIN")) as copy:
            for node_id in ids:
                vector = synthetic_vector(node_id, width)
                copy.write_row((node_id, PgVector(list(vector))))
        cur.execute(
            "UPDATE weft_nodes n SET embedding = t.embedding "
            "FROM bench_synthetic t WHERE n.id = t.id"
        )
        assert_rows(label="synthetic replace", expected=len(ids), found=cur.rowcount)
        cur.execute("SELECT DISTINCT vector_dims(embedding) FROM weft_nodes")
        dims = [int(row[0]) for row in cur.fetchall()]
        if dims != [width]:
            raise MeasurementRefusedError(
                f"embeddings are not uniformly width {width} after replacement: dims={dims}"
            )
    conn.commit()
    print(f"replaced {len(ids):,} embeddings with synthetic width-{width} vectors (latency only)")


def _fetch_sample(conn: psycopg.Connection, sample: Sequence[str]) -> dict[str, tuple[str, str]]:
    fetched: dict[str, tuple[str, str]] = {}
    with conn.cursor() as cur:
        for node_id in sample:
            cur.execute("SELECT embedding::text, content FROM weft_nodes WHERE id = %s", (node_id,))
            row = cur.fetchone()
            if row is None:
                raise MeasurementRefusedError(f"sampled id {node_id!r} is no longer in the table")
            fetched[node_id] = (str(row[0]), str(row[1]))
    return fetched


def _parse_pg_vector_text(text: str) -> list[float]:
    return [float(value) for value in text.strip("[]").split(",")]


def _arm_store_statement(
    conn: psycopg.Connection,
    *,
    chunks: int,
    width: int,
    sample: Sequence[str],
    fetched: dict[str, tuple[str, str]],
) -> LatencyResult:
    rows_before = _row_count(conn)
    samples_seconds: list[float] = []
    with conn.cursor() as cur:
        for node_id in sample:
            embedding_text, _ = fetched[node_id]
            vector = PgVector(_parse_pg_vector_text(embedding_text))
            started = time.monotonic()
            cur.execute(_SEARCH_VECTOR_SQL, {"vector": vector, "top_k": _TOP_K})
            rows = cur.fetchall()
            samples_seconds.append(time.monotonic() - started)
            if len(rows) != _TOP_K:
                raise MeasurementRefusedError(
                    f"store statement returned {len(rows)} rows for {node_id!r}, expected {_TOP_K}"
                )
    rows_after = _row_count(conn)
    result = summarise(
        arm=Arm.STORE_STATEMENT,
        chunks=chunks,
        width=width,
        samples_seconds=samples_seconds,
        rows_before=rows_before,
        rows_after=rows_after,
    )
    print(format_result(result))
    return result


_SKIP_REASON = (
    "weft ask embeds the query through [services] embed, which is hash at its default width "
    "64 and refuses a with: block"
)


def _question_for(content: str) -> str:
    return " ".join(content.split()[:8])


def _ask_command(binary: Path, question: str) -> list[str]:
    return [
        str(binary),
        "ask",
        "--retrieve-only",
        "--top-k",
        str(_TOP_K),
        "--format",
        "json",
        question,
    ]


def _require_full_page(stdout: str, question: str) -> None:
    """`--format json` prints one `AskResult` line holding every hit, never a line per hit."""
    try:
        answer = AskResult.model_validate_json(stdout)
    except ValidationError as exc:
        raise MeasurementRefusedError(
            f"`weft ask --retrieve-only` printed no AskResult for {question!r}: {exc}"
        ) from exc
    if len(answer.hits) != _TOP_K:
        raise MeasurementRefusedError(
            f"`weft ask --retrieve-only` returned {len(answer.hits)} hits for {question!r}, "
            f"expected {_TOP_K}"
        )


def _run_ask(binary: Path, database_dsn: str, question: str, workdir: Path) -> float:
    started = time.monotonic()
    result = subprocess.run(  # noqa: S603
        _ask_command(binary, question),
        cwd=workdir,
        env=_weft_env(database_dsn),
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        raise MeasurementRefusedError(
            f"`weft ask --retrieve-only` exited {result.returncode}: {result.stderr}"
        )
    _require_full_page(result.stdout, question)
    return elapsed


def _arm_cli_retrieve_only(
    conn: psycopg.Connection,
    binary: Path,
    database_dsn: str,
    workdir: Path,
    *,
    chunks: int,
    width: int,
    sample: Sequence[str],
    fetched: dict[str, tuple[str, str]],
) -> LatencyResult | None:
    if width != 64:
        print(f"arm: {Arm.CLI_RETRIEVE_ONLY.value}  skipped at width {width}: {_SKIP_REASON}")
        return None
    rows_before = _row_count(conn)
    samples_seconds: list[float] = []
    for node_id in sample:
        _, content = fetched[node_id]
        samples_seconds.append(_run_ask(binary, database_dsn, _question_for(content), workdir))
    rows_after = _row_count(conn)
    result = summarise(
        arm=Arm.CLI_RETRIEVE_ONLY,
        chunks=chunks,
        width=width,
        samples_seconds=samples_seconds,
        rows_before=rows_before,
        rows_after=rows_after,
    )
    print(format_result(result))
    return result


def _arm_cli_concurrent(
    conn: psycopg.Connection,
    binary: Path,
    database_dsn: str,
    workdir: Path,
    *,
    chunks: int,
    width: int,
    sample: Sequence[str],
    fetched: dict[str, tuple[str, str]],
) -> LatencyResult | None:
    if width != 64:
        print(f"arm: {Arm.CLI_CONCURRENT.value}  skipped at width {width}: {_SKIP_REASON}")
        return None
    rows_before = _row_count(conn)
    env = _weft_env(database_dsn)
    samples_seconds: list[float] = []
    batch = 8
    for start in range(0, len(sample), batch):
        node_ids = sample[start : start + batch]
        questions = [_question_for(fetched[node_id][1]) for node_id in node_ids]
        processes: list[tuple[float, subprocess.Popen[str], str]] = []
        for question in questions:
            started = time.monotonic()
            proc = subprocess.Popen(  # noqa: S603
                _ask_command(binary, question),
                cwd=workdir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            processes.append((started, proc, question))
        for started, proc, question in processes:
            stdout, stderr = proc.communicate()
            elapsed = time.monotonic() - started
            if proc.returncode != 0:
                raise MeasurementRefusedError(
                    f"`weft ask --retrieve-only` exited {proc.returncode}: {stderr}"
                )
            _require_full_page(stdout, question)
            samples_seconds.append(elapsed)
    rows_after = _row_count(conn)
    result = summarise(
        arm=Arm.CLI_CONCURRENT,
        chunks=chunks,
        width=width,
        samples_seconds=samples_seconds,
        rows_before=rows_before,
        rows_after=rows_after,
    )
    print(format_result(result))
    return result


def _alter_column_type(conn: psycopg.Connection, *, width: int) -> float:
    rows_before = _row_count(conn)
    with conn.cursor() as cur:
        started = time.monotonic()
        cur.execute(
            sql.SQL("ALTER TABLE weft_nodes ALTER COLUMN embedding TYPE vector({})").format(
                sql.Literal(width)
            )
        )
        elapsed = time.monotonic() - started
    conn.commit()
    rows_after = _row_count(conn)
    assert_rows(label="alter", expected=rows_before, found=rows_after)
    print(f"typed embedding as vector({width}): ALTER took {elapsed:.2f} s")
    return elapsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True, help="a 29.0 output directory")
    parser.add_argument("--chunks", type=int, required=True, help="the count 29.0 printed")
    parser.add_argument("--width", type=int, required=True, choices=[64, 1536])
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--admin-dsn", default=None)
    parser.add_argument("--record", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    arguments = parser.parse_args(argv)

    admin_dsn = arguments.admin_dsn or os.environ.get("WEFT_DATABASE_URL")
    if not admin_dsn:
        print("no admin DSN: pass --admin-dsn or set WEFT_DATABASE_URL", file=sys.stderr)
        return 2

    try:
        binary = _weft_binary()
    except MeasurementRefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    machine = host_machine()
    print(f"machine: {machine.label}")

    name = _database_name(chunks=arguments.chunks, width=arguments.width)
    database_dsn = make_conninfo(admin_dsn, dbname=name)
    created = False

    try:
        _create_database(admin_dsn, name)
        created = True
        print(f"database: {name} (nothing else touches it while this runs)")

        with tempfile.TemporaryDirectory() as raw_workdir:
            workdir = Path(raw_workdir)
            _run_index(binary, arguments.corpus, database_dsn, arguments.chunks, workdir)
            # Autocommit: `weft ask` provisions the store's schema with `ALTER TABLE` on every
            # connection, and it waits forever behind a read this session leaves in a transaction.
            with psycopg.connect(database_dsn, autocommit=True) as conn:
                register_vector(conn)
                assert_rows(label="indexed", expected=arguments.chunks, found=_row_count(conn))
                pgvector_version, server_version = _versions(conn)
                print(f"pgvector {pgvector_version}, server {server_version}")

                _debare_column_type(conn)

                synthetic = arguments.width != 64
                if synthetic:
                    _replace_with_synthetic(conn, width=arguments.width)

                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM weft_nodes")
                    ids = [str(row[0]) for row in cur.fetchall()]
                sample = query_sample(ids, arguments.queries)
                fetched = _fetch_sample(conn, sample)

                results: list[LatencyResult] = [
                    _arm_store_statement(
                        conn,
                        chunks=arguments.chunks,
                        width=arguments.width,
                        sample=sample,
                        fetched=fetched,
                    )
                ]
                for cli_arm in (_arm_cli_retrieve_only, _arm_cli_concurrent):
                    measured = cli_arm(
                        conn,
                        binary,
                        database_dsn,
                        workdir,
                        chunks=arguments.chunks,
                        width=arguments.width,
                        sample=sample,
                        fetched=fetched,
                    )
                    if measured is not None:
                        results.append(measured)

                alter_seconds = _alter_column_type(conn, width=arguments.width)

        if arguments.record is not None:
            run = LatencyRun(
                machine=machine,
                database=name,
                pgvector_version=pgvector_version,
                server_version=server_version,
                chunks=arguments.chunks,
                width=arguments.width,
                synthetic_vectors=synthetic,
                alter_seconds=alter_seconds,
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
        CountNotReportedError,
        RowCountMismatchError,
        MeasurementRefusedError,
        psycopg.Error,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        if created and not arguments.keep:
            _drop_database(admin_dsn, name)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
