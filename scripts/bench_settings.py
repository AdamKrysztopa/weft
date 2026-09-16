"""Settings-surface harness for Phase 31 task **31.6**.

Filtered recall@10 against an exact-scan control taken in the same run — a number per backend,
index kind and precision, at decreasing selectivity — reached *end to end through the shipped
binary*: a written `weft.toml` (`[packs.store]`/`[packs.qdrant]`) and a `vector-top-k` document's
own `Filter`, with no hand-written SQL and no direct client call. Phase 29 measured 65 arms and
every one of them issued its own SQL or its own client call, so nothing in this tree has ever
proven that a key written in `weft.toml` — `iterative_scan`, `index`, `precision` — actually
parses, validates, binds through `functools.partial`, and reaches the database. The tell this
harness exists to catch: `iterative_scan = "off"` and `= "relaxed_order"` returning *identical*
recall, which means the GUC never reached the server.

The ladder is `lineage.sources`, not Phase 29's `ext` bucket: the shipped ingest path attaches no
`ext` at all (`weft_chunk/__init__.py:10`), so of the five core filterable fields
(`weft_store/fields.py` `NodeField`) only `lineage.sources` is graded and writable in advance.
Selectivity comes from indexing the corpus in nested slices and reading each rung's true size from
`weft index`'s own `nodes now stored: N.` line — never a `count(*)`.

**Two pipeline documents, and they are never the same one.** `weft index --pipeline` names an
*ingest* document (extract/chunk/embed/store) and this harness always passes the shipped
`index-text`, the same one `bench_latency.py`'s `_run_index` uses. `weft ask --retrieve-only
--pipeline` names a *retrieval* document (retrieve/fuse/pack), and that is the generated one
`filter_document` writes, carrying the rung's `Filter`. The two cannot be interchanged — an ingest
document ends in a `NodeStore` and a retrieval one must end in `Passages` — and saying so here
because the distinction is invisible at the call sites, which differ only by the subcommand.

This module's pure functions (the arm matrix, the `weft.toml` each arm writes, the filter document,
and `bench_record.arms_from_settings`) are pinned by `tests/unit/scripts/test_bench_settings.py`.
`main` is not unit-tested — it drives a real database, a real Qdrant deployment and the shipped
binary as subprocesses, and is exercised by actually running it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

import bench_filtered
import bench_latency
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, ConfigDict

from weft_cli.ask import AskResult
from weft_retrieve.repack import RepackMethod
from weft_store.contract import FilterOp, VectorIndexKind, VectorPrecision

#: The width `[services] embed` can actually query — `ServiceSelection.embed` is a bare `str` and
#: the query path builds it `factory(None)`, so the query embedder is configless and answers at
#: `hash`'s own default (`weft_embed/hash_embedder.py:45`, `_DEFAULT_DIMENSION = 64`). `hash`
#: declares no `config_model`, so it cannot be asked for any other width (`R31.2`, not this task's
#: to fix).
WIDTH: Final[int] = 64

TOP_K: Final[int] = 10

#: Widest to narrowest — `None` is unfiltered.
_LADDER: Final[tuple[bench_filtered.Selectivity | None, ...]] = (
    None,
    bench_filtered.Selectivity.ONE_PERCENT,
    bench_filtered.Selectivity.TENTH_OF_A_PERCENT,
)


class Backend(StrEnum):
    PGVECTOR = "pgvector"
    QDRANT = "qdrant"


class Arm(BaseModel):
    """One configuration this harness measures — task **31.6**, the ninth owner decision's own
    matrix. `iterative_scan` is `None` on every Qdrant arm and on every `exact` pgvector arm: it
    is a pgvector session GUC and means nothing to either.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: Backend
    index: VectorIndexKind
    precision: VectorPrecision
    iterative_scan: bench_filtered.IterativeScan | None
    selectivity: bench_filtered.Selectivity | None

    @property
    def is_control(self) -> bool:
        return self.index is VectorIndexKind.EXACT


def arms() -> tuple[Arm, ...]:
    """The seventeen arms the ninth decision settled — see this task's ledger entry for the
    table. Every backend carries its own exact-scan control at every selectivity its approximate
    arms use; both `iterative_scan` modes are measured at every rung of the ladder, which is the
    pair whose recall has to differ or the GUC never reached the server.
    """
    pgvector_exact = tuple(
        Arm(
            backend=Backend.PGVECTOR,
            index=VectorIndexKind.EXACT,
            precision=VectorPrecision.FLOAT32,
            iterative_scan=None,
            selectivity=selectivity,
        )
        for selectivity in _LADDER
    )
    pgvector_hnsw_float32 = tuple(
        Arm(
            backend=Backend.PGVECTOR,
            index=VectorIndexKind.HNSW,
            precision=VectorPrecision.FLOAT32,
            iterative_scan=mode,
            selectivity=selectivity,
        )
        for mode in (bench_filtered.IterativeScan.OFF, bench_filtered.IterativeScan.RELAXED_ORDER)
        for selectivity in _LADDER
    )
    pgvector_compressed = (
        Arm(
            backend=Backend.PGVECTOR,
            index=VectorIndexKind.HNSW,
            precision=VectorPrecision.FLOAT16,
            iterative_scan=bench_filtered.IterativeScan.RELAXED_ORDER,
            selectivity=bench_filtered.Selectivity.ONE_PERCENT,
        ),
        Arm(
            backend=Backend.PGVECTOR,
            index=VectorIndexKind.HNSW,
            precision=VectorPrecision.BINARY,
            iterative_scan=bench_filtered.IterativeScan.RELAXED_ORDER,
            selectivity=bench_filtered.Selectivity.ONE_PERCENT,
        ),
    )
    qdrant_exact = tuple(
        Arm(
            backend=Backend.QDRANT,
            index=VectorIndexKind.EXACT,
            precision=VectorPrecision.FLOAT32,
            iterative_scan=None,
            selectivity=selectivity,
        )
        for selectivity in _LADDER
    )
    qdrant_hnsw = tuple(
        Arm(
            backend=Backend.QDRANT,
            index=VectorIndexKind.HNSW,
            precision=VectorPrecision.FLOAT32,
            iterative_scan=None,
            selectivity=selectivity,
        )
        for selectivity in _LADDER
    )
    return (
        *pgvector_exact,
        *pgvector_hnsw_float32,
        *pgvector_compressed,
        *qdrant_exact,
        *qdrant_hnsw,
    )


# ---------------------------------------------------------------------------------------------
# The settings surface — what the harness actually writes
# ---------------------------------------------------------------------------------------------


def weft_toml_for(arm: Arm) -> str:
    """The `weft.toml` text one arm's run writes.

    Never a `dsn` literal — `merged_pack_settings` is file-wins key by key with the environment
    filling what the file omits, so omitting `dsn` here is what lets `WEFT_DATABASE_URL` supply
    it, exactly as every other harness in this tree reaches the store.
    """
    lines = ["[services]", 'embed = "hash"', f'store = "{arm.backend.value}"', ""]
    if arm.backend is Backend.PGVECTOR:
        lines.append("[packs.store]")
        lines.append(f'index = "{arm.index.value}"')
        lines.append(f'precision = "{arm.precision.value}"')
        if arm.iterative_scan is not None:
            lines.append(f'iterative_scan = "{arm.iterative_scan.value}"')
    else:
        lines.append("[packs.qdrant]")
        lines.append(f'index = "{arm.index.value}"')
        lines.append(f'precision = "{arm.precision.value}"')
        lines.append(f"vector_size = {WIDTH}")
    return "\n".join(lines) + "\n"


def filter_document(
    selectivity: bench_filtered.Selectivity | None, *, sources: Sequence[str]
) -> str:
    """The pipeline document's YAML text — the ladder itself, as an `in` over `lineage.sources`.

    Three stages, because `--retrieve-only --pipeline` requires the document to end in `Passages`
    and only a `ContextPacker` produces one. `selectivity is None` writes no `filter:` key at all
    — an empty filter matches everything by accident rather than by statement, and the two are
    indistinguishable in a result. `top_n` is never below `TOP_K`: a smaller value would truncate
    the ranking before it is scored, and recall@10 would measure the packer.
    """
    if selectivity is not None and not sources:
        raise ValueError(
            "filter_document needs at least one source to filter lineage.sources by — an 'in' "
            "over an empty list matches nothing, and a recall of 0 reads as a broken index "
            "rather than as a harness that was handed no sources"
        )

    lines = [
        "stages:",
        "  - id: retrieve",
        "    use: vector-top-k",
        "    with:",
        f"      top_k: {TOP_K}",
    ]
    if selectivity is not None:
        lines.append("      filter:")
        lines.append(f"        op: {FilterOp.IN.value}")
        lines.append("        field: lineage.sources")
        lines.append("        value:")
        lines.extend(f'          - "{source}"' for source in sources)
    lines.append("  - {id: fuse, use: single-list}")
    lines.append(
        f"  - {{id: pack, use: repack, with: {{method: {RepackMethod.FORWARD.value}, "
        f"top_n: {TOP_K}}}}}"
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------
# The record — the seventh `arms_from_*` adapter's own run model
# ---------------------------------------------------------------------------------------------


class SettingsArmResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: Arm
    queries: int
    matching_rows: int
    returned_min: int
    recall_at_10: float
    p50_ms: float
    p95_ms: float
    rows_before: int
    rows_after: int


class SettingsRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: bench_latency.Machine
    database: str
    corpus: str
    documents: int
    rows: int
    width: int
    pgvector_version: str
    server_version: str
    qdrant_version: str
    results: tuple[SettingsArmResult, ...]
    taken_at: datetime


# ---------------------------------------------------------------------------------------------
# The driving half: not unit-tested, run against a real database and a real Qdrant deployment by
# the dispatcher — mirrors `bench_latency.py`'s own subprocess shape (`_ask_command`, `_run_ask`).
# ---------------------------------------------------------------------------------------------

_PIPELINE_NAME: Final[str] = "bench-settings-retrieve"


def _weft_binary() -> Path:
    binary = Path(sys.executable).parent / "weft"
    if not binary.exists():
        raise bench_latency.MeasurementRefusedError(
            f"no `weft` binary beside this interpreter at {binary}; install this project first"
        )
    return binary


def _database_name() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"weft_bench_settings_{WIDTH}_{stamp}"


def _create_database(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if cur.fetchone() is not None:
            raise bench_latency.MeasurementRefusedError(
                f"database {name!r} already exists; refusing to reuse it"
            )
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def _drop_database(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def _pgvector_versions(admin_dsn: str, database: str) -> tuple[str, str]:
    database_dsn = make_conninfo(admin_dsn, dbname=database)
    with psycopg.connect(database_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        extension = cur.fetchone()
        cur.execute("SHOW server_version")
        server = cur.fetchone()
    if extension is None or server is None:
        raise bench_latency.MeasurementRefusedError(
            "the database reported no pgvector extension or server version"
        )
    return str(extension[0]), str(server[0])


def _qdrant_version(url: str) -> str:
    """The deployment's own version, over the plain REST root — not `QdrantClient`, which this
    task's own no-direct-client-call rule refuses for anything the measurement depends on.
    """
    with urllib.request.urlopen(f"{url.rstrip('/')}/", timeout=10) as response:  # noqa: S310
        payload = json.loads(response.read())
    version = payload.get("version")
    if not version:
        raise bench_latency.MeasurementRefusedError(f"qdrant at {url} reported no version")
    return str(version)


def _sorted_sources(corpus: Path) -> tuple[Path, ...]:
    """Every file under `corpus`, ordered by `sha256` of its resolved path — deterministic and
    nested by construction, the same footing `bench_filtered.bucket_rank` uses.
    """
    files = [path for path in corpus.rglob("*") if path.is_file()]
    return tuple(
        sorted(files, key=lambda path: hashlib.sha256(str(path.resolve()).encode()).hexdigest())
    )


def _rung_counts(total: int) -> dict[bench_filtered.Selectivity, int]:
    tenth = max(1, round(bench_filtered.Selectivity.TENTH_OF_A_PERCENT.fraction * total))
    tenth = min(tenth, total)
    one = max(tenth, round(bench_filtered.Selectivity.ONE_PERCENT.fraction * total))
    one = min(one, total)
    return {
        bench_filtered.Selectivity.TENTH_OF_A_PERCENT: tenth,
        bench_filtered.Selectivity.ONE_PERCENT: one,
    }


def _run_index(binary: Path, corpus: Path, env: Mapping[str, str], workdir: Path) -> int:
    result = subprocess.run(  # noqa: S603
        [str(binary), "index", str(corpus.resolve()), "--pipeline", "index-text"],
        cwd=workdir,
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise bench_latency.MeasurementRefusedError(
            f"`weft index` exited {result.returncode}: {result.stderr}"
        )
    return bench_latency.parse_nodes_stored(result.stdout)


def _index_rungs(
    binary: Path, sources: Sequence[Path], env: Mapping[str, str], workdir: Path
) -> tuple[
    dict[bench_filtered.Selectivity | None, int],
    dict[bench_filtered.Selectivity | None, tuple[str, ...]],
]:
    """Index the corpus into one growing slice directory, narrowest rung first, and read each
    rung's true size straight off `weft index`'s own `nodes now stored: N.` line — never a
    `count(*)`. Nested by construction: the 0.1% rung's files are a subset of the 1% rung's,
    which are a subset of the full corpus.
    """
    counts = _rung_counts(len(sources))
    slice_dir = workdir / "slice"
    slice_dir.mkdir(parents=True, exist_ok=True)

    sizes: dict[bench_filtered.Selectivity | None, int] = {}
    filter_sources: dict[bench_filtered.Selectivity | None, tuple[str, ...]] = {}
    copied: list[Path] = []
    boundary = 0
    rungs: tuple[tuple[bench_filtered.Selectivity | None, int], ...] = (
        (
            bench_filtered.Selectivity.TENTH_OF_A_PERCENT,
            counts[bench_filtered.Selectivity.TENTH_OF_A_PERCENT],
        ),
        (bench_filtered.Selectivity.ONE_PERCENT, counts[bench_filtered.Selectivity.ONE_PERCENT]),
        (None, len(sources)),
    )
    for selectivity, count in rungs:
        for index, path in enumerate(sources[boundary:count], start=boundary):
            dest = slice_dir / f"{index:06d}_{path.name}"
            shutil.copy2(path, dest)
            copied.append(dest)
        boundary = count
        sizes[selectivity] = _run_index(binary, slice_dir, env, workdir)
        filter_sources[selectivity] = tuple(str(path.resolve()) for path in copied)
    return sizes, filter_sources


def _write_pipeline_document(workdir: Path, name: str, body: str) -> None:
    pipelines_dir = workdir / "pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    (pipelines_dir / f"{name}.yaml").write_text(f"name: {name}\n{body}", encoding="utf-8")


def _write_config(workdir: Path, arm: Arm, *, qdrant_collection: str | None) -> None:
    text = weft_toml_for(arm)
    if arm.backend is Backend.QDRANT and qdrant_collection is not None:
        text += f'collection = "{qdrant_collection}"\n'
    (workdir / "weft.toml").write_text(text, encoding="utf-8")


def _question_for(path: Path) -> str:
    return f"what does {path.stem.replace('_', ' ').replace('-', ' ')} say"


def _ask_command(binary: Path, question: str) -> list[str]:
    return [
        str(binary),
        "ask",
        question,
        "--pipeline",
        _PIPELINE_NAME,
        "--retrieve-only",
        "--top-k",
        str(TOP_K),
        "--format",
        "json",
    ]


def _run_ask(
    binary: Path, question: str, env: Mapping[str, str], workdir: Path
) -> tuple[float, tuple[str, ...]]:
    started = time.monotonic()
    result = subprocess.run(  # noqa: S603
        _ask_command(binary, question),
        cwd=workdir,
        env=dict(env),
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        raise bench_latency.MeasurementRefusedError(
            f"`weft ask --retrieve-only --pipeline {_PIPELINE_NAME}` exited "
            f"{result.returncode}: {result.stderr}"
        )
    answer = AskResult.model_validate_json(result.stdout)
    return elapsed, tuple(hit.node_id for hit in answer.hits)


def _run_arm(
    binary: Path,
    arm: Arm,
    *,
    env: Mapping[str, str],
    workdir: Path,
    questions: Sequence[str],
    matching_rows: int,
    truth: dict[str, tuple[str, ...]] | None,
) -> tuple[SettingsArmResult, dict[str, tuple[str, ...]]]:
    """Run one arm's query sample against the store the caller has already indexed and configured
    (`weft.toml`, the filter document) — `truth` is `None` only for the control arm that is about
    to produce it.
    """
    rows_before = _run_index(binary, workdir / "slice", env, workdir)

    found: dict[str, tuple[str, ...]] = {}
    seconds: list[float] = []
    for question in questions:
        elapsed, node_ids = _run_ask(binary, question, env, workdir)
        seconds.append(elapsed)
        found[question] = node_ids

    rows_after = _run_index(binary, workdir / "slice", env, workdir)

    reference = truth if truth is not None else found
    recalls = [
        bench_filtered.recall_at_k(reference[question], found[question], k=TOP_K)
        for question in questions
    ]
    milliseconds = [value * 1000 for value in seconds]
    result = SettingsArmResult(
        arm=arm,
        queries=len(questions),
        matching_rows=matching_rows,
        returned_min=min(len(node_ids) for node_ids in found.values()),
        recall_at_10=sum(recalls) / len(recalls),
        p50_ms=bench_latency.percentile(milliseconds, 0.50),
        p95_ms=bench_latency.percentile(milliseconds, 0.95),
        rows_before=rows_before,
        rows_after=rows_after,
    )
    print(
        f"{arm.backend.value} {arm.index.value} {arm.precision.value} "
        f"iterative_scan={arm.iterative_scan.value if arm.iterative_scan is not None else '-'} "
        f"selectivity={arm.selectivity.value if arm.selectivity is not None else 'unfiltered'}  "
        f"recall@10: {result.recall_at_10:.3f}  p50: {result.p50_ms:.1f} ms  "
        f"p95: {result.p95_ms:.1f} ms  rows: {rows_before:,}"
    )
    return result, found


def _run_group(
    binary: Path,
    group_arms: Sequence[Arm],
    *,
    sources: Sequence[Path],
    questions: Sequence[str],
    env: Mapping[str, str],
    workdir: Path,
    truth_by_selectivity: dict[bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]],
    qdrant_collection: str | None,
) -> tuple[list[SettingsArmResult], int]:
    """One `(index, precision)` group: one throwaway store, indexed once in nested rungs, then
    every arm in the group (differing only by `iterative_scan`) queried at every rung it names.

    `qdrant_collection` is threaded through rather than defaulted because this function rewrites
    `weft.toml` after `_index_rungs` has already indexed against the caller's copy: a collection
    named for ingest and absent for the queries would search a different, empty collection. And
    **Qdrant fixes index kind and precision when the collection is created**, so two groups sharing
    one collection name would measure the first group's settings twice — identical numbers, which
    is precisely what this harness reads as "the setting never reached the server".
    """
    rung_sizes, rung_sources = _index_rungs(binary, sources, env, workdir)
    is_control = group_arms[0].is_control

    results: list[SettingsArmResult] = []
    for iterative_scan in dict.fromkeys(arm.iterative_scan for arm in group_arms):
        matching = [arm for arm in group_arms if arm.iterative_scan == iterative_scan]
        template = matching[0]
        _write_config(workdir, template, qdrant_collection=qdrant_collection)
        for arm in matching:
            _write_pipeline_document(
                workdir,
                _PIPELINE_NAME,
                filter_document(arm.selectivity, sources=rung_sources[arm.selectivity]),
            )
            truth = None if is_control else truth_by_selectivity.get(arm.selectivity)
            result, found = _run_arm(
                binary,
                arm,
                env=env,
                workdir=workdir,
                questions=questions,
                matching_rows=rung_sizes[arm.selectivity],
                truth=truth,
            )
            results.append(result)
            if is_control:
                truth_by_selectivity[arm.selectivity] = found
    return results, rung_sizes[None]


def _group_key(arm: Arm) -> tuple[VectorIndexKind, VectorPrecision]:
    return (arm.index, arm.precision)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True, help="a directory of documents")
    parser.add_argument("--queries", type=int, default=50)
    parser.add_argument("--admin-dsn", default=None)
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--record", type=Path, default=None)
    arguments = parser.parse_args(argv)

    admin_dsn = arguments.admin_dsn or os.environ.get("WEFT_DATABASE_URL")
    if not admin_dsn:
        print("no admin DSN: pass --admin-dsn or set WEFT_DATABASE_URL", file=sys.stderr)
        return 2

    try:
        binary = _weft_binary()
    except bench_latency.MeasurementRefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    machine = bench_latency.host_machine()
    print(f"machine: {machine.label}")

    sources = _sorted_sources(arguments.corpus)
    if not sources:
        print(f"no files found under {arguments.corpus}", file=sys.stderr)
        return 2
    questions = tuple(
        _question_for(Path(path))
        for path in bench_latency.query_sample(
            [str(path) for path in sources], min(arguments.queries, len(sources))
        )
    )

    all_arms = arms()
    all_results: list[SettingsArmResult] = []
    database_label = _database_name()
    pgvector_version = server_version = ""
    qdrant_version = ""
    total_rows = 0
    created_databases: list[str] = []

    try:
        for backend in Backend:
            backend_arms = [arm for arm in all_arms if arm.backend is backend]
            groups: dict[tuple[VectorIndexKind, VectorPrecision], list[Arm]] = {}
            for arm in backend_arms:
                groups.setdefault(_group_key(arm), []).append(arm)
            ordered_groups = sorted(groups.items(), key=lambda item: not item[1][0].is_control)

            truth_by_selectivity: dict[
                bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]
            ] = {}
            for (index_kind, precision), group_arms in ordered_groups:
                with tempfile.TemporaryDirectory() as raw_workdir:
                    workdir = Path(raw_workdir)
                    if backend is Backend.PGVECTOR:
                        name = f"{database_label}_{index_kind.value}_{precision.value}"
                        _create_database(admin_dsn, name)
                        created_databases.append(name)
                        database_dsn = make_conninfo(admin_dsn, dbname=name)
                        env = {**os.environ, "WEFT_DATABASE_URL": database_dsn}
                        pgvector_version, server_version = _pgvector_versions(admin_dsn, name)
                    else:
                        env = dict(os.environ)
                        qdrant_version = _qdrant_version(arguments.qdrant_url)

                    collection = (
                        f"{database_label}_{index_kind.value}_{precision.value}"
                        if backend is Backend.QDRANT
                        else None
                    )
                    _write_config(workdir, group_arms[0], qdrant_collection=collection)
                    results, group_rows = _run_group(
                        binary,
                        group_arms,
                        sources=sources,
                        questions=questions,
                        env=env,
                        workdir=workdir,
                        truth_by_selectivity=truth_by_selectivity,
                        qdrant_collection=collection,
                    )
                    all_results.extend(results)
                    total_rows = max(total_rows, group_rows)

        if arguments.record is not None:
            run = SettingsRun(
                machine=machine,
                database=database_label,
                corpus=arguments.corpus.name,
                documents=len(sources),
                rows=total_rows,
                width=WIDTH,
                pgvector_version=pgvector_version,
                server_version=server_version,
                qdrant_version=qdrant_version,
                results=tuple(all_results),
                taken_at=datetime.now(UTC),
            )
            arguments.record.write_text(run.model_dump_json(indent=2), encoding="utf-8")
        return 0
    except (
        bench_latency.CountNotReportedError,
        bench_latency.RowCountMismatchError,
        bench_latency.MeasurementRefusedError,
        ValueError,
        psycopg.Error,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        for name in created_databases:
            _drop_database(admin_dsn, name)


if __name__ == "__main__":
    raise SystemExit(main())
