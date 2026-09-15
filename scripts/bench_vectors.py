"""Builds and reloads the real-embedder vector set — Phase 29 task **29.6**.

About 970 pinned arXiv PDFs, embedded once through `text-embedding-3-large` into 100,000 chunks,
so every later latency and recall measurement (29.1, 29.7-29.11) runs against the same fixed
corpus with no API call and no network. Five subcommands, each a step in that pipeline:

- `select`  pins which PDFs make the set, from the arXiv API.
- `fetch`   downloads and pins their bytes.
- `sketch`  indexes them once with the free `hash` embedder to learn exact chunk counts, picks
            the prefix reaching the target, counts billed tokens and prints the price. Nothing
            is spent.
- `embed`   refuses without `--yes`. With it, indexes the chosen PDFs through
            `openai-embeddings` and dumps the result to a vector set on disk.
- `load`    restores a vector set into a new throwaway database with no API call.

Everything below the subcommands is pure and unit-tested
(`tests/unit/scripts/test_bench_vectors.py`): the vector set's name, the price sketch, which PDFs
make the prefix, the pinned-PDF manifest and its pin check, and the on-disk vector set with its
integrity check. The subcommands compose those pieces with `weft` run as a subprocess, `psycopg`
and `urllib`, and are checked by running them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import fetch_corpus
import numpy as np
import numpy.typing as npt
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, ConfigDict

# --- the price, printed before the spend ---------------------------------------------------------


class EmbeddingModel(StrEnum):
    """A priced OpenAI embedding model. Prices are the vendor's published per-million rate."""

    LARGE = "text-embedding-3-large"
    SMALL = "text-embedding-3-small"

    @property
    def usd_per_million(self) -> Decimal:
        return Decimal("0.13") if self is EmbeddingModel.LARGE else Decimal("0.02")

    @property
    def native_width(self) -> int:
        return 3072 if self is EmbeddingModel.LARGE else 1536


class UnknownEmbeddingModelError(ValueError):
    """A `--model` name that is not one of `EmbeddingModel`'s published members."""


def model_named(name: str) -> EmbeddingModel:
    try:
        return EmbeddingModel(name)
    except ValueError as exc:
        known = ", ".join(member.value for member in EmbeddingModel)
        message = f"{name!r} is not a priced embedding model. Known models: {known}."
        raise UnknownEmbeddingModelError(message) from exc


class CostSketch(BaseModel):
    """What a run would cost, before it is run."""

    model_config = ConfigDict(frozen=True)

    pdfs: int
    chunks: int
    tokens: int
    model: EmbeddingModel
    usd: Decimal


def sketch_cost(*, pdfs: int, chunks: int, tokens: int, model: EmbeddingModel) -> CostSketch:
    usd = Decimal(tokens) * model.usd_per_million / Decimal(1_000_000)
    return CostSketch(pdfs=pdfs, chunks=chunks, tokens=tokens, model=model, usd=usd)


def print_sketch(sketch: CostSketch) -> None:
    quantised = sketch.usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    print(f"pdfs: {sketch.pdfs:,}")
    print(f"chunks: {sketch.chunks:,}")
    print(f"billed tokens: {sketch.tokens:,}")
    print(f"model: {sketch.model.value}")
    print(f"price: ${quantised} at ${sketch.model.usd_per_million} per 1M tokens")


# --- which PDFs make the set ----------------------------------------------------------------------


class InsufficientCorpusError(ValueError):
    """The fetched PDFs, summed in manifest order, never reach the target chunk count."""


def select_prefix(counts: Sequence[tuple[str, int]], *, target: int) -> tuple[str, ...]:
    chosen: list[str] = []
    total = 0
    for identifier, count in counts:
        if total >= target:
            break
        chosen.append(identifier)
        total += count
    if total < target:
        message = f"the fetched PDFs make {total:,} chunks, fewer than the {target:,} the set needs"
        raise InsufficientCorpusError(message)
    return tuple(chosen)


# --- naming ------------------------------------------------------------------------------------


def input_digest(pdf_sha256s: Iterable[str]) -> str:
    joined = "\n".join(sorted(pdf_sha256s))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def vector_set_name(digest: str, model: EmbeddingModel, width: int, day: date) -> str:
    return f"{digest[:12]}-{model.value}-{width}-{day.isoformat()}"


# --- the pinned PDFs -----------------------------------------------------------------------------


class BenchDocument(BaseModel):
    """One versioned arXiv document the set may draw on."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: str
    sha256: str


#: The feed-level `<id>` is an `http://arxiv.org/api/...` URL and does not match `abs/`, so this
#: pattern alone separates entry ids from it with no need to scope the match inside `<entry>`.
_ENTRY_ID_RE = re.compile(r"<id>http://arxiv\.org/abs/([^<]+)</id>")


def parse_arxiv_feed(body: bytes) -> tuple[BenchDocument, ...]:
    text = body.decode("utf-8")
    return tuple(
        BenchDocument(id=identifier, source=f"https://arxiv.org/pdf/{identifier}", sha256="")
        for identifier in _ENTRY_ID_RE.findall(text)
    )


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_manifest(path: Path, documents: Sequence[BenchDocument], *, query: str) -> None:
    lines = [f'query = "{_toml_escape(query)}"', ""]
    for document in documents:
        lines.append("[[document]]")
        lines.append(f'id = "{_toml_escape(document.id)}"')
        lines.append(f'source = "{_toml_escape(document.source)}"')
        lines.append(f'sha256 = "{_toml_escape(document.sha256)}"')
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def load_manifest(path: Path) -> tuple[BenchDocument, ...]:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    entries = raw.get("document", [])
    return tuple(
        BenchDocument(id=str(entry["id"]), source=str(entry["source"]), sha256=str(entry["sha256"]))
        for entry in entries
    )


def _manifest_query(path: Path) -> str:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    return str(raw.get("query", ""))


class PinMismatchError(ValueError):
    """A fetch returned bytes whose digest disagrees with the manifest's existing pin."""


def pin_or_verify(document: BenchDocument, body: bytes) -> BenchDocument:
    found = hashlib.sha256(body).hexdigest()
    if document.sha256 == "":
        return document.model_copy(update={"sha256": found})
    if document.sha256 == found:
        return document
    message = (
        f"{document.id} no longer matches its pin: expected {document.sha256[:16]}…, "
        f"found {found[:16]}…"
    )
    raise PinMismatchError(message)


# --- the vector set on disk -----------------------------------------------------------------------


class TableDump(BaseModel):
    """One table, dumped as Postgres would render its values as text."""

    model_config = ConfigDict(frozen=True)

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str | None, ...], ...]


class VectorSetMeta(BaseModel):
    """What a vector set is, and how it was made."""

    model_config = ConfigDict(frozen=True)

    name: str
    input_digest: str
    model: EmbeddingModel
    width: int
    day: date
    rows: int
    billed_tokens: int
    pdfs: int
    vectors_sha256: str
    tables_sha256: str


class VectorSet(BaseModel):
    """A reindexable set: the store's own tables. `vectors.f32` sits beside them on disk —

    100,000 x 3072 is ~307 million floats. As a `tuple[tuple[float, ...], ...]` of Python
    `float` objects that is on the order of 10 GB; as `<f4` on disk and a numpy memmap in
    memory it is 1.2 GB, read lazily. `L22.28`: this model carries only what is small — the
    vectors themselves are `open_vectors`'s job, not this model's field.
    """

    model_config = ConfigDict(frozen=True)

    meta: VectorSetMeta
    tables: tuple[TableDump, ...]


class VectorSetCorruptError(ValueError):
    """A vector set's data file does not match the digest its own `meta.json` pins."""


def _digest_file(path: Path) -> str:
    """sha256 of a file, read in 1 MB chunks — `fetch_corpus.digest`'s own shape, so a 1.2 GB
    `vectors.f32` is never read whole into memory just to be hashed."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_vector_set(
    root: Path,
    *,
    input_digest: str,
    model: EmbeddingModel,
    width: int,
    day: date,
    billed_tokens: int,
    pdfs: int,
    tables: Sequence[TableDump],
    vectors: npt.NDArray[np.float32],
) -> VectorSet:
    if vectors.ndim != 2:
        message = f"the set's vectors must be 2-D, got shape {vectors.shape}"
        raise ValueError(message)
    if vectors.shape[1] != width:
        message = f"the set has width {width}, but its vectors have {vectors.shape[1]} components"
        raise ValueError(message)

    nodes_table = next((table for table in tables if table.name == "weft_nodes"), None)
    found_rows = 0 if nodes_table is None else len(nodes_table.rows)
    if found_rows != vectors.shape[0]:
        message = (
            f"weft_nodes has {found_rows} rows, but there are {vectors.shape[0]} vectors. A "
            f"vector set's rows and vectors must be the same order and count."
        )
        raise ValueError(message)

    name = vector_set_name(input_digest, model, width, day)
    directory = root / name
    directory.mkdir(parents=True, exist_ok=False)

    vectors_path = directory / "vectors.f32"
    vectors.astype("<f4", copy=False).tofile(vectors_path)
    vectors_sha256 = _digest_file(vectors_path)

    tables_bytes = json.dumps([table.model_dump(mode="json") for table in tables]).encode("utf-8")
    (directory / "tables.json").write_bytes(tables_bytes)

    meta = VectorSetMeta(
        name=name,
        input_digest=input_digest,
        model=model,
        width=width,
        day=day,
        rows=int(vectors.shape[0]),
        billed_tokens=billed_tokens,
        pdfs=pdfs,
        vectors_sha256=vectors_sha256,
        tables_sha256=hashlib.sha256(tables_bytes).hexdigest(),
    )
    (directory / "meta.json").write_text(meta.model_dump_json(), encoding="utf-8")

    return VectorSet(meta=meta, tables=tuple(tables))


def _corrupt(name: str, expected: str, found: str) -> VectorSetCorruptError:
    message = f"{name} does not match its pin: expected {expected[:16]}…, found {found[:16]}…"
    return VectorSetCorruptError(message)


def read_vector_set(directory: Path) -> VectorSet:
    meta = VectorSetMeta.model_validate_json((directory / "meta.json").read_text(encoding="utf-8"))

    found_vectors_sha256 = _digest_file(directory / "vectors.f32")
    if found_vectors_sha256 != meta.vectors_sha256:
        raise _corrupt("vectors.f32", meta.vectors_sha256, found_vectors_sha256)

    tables_bytes = (directory / "tables.json").read_bytes()
    found_tables_sha256 = hashlib.sha256(tables_bytes).hexdigest()
    if found_tables_sha256 != meta.tables_sha256:
        raise _corrupt("tables.json", meta.tables_sha256, found_tables_sha256)

    raw_tables = json.loads(tables_bytes)
    tables = tuple(TableDump.model_validate(entry) for entry in raw_tables)

    return VectorSet(meta=meta, tables=tables)


def open_vectors(directory: Path, meta: VectorSetMeta) -> npt.NDArray[np.float32]:
    """A memory map onto `vectors.f32` — 1.2 GB of address space, not of resident memory, and
    never re-verified here: `read_vector_set` is the one place that checks the digest, so a
    caller who wants both calls it first and hands this function the `meta` it returned."""
    return np.memmap(
        directory / "vectors.f32", dtype="<f4", mode="r", shape=(meta.rows, meta.width)
    )


# ===================================================================================
# The subcommands. Not unit-tested — driven by running the binary, per the module docstring.
# ===================================================================================

_DEFAULT_QUERY: Final[str] = "cat:cs.IR AND submittedDate:[202401010000 TO 202412312359]"
_ARXIV_PAGE_SIZE: Final[int] = 100
_MANIFEST_CHECKPOINT: Final[int] = 25
_STORED_RE: Final[re.Pattern[str]] = re.compile(r"nodes now stored: (\d+)\.")


class SketchResult(BaseModel):
    """`sketch`'s own record — read back by `embed`, which never recomputes the prefix."""

    model_config = ConfigDict(frozen=True)

    chosen_ids: tuple[str, ...]
    chunks: int
    tokens: int
    model: EmbeddingModel
    input_digest: str


def _urlopen(url: str, *, timeout: int) -> bytes:
    if not url.startswith("https://"):
        message = f"refusing a non-https source: {url!r}"
        raise ValueError(message)
    # noqa: S310 on both lines below — the scheme is checked immediately above, which is the
    # audit S310 asks for. This is the one urlopen in the script; select and fetch both call it.
    request = urllib.request.Request(  # noqa: S310
        url, headers={"User-Agent": fetch_corpus.USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def _weft_command() -> list[str]:
    """The shipped `weft` binary — measured: `python -m weft_cli` fails, `weft_cli` ships no
    `__main__.py`, so this is `shutil.which`, never the module route."""
    weft = shutil.which("weft")
    if weft is None:
        message = (
            "no `weft` executable on PATH. `uv sync` installs weft-rag's console script into "
            "the active environment — activate it, or run this script with `uv run`."
        )
        raise FileNotFoundError(message)
    return [weft]


def _run_weft(
    argv: Sequence[str], *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    command = [*_weft_command(), *argv]
    # `command` is the path `shutil.which` resolved plus argv built here, the shape of
    # `scripts/check_kernel_isolated.py:34 "subprocess.run(command"`.
    return subprocess.run(  # noqa: S603
        command, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def _parse_stored_count(stdout: str) -> int:
    match = _STORED_RE.search(stdout)
    if match is None:
        message = f"could not find 'nodes now stored: N.' in weft index's output:\n{stdout}"
        raise ValueError(message)
    return int(match.group(1))


def _require_admin_dsn(admin_dsn: str | None) -> str:
    if not admin_dsn:
        message = "--admin-dsn is required (or set WEFT_DATABASE_URL) to administer a database."
        raise ValueError(message)
    return admin_dsn


def _database_exists(admin_dsn: str, name: str) -> bool:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        return cur.fetchone() is not None


def _create_database(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def _drop_database(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def _fresh_database(admin_dsn: str, name: str) -> str:
    _drop_database(admin_dsn, name)
    _create_database(admin_dsn, name)
    return make_conninfo(admin_dsn, dbname=name)


def _create_database_or_refuse(admin_dsn: str, name: str) -> str:
    if _database_exists(admin_dsn, name):
        message = f"database {name!r} already exists. `load` only writes into a fresh database."
        raise FileExistsError(message)
    _create_database(admin_dsn, name)
    return make_conninfo(admin_dsn, dbname=name)


def _primary_key_column(cur: psycopg.Cursor[tuple[Any, ...]], table_name: str) -> str:
    cur.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.table_name = %s AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        LIMIT 1
        """,
        (table_name,),
    )
    row = cur.fetchone()
    if row is None:
        message = f"{table_name} has no primary key to order a dump by"
        raise ValueError(message)
    return row[0]


def _dumpable_columns(
    cur: psycopg.Cursor[tuple[Any, ...]], table_name: str, *, exclude: frozenset[str]
) -> tuple[str, ...]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND is_generated <> 'ALWAYS'
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return tuple(name for (name,) in cur.fetchall() if name not in exclude)


def _dump_table(conn: psycopg.Connection[tuple[Any, ...]], table_name: str) -> TableDump:
    with conn.cursor() as cur:
        columns = _dumpable_columns(cur, table_name, exclude=frozenset())
        pk = _primary_key_column(cur, table_name)
        select_list = sql.SQL(", ").join(
            sql.SQL("{}::text").format(sql.Identifier(column)) for column in columns
        )
        query = sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
            select_list, sql.Identifier(table_name), sql.Identifier(pk)
        )
        cur.execute(query)
        rows = tuple(tuple(row) for row in cur.fetchall())
    return TableDump(name=table_name, columns=columns, rows=rows)


def _dump_nodes_with_vectors(
    conn: psycopg.Connection[tuple[Any, ...]], table_name: str, *, expected_rows: int
) -> tuple[TableDump, npt.NDArray[np.float32]]:
    """The 100,000 x 3072 dump. A named (server-side) cursor streams rows in `itersize`
    batches rather than pulling all of them across the wire at once, `register_vector`
    makes each `embedding` arrive as a `pgvector.Vector` rather than text to parse, and the
    vectors land straight into a preallocated array — never a Python list of them."""
    register_vector(conn)
    with conn.cursor() as meta_cur:
        columns = _dumpable_columns(meta_cur, table_name, exclude=frozenset({"embedding"}))
        pk = _primary_key_column(meta_cur, table_name)

    select_list = sql.SQL(", ").join(
        sql.SQL("{}::text").format(sql.Identifier(column)) for column in columns
    )
    query = sql.SQL("SELECT {}, embedding FROM {} ORDER BY {}").format(
        select_list, sql.Identifier(table_name), sql.Identifier(pk)
    )

    rows: list[tuple[str | None, ...]] = []
    vectors: npt.NDArray[np.float32] = np.empty((expected_rows, 0), dtype=np.float32)
    with conn.cursor(name="bench_dump") as cur:
        cur.itersize = 2000
        cur.execute(query)
        for index, record in enumerate(cur):
            *text_values, embedding = record
            rows.append(tuple(None if value is None else str(value) for value in text_values))
            vector = embedding.to_numpy()
            if index == 0:
                vectors = np.empty((expected_rows, vector.shape[0]), dtype=np.float32)
            vectors[index] = vector
    return TableDump(name=table_name, columns=columns, rows=tuple(rows)), vectors


def _count_tokens_cl100k(contents: Sequence[str]) -> int:
    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")
    return sum(len(encoding.encode(content)) for content in contents)


def _table_named(vector_set: VectorSet, name: str) -> TableDump:
    for table in vector_set.tables:
        if table.name == name:
            return table
    message = f"the vector set has no table named {name!r}"
    raise ValueError(message)


def _copy_table(conn: psycopg.Connection[tuple[Any, ...]], table: TableDump) -> None:
    columns = sql.SQL(", ").join(sql.Identifier(column) for column in table.columns)
    query = sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier(table.name), columns)
    with conn.cursor() as cur, cur.copy(query) as copy:
        for row in table.rows:
            copy.write_row(row)


def _copy_nodes(
    conn: psycopg.Connection[tuple[Any, ...]],
    table: TableDump,
    rows: Sequence[tuple[str | None, ...]],
    vectors: npt.NDArray[np.float32],
) -> None:
    """Streams `rows` beside `vectors` — a memory-mapped slice, not a materialised list — one
    `COPY` row at a time."""
    columns = sql.SQL(", ").join(sql.Identifier(column) for column in (*table.columns, "embedding"))
    query = sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier(table.name), columns)
    with conn.cursor() as cur, cur.copy(query) as copy:
        for row, vector in zip(rows, vectors, strict=True):
            rendered = "[" + ",".join(repr(float(component)) for component in vector) + "]"
            copy.write_row((*row, rendered))


def _provision_schema(dsn: str) -> None:
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        (tmp / "seed.txt").write_text("bench-vectors provisioning seed.\n", encoding="utf-8")
        env = os.environ.copy()
        env["WEFT_DATABASE_URL"] = dsn
        result = _run_weft(["index", str(tmp), "--pipeline", "index-text"], cwd=tmp, env=env)
        if result.returncode != 0:
            message = (
                "provisioning failed (`weft index --pipeline index-text`): "
                f"{result.stderr or result.stdout}"
            )
            raise ValueError(message)


# --- select ---------------------------------------------------------------------------------------


def cmd_select(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    if manifest.exists():
        message = f"{manifest} already exists. `select` does not overwrite a manifest."
        raise FileExistsError(message)

    documents: list[BenchDocument] = []
    seen: set[str] = set()
    start = 0
    fetched_any = False
    while len(documents) < args.count:
        if fetched_any:
            time.sleep(fetch_corpus.POLITE_DELAY_SECONDS)
        url = (
            "https://export.arxiv.org/api/query?search_query="
            f"{urllib.parse.quote(args.query, safe='')}"
            f"&sortBy=submittedDate&sortOrder=ascending&start={start}&max_results={_ARXIV_PAGE_SIZE}"
        )
        body = _urlopen(url, timeout=60)
        fetched_any = True
        page = parse_arxiv_feed(body)
        if not page:
            break
        for document in page:
            if document.id in seen:
                continue
            seen.add(document.id)
            documents.append(document)
            if len(documents) >= args.count:
                break
        start += _ARXIV_PAGE_SIZE

    chosen = tuple(documents[: args.count])
    write_manifest(manifest, chosen, query=args.query)
    print(f"selected {len(chosen)} documents into {manifest}")
    return 0


# --- fetch ----------------------------------------------------------------------------------------


def cmd_fetch(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    documents = list(load_manifest(manifest))
    query = _manifest_query(manifest)
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    updated: list[BenchDocument] = []
    fetched = present = failed = 0
    since_checkpoint = 0

    for document in documents:
        target = dest / f"{document.id}.pdf"
        if target.exists():
            body = target.read_bytes()
            if document.sha256 == "" or hashlib.sha256(body).hexdigest() == document.sha256:
                present += 1
                updated.append(pin_or_verify(document, body) if document.sha256 == "" else document)
                continue

        if since_checkpoint:
            time.sleep(fetch_corpus.POLITE_DELAY_SECONDS)
        since_checkpoint += 1
        try:
            body = _urlopen(document.source, timeout=120)
            pinned = pin_or_verify(document, body)
        except (urllib.error.URLError, TimeoutError, PinMismatchError, ValueError) as exc:
            print(f"  failed {document.id}: {exc}", file=sys.stderr)
            failed += 1
            updated.append(document)
        else:
            target.write_bytes(body)
            updated.append(pinned)
            fetched += 1

        if since_checkpoint >= _MANIFEST_CHECKPOINT:
            write_manifest(manifest, tuple(updated) + tuple(documents[len(updated) :]), query=query)
            since_checkpoint = 0

    write_manifest(manifest, tuple(updated), query=query)
    print(f"fetched {fetched}, already present {present}, failed {failed}")
    return 1 if failed > 0 else 0


# --- sketch ------------------------------------------------------------------------------------


def cmd_sketch(args: argparse.Namespace) -> int:
    admin_dsn = _require_admin_dsn(args.admin_dsn)
    documents = load_manifest(Path(args.manifest))
    pdfs_dir = Path(args.pdfs).resolve()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    model = model_named(args.model)

    full_digest = input_digest(document.sha256 for document in documents if document.sha256)
    db_name = f"weft_bench_sketch_{full_digest[:12]}"
    dsn = _fresh_database(admin_dsn, db_name)

    try:
        env = os.environ.copy()
        env["WEFT_DATABASE_URL"] = dsn
        result = _run_weft(
            ["index", str(pdfs_dir), "--pipeline", "index-pdf-text"], cwd=work, env=env
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        stored = _parse_stored_count(result.stdout)

        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM weft_nodes")
            row = cur.fetchone()
            counted = 0 if row is None else int(row[0])
            if counted != stored:
                message = (
                    f"weft index reported {stored} nodes stored, but weft_nodes holds {counted}"
                )
                raise ValueError(message)

            cur.execute("SELECT s, count(*) FROM weft_nodes, unnest(sources) AS s GROUP BY s")
            source_rows = cur.fetchall()

            counts_by_stem: dict[str, int] = {}
            sources_by_stem: dict[str, str] = {}
            for source, count in source_rows:
                stem = Path(str(source)).stem
                counts_by_stem[stem] = counts_by_stem.get(stem, 0) + int(count)
                sources_by_stem[stem] = str(source)

            counts = tuple(
                (document.id, counts_by_stem.get(document.id, 0)) for document in documents
            )
            chosen = select_prefix(counts, target=args.target)

            chosen_sources = [
                sources_by_stem[identifier]
                for identifier in chosen
                if identifier in sources_by_stem
            ]
            cur.execute(
                "SELECT DISTINCT id, content FROM weft_nodes, unnest(sources) AS s "
                "WHERE s = ANY(%s)",
                (chosen_sources,),
            )
            content_rows = cur.fetchall()

        tokens = _count_tokens_cl100k([str(content) for _id, content in content_rows])
        chosen_chunks = sum(counts_by_stem.get(identifier, 0) for identifier in chosen)

        sketch = sketch_cost(pdfs=len(chosen), chunks=chosen_chunks, tokens=tokens, model=model)
        print_sketch(sketch)

        chosen_digest = input_digest(
            document.sha256 for document in documents if document.id in chosen and document.sha256
        )
        result_model = SketchResult(
            chosen_ids=chosen,
            chunks=chosen_chunks,
            tokens=tokens,
            model=model,
            input_digest=chosen_digest,
        )
        (work / "sketch.json").write_text(result_model.model_dump_json(), encoding="utf-8")
    finally:
        _drop_database(admin_dsn, db_name)

    return 0


# --- embed ----------------------------------------------------------------------------------------


def cmd_embed(args: argparse.Namespace) -> int:
    # The sketch is read and printed before anything checks whether spending is even possible —
    # `--work /nonexistent` must name the missing sketch, not an absent --admin-dsn.
    work = Path(args.work)
    sketch_path = work / "sketch.json"
    if not sketch_path.exists():
        message = f"no sketch at {sketch_path}. Run `sketch` first, into the same --work directory."
        raise FileNotFoundError(message)
    sketch = SketchResult.model_validate_json(sketch_path.read_text(encoding="utf-8"))
    print_sketch(
        sketch_cost(
            pdfs=len(sketch.chosen_ids),
            chunks=sketch.chunks,
            tokens=sketch.tokens,
            model=sketch.model,
        )
    )
    if not args.yes:
        print("pass --yes to spend this", file=sys.stderr)
        return 2

    admin_dsn = _require_admin_dsn(args.admin_dsn)
    pdfs_dir = Path(args.pdfs).resolve()
    staged = work / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    for identifier in sketch.chosen_ids:
        source = pdfs_dir / f"{identifier}.pdf"
        target = staged / f"{identifier}.pdf"
        if target.is_symlink() or target.exists():
            target.unlink()
        target.symlink_to(source)

    db_name = f"weft_bench_embed_{sketch.input_digest[:12]}"
    if not _database_exists(admin_dsn, db_name):
        _create_database(admin_dsn, db_name)
    dsn = make_conninfo(admin_dsn, dbname=db_name)

    pipelines_dir = work / "pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    pipeline_doc = (
        "name: bench-embed\n"
        "extends: index-pdf-text\n"
        "replace:\n"
        f"  - {{id: embed, use: openai-embeddings, with: {{model: {sketch.model.value}}}}}\n"
    )
    (pipelines_dir / "bench-embed.yaml").write_text(pipeline_doc, encoding="utf-8")
    (work / "weft.toml").write_text(
        '[packs.openai]\napi_key = "${env:OPENAI_API_KEY}"\n', encoding="utf-8"
    )

    env = os.environ.copy()
    env["WEFT_DATABASE_URL"] = dsn
    result = _run_weft(["index", "staged", "--pipeline", "bench-embed"], cwd=work, env=env)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    stored = _parse_stored_count(result.stdout)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM weft_nodes")
            row = cur.fetchone()
            counted = 0 if row is None else int(row[0])
        if stored != counted or counted != sketch.chunks:
            message = (
                f"weft index reported {stored} nodes stored, weft_nodes holds {counted}, the "
                f"sketch chose {sketch.chunks} chunks — these must all agree before spending "
                f"is trusted. Database {db_name} was kept for inspection."
            )
            raise ValueError(message)

        nodes_table, vectors = _dump_nodes_with_vectors(conn, "weft_nodes", expected_rows=counted)
        sources_table = _dump_table(conn, "weft_sources")

    width = vectors.shape[1] if vectors.shape[0] else sketch.model.native_width
    out = Path(args.out)
    written = write_vector_set(
        out,
        input_digest=sketch.input_digest,
        model=sketch.model,
        width=width,
        day=date.today(),
        billed_tokens=sketch.tokens,
        pdfs=len(sketch.chosen_ids),
        tables=(nodes_table, sources_table),
        vectors=vectors,
    )
    _drop_database(admin_dsn, db_name)

    print(f"vector set: {out / written.meta.name}")
    print(f"rows: {written.meta.rows}")
    return 0


# --- load -----------------------------------------------------------------------------------------


def cmd_load(args: argparse.Namespace) -> int:
    admin_dsn = _require_admin_dsn(args.admin_dsn)
    set_dir = Path(args.set_dir)
    vector_set = read_vector_set(set_dir)
    dsn = _create_database_or_refuse(admin_dsn, args.database)
    _provision_schema(dsn)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE weft_nodes, weft_sources")
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM weft_nodes")
            before_nodes_row = cur.fetchone()
            cur.execute("SELECT count(*) FROM weft_sources")
            before_sources_row = cur.fetchone()
        before_nodes = 0 if before_nodes_row is None else int(before_nodes_row[0])
        before_sources = 0 if before_sources_row is None else int(before_sources_row[0])
        if before_nodes != 0 or before_sources != 0:
            message = (
                f"expected an empty database after TRUNCATE, found {before_nodes} nodes and "
                f"{before_sources} sources"
            )
            raise ValueError(message)

        _copy_table(conn, _table_named(vector_set, "weft_sources"))

        nodes_table = _table_named(vector_set, "weft_nodes")
        row_count = (
            len(nodes_table.rows) if args.rows is None else min(args.rows, len(nodes_table.rows))
        )
        vectors = open_vectors(set_dir, vector_set.meta)[:row_count]
        _copy_nodes(conn, nodes_table, nodes_table.rows[:row_count], vectors)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM weft_nodes")
            after_row = cur.fetchone()
        after_nodes = 0 if after_row is None else int(after_row[0])
        if after_nodes != row_count:
            message = f"loaded {after_nodes} rows, expected {row_count}"
            raise ValueError(message)

    print(f"before: 0 rows   after: {row_count} rows")
    print(f"loaded {row_count} rows into {args.database}")
    return 0


# --- argparse ----------------------------------------------------------------------------------


def _add_admin_dsn(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--admin-dsn",
        default=os.environ.get("WEFT_DATABASE_URL"),
        help="a DSN naming the Postgres server to administer databases on (default: "
        "$WEFT_DATABASE_URL)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench_vectors.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    select = subparsers.add_parser("select", help="pin which PDFs make the corpus")
    select.add_argument("--manifest", type=Path, required=True)
    select.add_argument("--query", default=_DEFAULT_QUERY)
    select.add_argument("--count", type=int, default=1100)
    select.set_defaults(func=cmd_select)

    fetch = subparsers.add_parser("fetch", help="download and pin the selected PDFs")
    fetch.add_argument("--manifest", type=Path, required=True)
    fetch.add_argument("--dest", type=Path, required=True)
    fetch.set_defaults(func=cmd_fetch)

    sketch = subparsers.add_parser("sketch", help="index once for free and price the target")
    sketch.add_argument("--manifest", type=Path, required=True)
    sketch.add_argument("--pdfs", type=Path, required=True)
    sketch.add_argument("--work", type=Path, required=True)
    sketch.add_argument("--target", type=int, default=100_000)
    sketch.add_argument("--model", default=EmbeddingModel.LARGE.value)
    _add_admin_dsn(sketch)
    sketch.set_defaults(func=cmd_sketch)

    embed = subparsers.add_parser("embed", help="spend the sketch's price and write the vector set")
    embed.add_argument("--work", type=Path, required=True)
    embed.add_argument("--pdfs", type=Path, required=True)
    embed.add_argument("--out", type=Path, required=True)
    embed.add_argument("--yes", action="store_true")
    _add_admin_dsn(embed)
    embed.set_defaults(func=cmd_embed)

    load = subparsers.add_parser("load", help="reload a vector set with no API call")
    load.add_argument("--set", dest="set_dir", type=Path, required=True)
    load.add_argument("--database", required=True)
    load.add_argument("--rows", type=int, default=None)
    _add_admin_dsn(load)
    load.set_defaults(func=cmd_load)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        ValueError,
        FileExistsError,
        FileNotFoundError,
        psycopg.Error,
        subprocess.SubprocessError,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
