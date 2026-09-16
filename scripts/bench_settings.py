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
`ext` at all (`weft_chunk/__init__.py:10 "This pack contributes no"`), so of the five core
filterable fields
(`weft_store/fields.py` `NodeField`) only `lineage.sources` is graded and writable in advance.
Selectivity comes from indexing the corpus in nested slices and reading each rung's true size from
`weft index`'s own `nodes now stored: N.` line — never a `count(*)`.

**Two pipeline documents, and they are never the same one.** `weft index --pipeline` names an
*ingest* document (extract/chunk/embed/store) and `weft ask --retrieve-only --pipeline` names a
*retrieval* document (retrieve/fuse/pack). The two cannot be interchanged — an ingest document ends
in a `NodeStore` and a retrieval one must end in `Passages` — and saying so here because the
distinction is invisible at the call sites, which differ only by the subcommand. **This harness
generates both**: `ingest_document` derives from the shipped `index-pdf-text`, and
`filter_document` writes the retrieval one carrying the rung's `Filter`.

*(This paragraph said the ingest half "always passes the shipped `index-text`". That was wrong and
a real run caught it: `index-text`'s extractor claims `.md`/`.txt`, the corpus is 1000 PDFs, and
`weft index` exited 4 — "found .pdf, and the installed extractors claim .md, .txt". The
implementer flagged this exact sentence as worth confirming and the confirmation checked the wrong
half of it.)*

This module's pure functions (the arm matrix, the `weft.toml` each arm writes, the filter document,
`corpus_sources`, and `bench_record.arms_from_settings`) are pinned by
`tests/unit/scripts/test_bench_settings.py`. `corpus_sources` is public rather than `_`-prefixed
because it is tested from outside: pyright's strict `reportPrivateUsage` refuses a leading-
underscore name reached across modules, and reaching around that rule to keep a name private is
the wrong trade for a function that now carries the "which documents *are* the corpus" contract.
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
import threading
import time
import urllib.request
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

import bench_filtered
import bench_latency
import bench_vectors
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, ConfigDict

from weft_cli.ask import AskResult
from weft_retrieve.repack import RepackMethod
from weft_store.contract import FilterOp, VectorIndexKind, VectorPrecision

#: The width `[services] embed` can actually query — `ServiceSelection.embed` is a bare `str` and
#: the query path builds it `factory(None)`, so the query embedder is configless and answers at
#: `hash`'s own default (`weft_embed/hash_embedder.py:45 "_DEFAULT_DIMENSION = 64"`). `hash`
#: declares no `config_model`, so it cannot be asked for any other width (`R31.2`, not this task's
#: to fix).
WIDTH: Final[int] = 64

#: What `[packs.qdrant] timeout_seconds` is set to for every Qdrant arm. Not a tuned number and
#: not a measurement — headroom, kept for a reason that is no longer the original one.
#:
#: It was added because `QdrantStore.add` issued one unbatched request for whatever it was handed,
#: and `weft index` hands it the whole corpus as a single batch. Two runs died there, the second
#: with this setting already at 900. **`R31.10` fixed the cause** — `add` now slices both its read
#: and its write — so this no longer carries the run. It stays because a corpus-sized ingest is
#: still many requests and the client's own default is short, and because it is an ordinary
#: `[packs.qdrant]` key rather than a harness special case.
QDRANT_TIMEOUT_SECONDS: Final[int] = 900

#: How many groups run at once by default. Groups are independent — each owns its own database or
#: its own collection — with exactly one ordering constraint, which `main` enforces by running in
#: waves: a backend's exact-scan **control** must finish before any approximate group of that
#: backend starts, because every approximate arm scores its recall against the control's node ids.
#: Four rather than twelve because `weft index` holds a whole batch in memory and `weft_cli`
#: hands it the entire corpus as one batch, so concurrency is bounded by memory, not by CPUs.
DEFAULT_JOBS: Final[int] = 4

_STARTED: Final[float] = time.monotonic()
_SAY_LOCK: Final[threading.Lock] = threading.Lock()


def _say(label: str, message: str) -> None:
    """One progress line, flushed.

    **Flushed, and that is the whole point.** The 2026-09-16 run printed one line per completed
    arm and nothing else, with no `flush`; Python block-buffers stdout when it is redirected to a
    file, so 105 minutes of work sat in a 4-8 KB buffer and the log read as empty. A run with no
    progress signal is indistinguishable from a hung one — the first act of the session that
    followed was taking a stack sample of the process to decide which it was. `R31.8` carries the
    same defect across the five sibling harnesses.

    The lock keeps two worker threads from interleaving within a line; `print` is otherwise
    atomic enough under the GIL, but "otherwise" is not a guarantee worth relying on in the one
    mechanism that exists to tell you what is happening.
    """
    elapsed = time.monotonic() - _STARTED
    minutes, seconds = divmod(int(elapsed), 60)
    with _SAY_LOCK:
        print(f"[{minutes:3d}:{seconds:02d}] {label:<28} {message}", flush=True)


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
        # Two 2026-09-16 runs died here, both reaching the operator as `'store' failed: ` with
        # no message at all. `R31.9` fixed the message — the seam now names the exception class —
        # and `R31.10` fixed the cause, slicing `QdrantStore.add`'s read and write instead of
        # sending one request per corpus. This key is headroom over the client's short default,
        # not the thing that makes the ingest possible.
        lines.append(f"timeout_seconds = {QDRANT_TIMEOUT_SECONDS}")
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
    """The two versions, read **after** something has already opened `database`.

    A freshly `CREATE DATABASE`d database has no `vector` extension: `PgVectorStore` issues
    `CREATE EXTENSION IF NOT EXISTS` on its first connection, so probing `pg_extension` before the
    first `weft index` finds nothing and this refuses the whole run. `bench_filtered.py` reads the
    same two values and does it after its own `_load`, for the same reason. Called here once the
    group's ingest has run rather than at database creation, which is where it sat until a real
    run exited 2 on it.
    """
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


def corpus_sources(corpus: Path, *, manifest: Path | None = None) -> tuple[Path, ...]:
    """The corpus's documents, ordered by `sha256` of the resolved path — deterministic and nested
    by construction, the same footing `bench_filtered.bucket_rank` uses.

    **`manifest` is what makes "the corpus" mean the *indexable* set rather than the directory.**
    `corpus/open-ragbench-pdfs.toml` carries **997** `[[document]]` entries — already the filtered
    set — beside **3** `[[excluded]]` ones recording *why* those are absent, two of them papers
    `pdf-text` cannot extract at all: *"raises UnicodeEncodeError on an unpaired surrogate
    (R29.2)"*. `R29.2` is open, and the raise aborts the whole `weft index` run rather than failing
    one document, so globbing the 1000 files on disk meets a paper that kills the run — which is
    exactly what happened on the first real attempt.

    `load_manifest` alone is therefore correct and `exclude_documents` is **not** applied here:
    that function is for the moment of exclusion, and re-applying it raises
    `UnknownExclusionError` because the excluded ids are no longer among the documents. The reader
    is `bench_vectors`' own rather than a second parser of the same file (`L5.6`).
    """
    if manifest is None:
        files = [path for path in corpus.rglob("*") if path.is_file()]
    else:
        documents = bench_vectors.load_manifest(manifest)
        files = [corpus / f"{document.id}.pdf" for document in documents]
        missing = [path for path in files if not path.is_file()]
        if missing:
            raise bench_latency.MeasurementRefusedError(
                f"{len(missing)} manifest document(s) are not under {corpus}, "
                f"starting with {missing[0].name}"
            )
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


_INGEST_NAME: Final[str] = "bench-settings-ingest"


def ingest_document(backend: Backend) -> str:
    """The ingest document this harness writes, derived from a shipped one rather than invented.

    **No shipped document pairs PDFs with Qdrant**, which is what forces this: `index-pdf-text`
    is `index-pdf` → `index-text` with only the extractor replaced, so it stores to `pgvector`,
    and `index-qdrant` swaps the store but keeps the `text` extractor, which claims `.md`/`.txt`
    alone. The corpus the ninth decision settled on is 1000 PDFs, so the Qdrant arms need the
    combination the tree does not ship — one `replace:` away from the one it does.
    """
    body = "extends: index-pdf-text\n"
    if backend is Backend.QDRANT:
        body += "replace:\n  - {id: store, use: qdrant}\n"
    return body


def _run_index(
    binary: Path, corpus: Path, env: Mapping[str, str], workdir: Path, *, pipeline: str
) -> int:
    result = subprocess.run(  # noqa: S603
        [str(binary), "index", str(corpus.resolve()), "--pipeline", pipeline],
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
    binary: Path,
    sources: Sequence[Path],
    env: Mapping[str, str],
    workdir: Path,
    *,
    pipeline: str,
    label: str,
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
        rung_name = selectivity.value if selectivity is not None else "full"
        _say(label, f"indexing rung {rung_name}: {count} document(s)")
        sizes[selectivity] = _run_index(binary, slice_dir, env, workdir, pipeline=pipeline)
        _say(label, f"rung {rung_name} stored {sizes[selectivity]:,} node(s)")
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
    ingest_pipeline: str,
    matching_rows: int,
    truth: dict[str, tuple[str, ...]] | None,
    label: str,
) -> tuple[SettingsArmResult, dict[str, tuple[str, ...]]]:
    """Run one arm's query sample against the store the caller has already indexed and configured
    (`weft.toml`, the filter document) — `truth` is `None` only for the control arm that is about
    to produce it.
    """
    rung = arm.selectivity.value if arm.selectivity is not None else "unfiltered"
    scan = arm.iterative_scan.value if arm.iterative_scan is not None else "-"
    _say(label, f"arm scan={scan} selectivity={rung}: re-indexing before {len(questions)} queries")
    rows_before = _run_index(binary, workdir / "slice", env, workdir, pipeline=ingest_pipeline)

    found: dict[str, tuple[str, ...]] = {}
    seconds: list[float] = []
    for position, question in enumerate(questions, start=1):
        elapsed, node_ids = _run_ask(binary, question, env, workdir)
        seconds.append(elapsed)
        found[question] = node_ids
        if position % 10 == 0 or position == len(questions):
            _say(label, f"arm scan={scan} selectivity={rung}: {position}/{len(questions)} queries")

    rows_after = _run_index(binary, workdir / "slice", env, workdir, pipeline=ingest_pipeline)

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
    ingest_pipeline: str,
    label: str,
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
    _say(label, f"group starting: {len(group_arms)} arm(s), {len(sources)} document(s)")
    rung_sizes, rung_sources = _index_rungs(
        binary, sources, env, workdir, pipeline=ingest_pipeline, label=label
    )
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
                ingest_pipeline=ingest_pipeline,
                matching_rows=rung_sizes[arm.selectivity],
                truth=truth,
                label=label,
            )
            results.append(result)
            if is_control:
                truth_by_selectivity[arm.selectivity] = found
    _say(label, f"group done: {len(results)} arm(s)")
    return results, rung_sizes[None]


def _group_key(arm: Arm) -> tuple[VectorIndexKind, VectorPrecision]:
    return (arm.index, arm.precision)


class _GroupPlan(BaseModel):
    """One unit of parallel work: a backend's `(index, precision)` group and every arm in it."""

    model_config = ConfigDict(frozen=True)

    backend: Backend
    index: VectorIndexKind
    precision: VectorPrecision
    group_arms: tuple[Arm, ...]

    @property
    def is_control(self) -> bool:
        return self.group_arms[0].is_control

    @property
    def label(self) -> str:
        return f"{self.backend.value} {self.index.value}/{self.precision.value}"


class _GroupOutcome(BaseModel):
    """What one group hands back, so `main` never reaches into a worker thread's locals."""

    model_config = ConfigDict(frozen=True)

    results: tuple[SettingsArmResult, ...]
    rows: int
    pgvector_version: str = ""
    server_version: str = ""
    qdrant_version: str = ""


def _run_one_group(
    binary: Path,
    plan: _GroupPlan,
    *,
    sources: Sequence[Path],
    questions: Sequence[str],
    admin_dsn: str,
    qdrant_url: str,
    database_label: str,
    truth_by_selectivity: dict[bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]],
    registry_lock: threading.Lock,
    created_databases: list[str],
) -> _GroupOutcome:
    """Provision one group's throwaway store, run it, and report — the body of a worker thread.

    **What makes this safe to run beside its siblings.** Each group owns a database or a collection
    named for its own `(index, precision)`, and its own temporary working directory, so two groups
    share no state. The one thing they do share is `truth_by_selectivity`, and `main` keeps that
    safe by ordering rather than by locking: a backend's control group runs alone in wave one and
    is its only writer, and wave two only ever reads it.

    The database name is registered under a lock **before** the work starts, so a group that dies
    half-built is still dropped by the caller's `finally`.
    """
    store_name = f"{database_label}_{plan.index.value}_{plan.precision.value}"
    pgvector_version = server_version = qdrant_version = ""
    collection: str | None = None
    database_name: str | None = None

    with tempfile.TemporaryDirectory() as raw_workdir:
        workdir = Path(raw_workdir)
        if plan.backend is Backend.PGVECTOR:
            _create_database(admin_dsn, store_name)
            with registry_lock:
                created_databases.append(store_name)
            database_name = store_name
            env = {**os.environ, "WEFT_DATABASE_URL": make_conninfo(admin_dsn, dbname=store_name)}
        else:
            env = dict(os.environ)
            qdrant_version = _qdrant_version(qdrant_url)
            collection = store_name

        _write_config(workdir, plan.group_arms[0], qdrant_collection=collection)
        _write_pipeline_document(workdir, _INGEST_NAME, ingest_document(plan.backend))
        results, group_rows = _run_group(
            binary,
            plan.group_arms,
            sources=sources,
            questions=questions,
            env=env,
            workdir=workdir,
            truth_by_selectivity=truth_by_selectivity,
            qdrant_collection=collection,
            ingest_pipeline=_INGEST_NAME,
            label=plan.label,
        )
        if database_name is not None:
            pgvector_version, server_version = _pgvector_versions(admin_dsn, database_name)

    return _GroupOutcome(
        results=tuple(results),
        rows=group_rows,
        pgvector_version=pgvector_version,
        server_version=server_version,
        qdrant_version=qdrant_version,
    )


def _write_record(
    path: Path,
    *,
    machine: bench_latency.Machine,
    database_label: str,
    corpus: str,
    documents: int,
    outcomes: Sequence[_GroupOutcome],
) -> None:
    """Persist everything measured **so far** — called after every completed group.

    The 2026-09-16 run wrote its record once, after all seventeen arms. It died on the twelfth, the
    file was never written, and eleven arms of a 105-minute run survived only because a stdio
    buffer happened to flush at exit. Writing here means a late failure costs the arms that did not
    run, and nothing else.
    """
    results = tuple(result for outcome in outcomes for result in outcome.results)
    if not results:
        return

    def version(field: str) -> str:
        return next(
            (getattr(outcome, field) for outcome in outcomes if getattr(outcome, field)), ""
        )

    run = SettingsRun(
        machine=machine,
        database=database_label,
        corpus=corpus,
        documents=documents,
        rows=max(outcome.rows for outcome in outcomes),
        width=WIDTH,
        pgvector_version=version("pgvector_version"),
        server_version=version("server_version"),
        qdrant_version=version("qdrant_version"),
        results=results,
        taken_at=datetime.now(UTC),
    )
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")


def _plans_for(all_arms: Sequence[Arm]) -> list[_GroupPlan]:
    """Every `(backend, index, precision)` group as one plan — the unit `main` parallelises.

    A group, not an arm, is the unit: arms within a group differ only by `iterative_scan` and
    share one indexed store, so splitting them would re-index the corpus per arm rather than per
    group — and re-indexing is ~90% of this measurement's wall time.
    """
    plans: list[_GroupPlan] = []
    for backend in Backend:
        grouped: dict[tuple[VectorIndexKind, VectorPrecision], list[Arm]] = {}
        for arm in (candidate for candidate in all_arms if candidate.backend is backend):
            grouped.setdefault(_group_key(arm), []).append(arm)
        plans.extend(
            _GroupPlan(
                backend=backend,
                index=index_kind,
                precision=precision,
                group_arms=tuple(group_arms),
            )
            for (index_kind, precision), group_arms in grouped.items()
        )
    return plans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True, help="a directory of documents")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help=(
            "a corpus manifest whose [[document]] entries name the indexable set and whose "
            "[[excluded]] entries name what to leave out; without it every file under --corpus "
            "is taken, which for open_ragbench means meeting two papers R29.2 aborts the run on"
        ),
    )
    parser.add_argument("--queries", type=int, default=50)
    parser.add_argument("--admin-dsn", default=None)
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--record", type=Path, default=None)
    parser.add_argument(
        "--jobs",
        type=int,
        default=DEFAULT_JOBS,
        help=(
            "how many groups run at once. Groups own separate databases and collections, so they "
            "do not interfere logically — but they share one server, so the p50/p95 figures are "
            "taken under contention and the record says so. 1 restores the serial run"
        ),
    )
    arguments = parser.parse_args(argv)
    if arguments.jobs < 1:
        print("--jobs must be at least 1", file=sys.stderr)
        return 2

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
    _say("run", f"machine: {machine.label}")

    sources = corpus_sources(arguments.corpus, manifest=arguments.manifest)
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
    database_label = _database_name()
    created_databases: list[str] = []
    registry_lock = threading.Lock()
    outcomes: list[_GroupOutcome] = []

    plans = _plans_for(all_arms)

    # Per backend, and written only by that backend's control group — which is why the control
    # gets a wave to itself. An approximate arm's recall is scored against the control's node ids,
    # so a wave that ran both at once would score some arms against an empty reference.
    truth_by_backend: dict[
        Backend, dict[bench_filtered.Selectivity | None, dict[str, tuple[str, ...]]]
    ] = {backend: {} for backend in Backend}
    waves = (
        [plan for plan in plans if plan.is_control],
        [plan for plan in plans if not plan.is_control],
    )

    def record_now() -> None:
        if arguments.record is not None:
            _write_record(
                arguments.record,
                machine=machine,
                database_label=database_label,
                corpus=arguments.corpus.name,
                documents=len(sources),
                outcomes=outcomes,
            )

    _say(
        "run",
        f"{len(plans)} group(s), {len(all_arms)} arm(s), {len(sources)} document(s), "
        f"{len(questions)} queries/arm, jobs={arguments.jobs}",
    )

    try:
        for number, wave in enumerate(waves, start=1):
            if not wave:
                continue
            names = ", ".join(plan.label for plan in wave)
            _say("run", f"wave {number} of 2: {len(wave)} group(s) in parallel — {names}")
            with ThreadPoolExecutor(max_workers=min(arguments.jobs, len(wave))) as executor:
                futures = [
                    executor.submit(
                        _run_one_group,
                        binary,
                        plan,
                        sources=sources,
                        questions=questions,
                        admin_dsn=admin_dsn,
                        qdrant_url=arguments.qdrant_url,
                        database_label=database_label,
                        truth_by_selectivity=truth_by_backend[plan.backend],
                        registry_lock=registry_lock,
                        created_databases=created_databases,
                    )
                    for plan in wave
                ]
                for future in futures:
                    outcomes.append(future.result())
                    record_now()
            _say(
                "run", f"wave {number} done: {sum(len(o.results) for o in outcomes)} arm(s) so far"
            )

        record_now()
        _say("run", f"complete: {sum(len(o.results) for o in outcomes)} arm(s)")
        return 0
    except (
        bench_latency.CountNotReportedError,
        bench_latency.RowCountMismatchError,
        bench_latency.MeasurementRefusedError,
        ValueError,
        psycopg.Error,
        OSError,
    ) as exc:
        record_now()
        _say("run", f"FAILED after {sum(len(o.results) for o in outcomes)} arm(s) — record kept")
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        for name in created_databases:
            _drop_database(admin_dsn, name)


if __name__ == "__main__":
    raise SystemExit(main())
