"""`TextExtractor` — the built-in extractor over a directory of `.txt` and `.md` files.

Specified in `docs/06-phase-0-build.md` step 8: "a text extractor over a
directory of `.txt` and `.md` files." Two responsibilities, deliberately
kept separate: `discover_source_docs` turns a directory on disk into
`SourceDoc`s — nothing in `Extractor` (`contract.py`) takes a path, so
something has to read the filesystem before extraction can even start — and
`TextExtractor.run` is the actual `Extractor` plugin, which only ever sees
the `SourceDoc`s it is handed and decodes their bytes as UTF-8. Splitting
them is what keeps the contract itself filesystem-free: a future extractor
reading from an object store, a database or a zip archive satisfies the same
`Extractor` Protocol without this module's directory-walking becoming part
of what a plugin must implement.

`EXTENSIONS` is capability metadata, per `docs/02-extension-model.md` section
1 — "a capability declares its own metadata... this is not decoration — it
is the fix for the accept-then-fail bug." It is *this extractor's* claim and
nothing wider: `weft_extract.accept.claimed_extensions` reads it off this
class the same way it reads every other registered extractor's, and it is
their union — never this constant alone — that decides what ingest accepts.
`discover_source_docs` takes that union as an argument for exactly that
reason.
"""

import hashlib
from collections.abc import Collection, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import (
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
)

#: The two suffixes this built-in extractor claims — `06` step 8's exact scope.
EXTENSIONS: tuple[str, ...] = (".txt", ".md")


class TextExtractorConfig(BaseModel):
    """`TextExtractor` takes no configuration — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class TextExtractor:
    """Decodes each `SourceDoc`'s bytes as UTF-8 and builds one root `Node` per document.

    Satisfies `weft_extract.contract.Extractor` structurally — this class
    never imports it, the same path any third-party extractor pack takes.
    Every produced node is built through `Node.synthetic`: extraction has no
    upstream `Node`, only a source document, so `sources` is authored
    directly here and nowhere else in the ingest path (`docs/02-extension-model.md`
    → *The one exception is a root*).
    """

    extensions: tuple[str, ...] = EXTENSIONS

    def __init__(self, config: TextExtractorConfig | None = None) -> None:
        del config  # nothing to configure — see TextExtractorConfig

    async def run(self, payload: Sequence[SourceDoc], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no source documents to extract")

        nodes: list[Node] = []
        for doc in payload:
            try:
                text = doc.content.decode("utf-8")
            except UnicodeDecodeError as exc:
                return Failed(reason=f"'{doc.uri}' is not valid UTF-8: {exc}")
            nodes.append(
                Node.synthetic(
                    content=text,
                    media_type=MediaType.TEXT,
                    reason=f"extracted from '{doc.uri}'",
                    sources=frozenset({doc.source_id}),
                )
            )
        return Produced(value=nodes)


def discover_source_docs(directory: Path, *, extensions: Collection[str]) -> tuple[SourceDoc, ...]:
    """Every file under `directory` whose suffix is in `extensions`, read into a `SourceDoc`.

    Recurses. `source_id` is the file's **resolved path**, which is what makes re-indexing an
    unchanged directory produce the same `Node` ids (`docs/02-extension-model.md` →
    *Identity is a content-addressed digest*) — and what makes it a fact about this machine's
    filesystem rather than about the document. It is stable across runs from the same
    checkout and across nothing wider than that: it moves when a file is renamed and stands
    still when the bytes under it change. A caller needing an identity a corpus carries with
    it hashes `SourceDoc.content` instead, as `weft_cli.ingest.content_hashes_of` does for a
    run record's corpus digest (ledger 16.0). Files are read and returned in sorted-path
    order, so two runs over the same directory build the same batch in the same order.

    **`extensions` is required, and that is a repair.** This used to read
    `EXTENSIONS` — *this* module's constant — which meant a directory walk in
    a shared helper silently decided that ingest accepts what one pack claims.
    A second extractor pack made `.pdf` invisible to `weft index` with no
    error anywhere. The accept set now arrives from the caller, derived from
    the registry by `weft_extract.accept.claimed_extensions`, and there is no
    default here for it to fall back to.
    """
    paths = sorted(
        path for path in directory.rglob("*") if path.is_file() and path.suffix in extensions
    )
    return tuple(
        SourceDoc(
            source_id=SourceId(str(path.resolve())),
            uri=path.resolve().as_uri(),
            content=path.read_bytes(),
        )
        for path in paths
    )


class SourceRef(BaseModel):
    """A source document's identity and content hash — never its bytes. Ledger task **43.1**.

    `discover_source_docs` measured 3.45 GB resident before the first batch of a 1,000-PDF
    corpus, because it reads every file's bytes into one `SourceDoc` tuple before indexing
    starts anything. `SourceRef` is what a directory walk hands back instead: `source_id` and
    `uri` are the identical values `discover_source_docs` derives from the same resolved
    `path`, so the two walks agree on identity, and `size`/`content_hash` are enough for
    change detection and for `load_source_docs`' own check — everything `weft_cli.ingest`
    needs before a batch is actually loaded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: SourceId
    uri: str
    path: Path
    size: int
    content_hash: str


#: `_stream_hash`'s own chunk size — task **43.1**. Fixed regardless of file size, which is the
#: whole point: resident memory for one file's hash is bounded by this constant, never by that
#: file's own length.
_HASH_CHUNK_BYTES: int = 1 << 20


def _stream_hash(path: Path) -> str:
    """sha256 of `path`'s bytes, read in `_HASH_CHUNK_BYTES` chunks — never the whole file at
    once, which is `inventory_source_refs`' whole reason to exist.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_source_refs(directory: Path, *, extensions: Collection[str]) -> tuple[SourceRef, ...]:
    """Every file under `directory` an extension in `extensions` claims, as a `SourceRef` —
    the same walk and sorted order `discover_source_docs` uses, holding no file's bytes.

    Ledger task **43.1**. Resident memory before the first batch is now bounded by one file's
    hashing buffer, not by the corpus: `discover_source_docs` read every claimed file into one
    tuple before indexing could start anything, which is the 3.45 GB `43.0` measured. Each
    file is stream-hashed by `_stream_hash` and never held whole.
    """
    paths = sorted(
        path for path in directory.rglob("*") if path.is_file() and path.suffix in extensions
    )
    return tuple(
        SourceRef(
            source_id=SourceId(str(path.resolve())),
            uri=path.resolve().as_uri(),
            path=path.resolve(),
            size=path.stat().st_size,
            content_hash=_stream_hash(path),
        )
        for path in paths
    )


class SourceChangedDuringIndexError(WeftError):
    """A file named by a `SourceRef` no longer matches the hash its inventory took, or is gone.

    Ledger task **43.1**. `inventory_source_refs` and `load_source_docs` run at different
    points of a possibly long batched run — a large corpus takes long enough for a file to be
    edited or removed underneath it — so a batch's load re-hashes each file before trusting it
    and refuses by name rather than silently indexing bytes under a stale identity: the record
    `weft_cli.ingest` writes for a source is keyed on the hash its inventory took, and writing
    it against different bytes would make that record a claim about content nobody checked.
    The next run over the same directory sees the file as changed and indexes it fresh.
    """


def load_source_docs(refs: Sequence[SourceRef]) -> tuple[SourceDoc, ...]:
    """`refs`, read into `SourceDoc`s, in the order given — one batch's worth of bytes.

    Ledger task **43.1**. Re-hashes each file and raises `SourceChangedDuringIndexError`,
    naming the file's `uri`, when the file is gone or its bytes no longer match the hash
    `inventory_source_refs` took for it — the inventory and the load are two different points
    in time, and a batched run may span long enough for a file to move between them.
    """
    docs: list[SourceDoc] = []
    for ref in refs:
        if not ref.path.is_file():
            raise SourceChangedDuringIndexError(
                f"'{ref.uri}' changed since this run's inventory: it is no longer on disk. "
                "Indexing was refused rather than recording it under a stale identity — the "
                "next run over this directory will see it as changed."
            )
        content = ref.path.read_bytes()
        if hashlib.sha256(content).hexdigest() != ref.content_hash:
            raise SourceChangedDuringIndexError(
                f"'{ref.uri}' changed since this run's inventory: its bytes no longer match "
                "the hash taken at the start of this run. Indexing was refused rather than "
                "recording it under a stale identity — the next run over this directory will "
                "see it as changed."
            )
        docs.append(SourceDoc(source_id=ref.source_id, uri=ref.uri, content=content))
    return tuple(docs)
