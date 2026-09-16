"""Builds and reloads the real-embedder vector set — Phase 29 task **29.6**.

About 970 pinned PDFs, embedded once through `text-embedding-3-large` into 100,000 chunks, so
every later latency and recall measurement (29.1, 29.7-29.11) runs against the same fixed corpus
with no API call and no network. Seven subcommands, each a step in that pipeline:

- `select`  pins which PDFs make the set — from `vectara/open_ragbench`'s 1,000 arXiv papers at a
            pinned revision (the default), or from the PMC Open Access bucket on AWS Open Data.
- `fetch`   downloads and pins their bytes.
- `exclude` drops a paper from the set by id, recording the reason in the manifest itself.
- `sketch`  indexes them once with the free `hash` embedder to learn exact chunk counts, picks
            the prefix reaching the target, counts billed tokens and prints the price. Nothing
            is spent.
- `embed`   refuses without `--yes`. With it, indexes the chosen PDFs through
            `openai-embeddings` in resumable slices of `--batch-size` papers, and dumps the
            result to a vector set on disk once every chosen paper is done.
- `load`    restores a vector set into a new throwaway database with no API call.
- `subset`  cuts a vector set down to the manifest-order prefix of whole papers that reaches a
            chunk target, and writes it as its own checksummed vector set.

Everything below the subcommands is pure and unit-tested
(`tests/unit/scripts/test_bench_vectors.py`): the vector set's name, the price sketch, which PDFs
make the prefix, the pinned-PDF manifest and its pin check, and the on-disk vector set with its
integrity check. The subcommands compose those pieces with `weft` run as a subprocess, `psycopg`
and `urllib`, and are checked by running them.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import itertools
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
from pathlib import Path, PurePosixPath
from typing import Any, Final

import bench_latency
import fetch_corpus
import numpy as np
import numpy.typing as npt
import psycopg
from open_ragbench import RAGBENCH_REVISION, ragbench_file_url
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

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


def distinct_prefix(
    pairs: Iterable[tuple[str, str]], order: Sequence[str], *, target: int
) -> tuple[str, ...]:
    nodes_by_paper: dict[str, set[str]] = {}
    for node_id, paper in frozenset(pairs):
        nodes_by_paper.setdefault(paper, set()).add(node_id)

    chosen: list[str] = []
    union: set[str] = set()
    for paper in order:
        if len(union) >= target:
            break
        chosen.append(paper)
        union |= nodes_by_paper.get(paper, set())
    if len(union) < target:
        message = (
            f"the fetched PDFs make {len(union):,} chunks, fewer than the {target:,} the set needs"
        )
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
    """One versioned document the set may draw on."""

    model_config = ConfigDict(frozen=True)

    id: str
    source: str
    sha256: str


#: PubMed Central Open Access bucket on AWS Open Data: anonymous HTTPS, built for bulk reads, and
#: keyed by versioned article (`PMC10000014.1/PMC10000014.1.pdf`), read 2026-09-15. Chosen over
#: arXiv, whose API answered 429 and whose PDF host answered 406 to this machine that day.
PMC_BUCKET_URL: Final[str] = "https://pmc-oa-opendata.s3.amazonaws.com"

#: `ListObjectsV2` with `delimiter=/` groups one `<CommonPrefixes><Prefix>` per versioned article;
#: the bucket-level `<Prefix></Prefix>` sits outside a `<CommonPrefixes>` and so does not match.
_COMMON_PREFIX_RE = re.compile(r"<CommonPrefixes>\s*<Prefix>([^<]+?)/</Prefix>\s*</CommonPrefixes>")
_CONTINUATION_TOKEN_RE = re.compile(r"<NextContinuationToken>([^<]+)</NextContinuationToken>")


class S3Page(BaseModel):
    """One page of an S3 `ListObjectsV2` listing, grouped by `delimiter=/`."""

    model_config = ConfigDict(frozen=True)

    articles: tuple[str, ...]
    continuation: str | None


def parse_s3_listing(body: bytes) -> S3Page:
    text = body.decode("utf-8")
    articles = tuple(_COMMON_PREFIX_RE.findall(text))
    match = _CONTINUATION_TOKEN_RE.search(text)
    return S3Page(articles=articles, continuation=None if match is None else match.group(1))


class PmcArticle(BaseModel):
    """One article's metadata, as `<key>.json` carries it. `extra="ignore"` because the real
    JSON carries more fields than admission needs."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    pmcid: str
    version: int
    is_pmc_openaccess: bool
    is_retracted: bool
    is_historical_ocr: bool
    license_code: str | None
    pdf_url: str | None


#: Licences that permit any use. `CC BY-NC` and similar are excluded even though they are open
#: access, because "open access" and "reusable for a benchmark corpus" are not the same claim.
ADMITTED_LICENSES: Final[frozenset[str]] = frozenset({"CC BY", "CC0"})


def admitted(article: PmcArticle) -> bool:
    return (
        article.is_pmc_openaccess
        and not article.is_retracted
        and not article.is_historical_ocr
        and article.license_code in ADMITTED_LICENSES
        and article.pdf_url is not None
    )


def document_for(article_key: str) -> BenchDocument:
    """Pins an article to the PDF under its own versioned prefix — the key already carries the
    revision, so the same key can never later resolve to different bytes."""
    return BenchDocument(
        id=article_key,
        source=f"{PMC_BUCKET_URL}/{article_key}/{article_key}.pdf",
        sha256="",
    )


# --- the open_ragbench corpus ---------------------------------------------------------------------


class RagbenchLabel(BaseModel):
    """One `qrels.json` entry: which paper and section a query is labelled against."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    doc_id: str
    section_id: int


def golden_papers(qrels_body: bytes) -> frozenset[str]:
    labels = TypeAdapter(dict[str, RagbenchLabel]).validate_json(qrels_body)
    return frozenset(label.doc_id for label in labels.values())


class UnpinnablePaperError(ValueError):
    """A `pdf_urls.json` id and URL that could later resolve to different bytes: the id carries
    no arXiv version suffix, or the URL is not exactly `https://arxiv.org/pdf/<id>`."""


_ARXIV_VERSIONED_ID_RE: Final[re.Pattern[str]] = re.compile(r"\d{4}\.\d{4,5}v\d+")


def ragbench_documents(pdf_urls_body: bytes, golden: frozenset[str]) -> tuple[BenchDocument, ...]:
    pdf_urls = TypeAdapter(dict[str, str]).validate_json(pdf_urls_body)

    documents: dict[str, BenchDocument] = {}
    for identifier, url in pdf_urls.items():
        expected_url = f"https://arxiv.org/pdf/{identifier}"
        if _ARXIV_VERSIONED_ID_RE.fullmatch(identifier) is None:
            message = f"{identifier} carries no arXiv version suffix, so its bytes could change"
            raise UnpinnablePaperError(message)
        if url != expected_url:
            message = (
                f"{identifier} points at {url!r}, not its own pinned URL {expected_url!r}, so "
                "its bytes could change"
            )
            raise UnpinnablePaperError(message)
        documents[identifier] = BenchDocument(id=identifier, source=expected_url, sha256="")

    golden_ids = sorted(identifier for identifier in documents if identifier in golden)
    rest_ids = sorted(identifier for identifier in documents if identifier not in golden)
    return tuple(documents[identifier] for identifier in (*golden_ids, *rest_ids))


class Exclusion(BaseModel):
    """A paper left out of the set, and why."""

    model_config = ConfigDict(frozen=True)

    id: str
    reason: str


class UnknownExclusionError(ValueError):
    """An exclusion names a paper the manifest's documents do not hold — a typo, or an id already
    excluded."""


def exclude_documents(
    documents: Sequence[BenchDocument], exclusions: Sequence[Exclusion]
) -> tuple[BenchDocument, ...]:
    known_ids = {document.id for document in documents}
    for exclusion in exclusions:
        if exclusion.id not in known_ids:
            message = f"{exclusion.id} is not in the manifest, so it cannot be excluded"
            raise UnknownExclusionError(message)
    excluded_ids = {exclusion.id for exclusion in exclusions}
    return tuple(document for document in documents if document.id not in excluded_ids)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_manifest(
    path: Path,
    documents: Sequence[BenchDocument],
    *,
    query: str,
    excluded: Sequence[Exclusion] = (),
) -> None:
    lines = [f'query = "{_toml_escape(query)}"', ""]
    for document in documents:
        lines.append("[[document]]")
        lines.append(f'id = "{_toml_escape(document.id)}"')
        lines.append(f'source = "{_toml_escape(document.source)}"')
        lines.append(f'sha256 = "{_toml_escape(document.sha256)}"')
        lines.append("")
    for exclusion in excluded:
        lines.append("[[excluded]]")
        lines.append(f'id = "{_toml_escape(exclusion.id)}"')
        lines.append(f'reason = "{_toml_escape(exclusion.reason)}"')
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


def load_exclusions(path: Path) -> tuple[Exclusion, ...]:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    entries = raw.get("excluded", [])
    return tuple(Exclusion(id=str(entry["id"]), reason=str(entry["reason"])) for entry in entries)


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
    derived_from: str | None = None


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
    derived_from: str | None = None,
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
        derived_from=derived_from,
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


class UnattributableRowError(ValueError):
    """A row's `sources` names no paper, so it cannot be attributed to any."""


def papers_of_sources(rendered: str | None) -> tuple[str, ...]:
    if rendered is None:
        message = f"0 sources: {rendered!r}"
        raise UnattributableRowError(message)
    inner = rendered.removeprefix("{").removesuffix("}")
    elements = inner.split(",") if inner else []
    if not elements:
        message = f"0 sources: {rendered!r}"
        raise UnattributableRowError(message)
    return tuple(PurePosixPath(element).stem for element in elements)


def chunks_per_paper(pairs: Iterable[tuple[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pair in frozenset(pairs):
        paper = pair[1]
        counts[paper] = counts.get(paper, 0) + 1
    return counts


def distinct_chunks(pairs: Iterable[tuple[str, str]], papers: frozenset[str]) -> int:
    return len({node_id for node_id, paper in pairs if paper in papers})


def subset_vector_set(
    set_dir: Path,
    root: Path,
    *,
    documents: Sequence[BenchDocument],
    target: int,
    day: date,
) -> VectorSet:
    parent = read_vector_set(set_dir)
    vectors = open_vectors(set_dir, parent.meta)

    known_table_names = frozenset({"weft_nodes", "weft_sources"})
    for table in parent.tables:
        if table.name not in known_table_names:
            message = f"the vector set carries a table this subset does not know: {table.name!r}"
            raise ValueError(message)

    nodes = _table_named(parent, "weft_nodes")
    id_index = nodes.columns.index("id")
    sources_index = nodes.columns.index("sources")
    row_papers = tuple(papers_of_sources(row[sources_index]) for row in nodes.rows)
    pairs = tuple(
        (row[id_index] or "", paper)
        for row, papers in zip(nodes.rows, row_papers, strict=True)
        for paper in papers
    )

    chosen = distinct_prefix(pairs, [d.id for d in documents], target=target)
    chosen_set = frozenset(chosen)

    kept = [
        i for i, papers in enumerate(row_papers) if any(paper in chosen_set for paper in papers)
    ]
    subset_nodes = TableDump(
        name="weft_nodes",
        columns=nodes.columns,
        rows=tuple(nodes.rows[i] for i in kept),
    )
    subset_vectors = np.asarray(vectors[kept], dtype=np.float32)

    sources = _table_named(parent, "weft_sources")
    source_id_index = sources.columns.index("id")
    subset_sources = TableDump(
        name="weft_sources",
        columns=sources.columns,
        rows=tuple(
            row
            for row in sources.rows
            if PurePosixPath(str(row[source_id_index])).stem in chosen_set
        ),
    )

    return write_vector_set(
        root,
        input_digest=input_digest(d.sha256 for d in documents if d.id in chosen_set),
        model=parent.meta.model,
        width=parent.meta.width,
        day=day,
        billed_tokens=0,
        pdfs=len(chosen),
        tables=(subset_nodes, subset_sources),
        vectors=subset_vectors,
        derived_from=parent.meta.name,
    )


# ===================================================================================
# The subcommands. Not unit-tested — driven by running the binary, per the module docstring.
# ===================================================================================

_MANIFEST_CHECKPOINT: Final[int] = 25
_STORED_RE: Final[re.Pattern[str]] = re.compile(r"nodes now stored: (\d+)\.")

#: HTTP codes worth retrying: throttling (429), the transient server errors, and 406, which arXiv
#: used as a throttle on 2026-09-15, answering it to one request and 200 to the next.
_RETRYABLE_HTTP_CODES: Final[frozenset[int]] = frozenset({406, 429, 500, 502, 503, 504})
_RETRY_DELAYS_SECONDS: Final[tuple[int, ...]] = (2, 4, 8, 16)


class SketchResult(BaseModel):
    """`sketch`'s own record — read back by `embed`, which never recomputes the prefix."""

    model_config = ConfigDict(frozen=True)

    chosen_ids: tuple[str, ...]
    chunks: int
    tokens: int
    model: EmbeddingModel
    input_digest: str


def _urlopen(url: str, *, timeout: int, accept: str) -> bytes:
    if not url.startswith("https://"):
        message = f"refusing a non-https source: {url!r}"
        raise ValueError(message)
    # noqa: S310 on both lines below — the scheme is checked immediately above, which is the
    # audit S310 asks for. This is the one urlopen in the script; select and fetch both call it.
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={
            "User-Agent": fetch_corpus.USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en",
        },
    )
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE_HTTP_CODES:
                raise
            last_exc = exc
        except (
            http.client.IncompleteRead,
            urllib.error.URLError,
            TimeoutError,
            ConnectionResetError,
        ) as exc:
            last_exc = exc
        if attempt < len(_RETRY_DELAYS_SECONDS):
            time.sleep(_RETRY_DELAYS_SECONDS[attempt])
    if last_exc is not None:
        raise last_exc
    message = "_urlopen exhausted its retries without recording an exception"
    raise RuntimeError(message)


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


class CorpusSource(StrEnum):
    """Which real-world corpus `select` draws documents from."""

    PMC = "pmc"
    OPEN_RAGBENCH = "open-ragbench"


def cmd_select(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    if manifest.exists():
        message = f"{manifest} already exists. `select` does not overwrite a manifest."
        raise FileExistsError(message)

    if args.source == CorpusSource.OPEN_RAGBENCH:
        return _select_open_ragbench(manifest)
    return _select_pmc(args, manifest)


def _select_open_ragbench(manifest: Path) -> int:
    pdf_urls_body = _urlopen(
        ragbench_file_url("pdf_urls.json"), timeout=60, accept="application/json"
    )
    qrels_body = _urlopen(ragbench_file_url("qrels.json"), timeout=60, accept="application/json")

    golden = golden_papers(qrels_body)
    documents = ragbench_documents(pdf_urls_body, golden)
    golden_count = sum(1 for document in documents if document.id in golden)

    write_manifest(
        manifest,
        documents,
        query=f"open_ragbench revision {RAGBENCH_REVISION} golden papers first",
    )
    print(
        f"selected {len(documents)} documents into {manifest} ({golden_count} golden papers first)"
    )
    return 0


def _select_pmc(args: argparse.Namespace, manifest: Path) -> int:
    documents: list[BenchDocument] = []
    looked_at = 0
    skipped_unadmitted = 0
    skipped_unreadable = 0

    continuation: str | None = None
    while len(documents) < args.count:
        if continuation is None:
            listing_url = (
                f"{PMC_BUCKET_URL}/?list-type=2&delimiter=/&max-keys=1000"
                f"&start-after={args.start_after}"
            )
        else:
            listing_url = (
                f"{PMC_BUCKET_URL}/?list-type=2&delimiter=/&max-keys=1000"
                f"&continuation-token={urllib.parse.quote(continuation, safe='')}"
            )
        page = parse_s3_listing(_urlopen(listing_url, timeout=60, accept="application/xml"))

        for key in page.articles:
            if len(documents) >= args.count:
                break
            looked_at += 1
            article_body = _urlopen(
                f"{PMC_BUCKET_URL}/{key}/{key}.json", timeout=60, accept="application/json"
            )
            try:
                article = PmcArticle.model_validate_json(article_body)
            except ValidationError:
                skipped_unreadable += 1
                continue
            if not admitted(article):
                skipped_unadmitted += 1
                continue
            documents.append(document_for(key))

        continuation = page.continuation
        if continuation is None:
            break

    if len(documents) < args.count:
        message = (
            f"the bucket held only {len(documents):,} admitted articles from start-after "
            f"{args.start_after!r} ({looked_at:,} looked at), fewer than the {args.count:,} "
            "the set needs"
        )
        raise InsufficientCorpusError(message)

    chosen = tuple(documents[: args.count])
    write_manifest(
        manifest,
        chosen,
        query=(
            f"pmc-oa-opendata start-after {args.start_after} "
            f"licences {','.join(sorted(ADMITTED_LICENSES))}"
        ),
    )
    print(
        f"selected {len(chosen)} documents into {manifest} (looked at {looked_at} articles, "
        f"skipped {skipped_unadmitted} unadmitted, {skipped_unreadable} unreadable)"
    )
    return 0


# --- fetch ----------------------------------------------------------------------------------------


def cmd_fetch(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    documents = list(load_manifest(manifest))
    query = _manifest_query(manifest)
    exclusions = load_exclusions(manifest)
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

        since_checkpoint += 1
        try:
            body = _urlopen(document.source, timeout=120, accept="application/pdf")
            pinned = pin_or_verify(document, body)
        except (
            urllib.error.URLError,
            TimeoutError,
            PinMismatchError,
            ValueError,
            http.client.IncompleteRead,
            http.client.HTTPException,
        ) as exc:
            print(f"  failed {document.id}: {exc}", file=sys.stderr)
            failed += 1
            updated.append(document)
        else:
            target.write_bytes(body)
            updated.append(pinned)
            fetched += 1

        if args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

        if since_checkpoint >= _MANIFEST_CHECKPOINT:
            write_manifest(
                manifest,
                tuple(updated) + tuple(documents[len(updated) :]),
                query=query,
                excluded=exclusions,
            )
            since_checkpoint = 0

    write_manifest(manifest, tuple(updated), query=query, excluded=exclusions)
    print(f"fetched {fetched}, already present {present}, failed {failed}")
    return 1 if failed > 0 else 0


# --- exclude ----------------------------------------------------------------------------------


def cmd_exclude(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    documents = load_manifest(manifest)
    query = _manifest_query(manifest)
    existing = load_exclusions(manifest)
    new = Exclusion(id=args.id, reason=args.reason)

    kept = exclude_documents(documents, (new,))
    write_manifest(manifest, kept, query=query, excluded=(*existing, new))
    print(f"excluded {new.id} ({new.reason}); {len(kept)} documents remain")
    return 0


# --- sketch ------------------------------------------------------------------------------------


def _chunk_target(value: str) -> int | None:
    if value == "all":
        return None
    try:
        target = int(value)
    except ValueError as exc:
        message = f"{value!r} is not a chunk count or 'all'"
        raise argparse.ArgumentTypeError(message) from exc
    if target <= 0:
        message = f"{value!r} is not a positive chunk count"
        raise argparse.ArgumentTypeError(message)
    return target


def _stage_papers(ids: Sequence[str], pdfs_dir: Path, staged: Path) -> None:
    for identifier in ids:
        if not (pdfs_dir / f"{identifier}.pdf").exists():
            message = f"{identifier}'s PDF is missing from {pdfs_dir}"
            raise FileNotFoundError(message)
    staged.mkdir(parents=True, exist_ok=True)
    # A link left by an earlier run would index a paper no longer chosen.
    for stale in staged.glob("*.pdf"):
        stale.unlink()
    for identifier in ids:
        (staged / f"{identifier}.pdf").symlink_to(pdfs_dir / f"{identifier}.pdf")


def cmd_sketch(args: argparse.Namespace) -> int:
    admin_dsn = _require_admin_dsn(args.admin_dsn)
    documents = load_manifest(Path(args.manifest))
    pdfs_dir = Path(args.pdfs).resolve()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    model = model_named(args.model)

    staged = work / "sketch-staged"
    _stage_papers([document.id for document in documents], pdfs_dir, staged)

    full_digest = input_digest(document.sha256 for document in documents if document.sha256)
    db_name = f"weft_bench_sketch_{full_digest[:12]}"
    dsn = _fresh_database(admin_dsn, db_name)

    try:
        env = os.environ.copy()
        env["WEFT_DATABASE_URL"] = dsn
        result = _run_weft(
            ["index", str(staged), "--pipeline", "index-pdf-text"], cwd=work, env=env
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

            cur.execute("SELECT id, s FROM weft_nodes, unnest(sources) AS s")
            pair_rows = cur.fetchall()

            pairs = tuple((str(node_id), Path(str(source)).stem) for node_id, source in pair_rows)
            sources_by_stem: dict[str, str] = {
                Path(str(source)).stem: str(source) for _node_id, source in pair_rows
            }
            counts = chunks_per_paper(pairs)

            if args.target is None:
                for document in documents:
                    if counts.get(document.id, 0) == 0:
                        message = (
                            f"{document.id} produced no chunks, so a set of all papers "
                            "cannot include it"
                        )
                        raise InsufficientCorpusError(message)
                chosen = tuple(document.id for document in documents)
            else:
                chosen = distinct_prefix(
                    pairs, [document.id for document in documents], target=args.target
                )
            chosen_set = frozenset(chosen)

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
        chosen_chunks = distinct_chunks(pairs, chosen_set)

        papers_by_node: dict[str, set[str]] = {}
        for node_id, paper in frozenset(pairs):
            papers_by_node.setdefault(node_id, set()).add(paper)
        shared_nodes = sum(1 for papers in papers_by_node.values() if len(papers) >= 2)
        print(f"shared nodes: {shared_nodes}")

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

#: `weft_sources.status`, rendered lowercase by `::text` — read 2026-09-15 from a partial embed:
#: every source is `indexing` before a run and `active` only once it finishes.
_ACTIVE_STATUS: Final[str] = "active"


def next_slice(chosen: Sequence[str], done: frozenset[str], *, size: int) -> tuple[str, ...]:
    if size < 1:
        message = f"size must be at least 1, got {size}"
        raise ValueError(message)
    remaining = (identifier for identifier in chosen if identifier not in done)
    return tuple(itertools.islice(remaining, size))


def active_papers(rows: Iterable[tuple[str | None, str | None]]) -> frozenset[str]:
    return frozenset(
        PurePosixPath(row_id).stem
        for row_id, status in rows
        if row_id is not None and status == _ACTIVE_STATUS
    )


def _read_done_papers(dsn: str) -> frozenset[str]:
    """The active papers `weft_sources` already holds. Autocommit, and closed before the caller
    runs `weft`: an open connection blocks weft's lazy schema DDL (`L22.30`)."""
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('weft_sources')")
        row = cur.fetchone()
        if row is None or row[0] is None:
            return frozenset()
        cur.execute("SELECT id, status::text FROM weft_sources")
        rows = cur.fetchall()
    return active_papers(rows)


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

    slice_number = 0
    while True:
        done = _read_done_papers(dsn)
        current = next_slice(sketch.chosen_ids, done, size=args.batch_size)
        if not current:
            break
        slice_number += 1
        _stage_papers(current, pdfs_dir, work / "staged")
        result = _run_weft(
            ["index", "staged", "--pipeline", "bench-embed", "--batch-size", str(len(current))],
            cwd=work,
            env=env,
        )
        print(
            f"slice {slice_number}: {len(current)} papers, "
            f"{len(done) + len(current)} of {len(sketch.chosen_ids)} done"
        )
        for line in result.stdout.splitlines():
            if "documents:" in line or "batch" in line:
                print(line)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            message = (
                f"embed failed on the slice {current[0]}..{current[-1]} "
                f"(exit code {result.returncode}). Database {db_name} was kept, so re-running "
                "the same `embed` command resumes."
            )
            raise ValueError(message)
        # Without this a slice weft left unmarked would be chosen, and paid for, again forever.
        stuck = sorted(frozenset(current) - _read_done_papers(dsn))
        if stuck:
            message = (
                f"weft index exited 0 but left {len(stuck)} paper(s) of slice {slice_number} not "
                f"active: {', '.join(stuck[:5])}. Stopped rather than re-paying that slice; "
                f"database {db_name} was kept."
            )
            raise ValueError(message)

    done = _read_done_papers(dsn)
    missing = frozenset(sketch.chosen_ids) - done
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM weft_nodes")
        row = cur.fetchone()
        node_count = 0 if row is None else int(row[0])
    if missing or node_count != sketch.chunks:
        message = (
            f"{len(done)} of {len(sketch.chosen_ids)} chosen papers are active, weft_nodes "
            f"holds {node_count} nodes, the sketch chose {sketch.chunks} chunks — these must "
            f"all agree before spending is trusted. Database {db_name} was kept for inspection."
        )
        raise ValueError(message)

    with psycopg.connect(dsn) as conn:
        nodes_table, vectors = _dump_nodes_with_vectors(
            conn, "weft_nodes", expected_rows=node_count
        )
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
            # Named, not CASCADE: a table added later that references weft_nodes must refuse
            # here rather than be emptied without anyone deciding it should be.
            cur.execute("TRUNCATE weft_node_productions, weft_nodes, weft_sources")
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM weft_nodes")
            before_nodes_row = cur.fetchone()
            cur.execute("SELECT count(*) FROM weft_sources")
            before_sources_row = cur.fetchone()
            cur.execute("SELECT count(*) FROM weft_node_productions")
            before_productions_row = cur.fetchone()
        before_nodes = 0 if before_nodes_row is None else int(before_nodes_row[0])
        before_sources = 0 if before_sources_row is None else int(before_sources_row[0])
        before_productions = 0 if before_productions_row is None else int(before_productions_row[0])
        if before_nodes != 0 or before_sources != 0 or before_productions != 0:
            message = (
                f"expected an empty database after TRUNCATE, found {before_nodes} nodes, "
                f"{before_sources} sources and {before_productions} productions"
            )
            raise ValueError(message)

        with conn.cursor() as cur:
            # Provisioning committed the column to the `hash` embedder's width (64); the table is
            # empty post-TRUNCATE, so retyping to the set's own width is a metadata-only rewrite.
            cur.execute(
                sql.SQL("ALTER TABLE weft_nodes ALTER COLUMN embedding TYPE vector({n})").format(
                    n=sql.Literal(vector_set.meta.width)
                )
            )
        conn.commit()

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


# --- subset -----------------------------------------------------------------------------------


def cmd_subset(args: argparse.Namespace) -> int:
    documents = load_manifest(Path(args.manifest))
    written = subset_vector_set(
        Path(args.set_dir),
        Path(args.out),
        documents=documents,
        target=args.target,
        day=date.today(),
    )
    print(f"subset: {Path(args.out) / written.meta.name}")
    print(f"rows: {written.meta.rows:,}")
    print(f"papers: {written.meta.pdfs}")
    print(f"derived from: {written.meta.derived_from}")
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
    select.add_argument(
        "--source",
        choices=[member.value for member in CorpusSource],
        default=CorpusSource.OPEN_RAGBENCH.value,
        type=CorpusSource,
    )
    select.add_argument("--start-after", default="PMC11000000")
    select.add_argument("--count", type=int, default=1100)
    select.set_defaults(func=cmd_select)

    fetch = subparsers.add_parser("fetch", help="download and pin the selected PDFs")
    fetch.add_argument("--manifest", type=Path, required=True)
    fetch.add_argument("--dest", type=Path, required=True)
    fetch.add_argument("--delay-seconds", type=float, default=0.0)
    fetch.set_defaults(func=cmd_fetch)

    exclude = subparsers.add_parser("exclude", help="drop a paper from the set, by id")
    exclude.add_argument("--manifest", type=Path, required=True)
    exclude.add_argument("--id", required=True)
    exclude.add_argument("--reason", required=True)
    exclude.set_defaults(func=cmd_exclude)

    sketch = subparsers.add_parser("sketch", help="index once for free and price the target")
    sketch.add_argument("--manifest", type=Path, required=True)
    sketch.add_argument("--pdfs", type=Path, required=True)
    sketch.add_argument("--work", type=Path, required=True)
    sketch.add_argument(
        "--target",
        type=_chunk_target,
        default=100_000,
        help="a chunk count, or `all` for every manifest paper",
    )
    sketch.add_argument("--model", default=EmbeddingModel.LARGE.value)
    _add_admin_dsn(sketch)
    sketch.set_defaults(func=cmd_sketch)

    embed = subparsers.add_parser("embed", help="spend the sketch's price and write the vector set")
    embed.add_argument("--work", type=Path, required=True)
    embed.add_argument("--pdfs", type=Path, required=True)
    embed.add_argument("--out", type=Path, required=True)
    embed.add_argument("--yes", action="store_true")
    embed.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="papers per weft index run; each run marks its own slice active, so a killed run "
        "re-pays only that slice",
    )
    _add_admin_dsn(embed)
    embed.set_defaults(func=cmd_embed)

    load = subparsers.add_parser("load", help="reload a vector set with no API call")
    load.add_argument("--set", dest="set_dir", type=Path, required=True)
    load.add_argument("--database", required=True)
    load.add_argument("--rows", type=int, default=None)
    _add_admin_dsn(load)
    load.set_defaults(func=cmd_load)

    subset = subparsers.add_parser(
        "subset", help="cut a vector set down to a manifest-order prefix of whole papers"
    )
    subset.add_argument("--set", dest="set_dir", type=Path, required=True)
    subset.add_argument("--manifest", type=Path, required=True)
    subset.add_argument("--out", type=Path, required=True)
    subset.add_argument("--target", type=int, default=100_000)
    subset.set_defaults(func=cmd_subset)

    return parser


def main(argv: list[str] | None = None) -> int:
    bench_latency.line_buffer_stdout()
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
        http.client.HTTPException,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
