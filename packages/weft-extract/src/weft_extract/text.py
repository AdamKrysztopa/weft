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
is the fix for the accept-then-fail bug." `discover_source_docs` is what
actually reads it; a future dispatcher choosing an extractor by file
extension would read it too, rather than a second, hand-maintained list.
"""

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
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


def discover_source_docs(directory: Path) -> tuple[SourceDoc, ...]:
    """Every `.txt`/`.md` file under `directory`, read into a `SourceDoc`.

    Recurses. `source_id` is the file's resolved path — stable across runs
    from the same checkout, which is what makes re-indexing an unchanged
    directory produce the same `Node` ids (`docs/02-extension-model.md` →
    *Identity is a content-addressed digest*). Files are read and returned in
    sorted-path order, so two runs over the same directory build the same
    batch in the same order.
    """
    paths = sorted(
        path for path in directory.rglob("*") if path.is_file() and path.suffix in EXTENSIONS
    )
    return tuple(
        SourceDoc(
            source_id=SourceId(str(path.resolve())),
            uri=path.resolve().as_uri(),
            content=path.read_bytes(),
        )
        for path in paths
    )
