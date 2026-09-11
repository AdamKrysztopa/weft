"""G17's whole measurement, in one run — `docs/internal/05-grilling-sessions.md` → G17.

**Re-run this rather than quoting its output.** That section's own *Bring* says the measurement is
re-taken rather than carried forward, and the reason is on the record: the first probe this question
ever had measured drift at the *end of the document*, where the page error is 0 on all nine papers,
and that reading would have shipped the wrong repair (`docs/internal/lessons.md` `L11.3`).

Three things are printed, and they answer different questions:

1. **How wrong is a page carried verbatim?** — probed at every page boundary (a step function's
   error is maximal at its steps) *and* at every chunk offset the chunker actually produces,
   which is what a reader hits, since nobody follows a citation to a page boundary.
2. **Where does `PdfPages` actually die?** — the ladder run rung by rung, printing which `ext`
   namespaces survive each one, with `page_for` asked at the end and again with no cleaners at
   all as the counterfactual.
3. **What does position 5 cost?** — one root node per page means the chunker runs per page, so
   chunks stop spanning page breaks. The price is a chunk count and a tail-window count.

**Why this calls the cleaners' private `_normalize` rather than their `run()`.** Every contract
method in Weft is `async def` (G6), and fitness function 7(a) permits `asyncio.run` **exactly
once in the whole repository**, at `weft_cli.cli` — a walk that covers `scripts/`. So a hand-run
measurement is synchronous or it is a second colour bridge, and `eval/run_baseline.py` reached
the same fork and answered it the same way: do the pure part in-process, shell out for anything
that must be a process. The part measured here *is* pure — cleaning and chunking are string
transformations over already-extracted text, no I/O — and each cleaner's `run()` is one line over
the helper this calls (`[node.derive(content=_normalize(node.content)) for node in payload]`),
which `_assert_the_wrapper_is_one_line` below checks against the source rather than asserting in
prose. The chunker's window arithmetic is reproduced here for the same reason and checked the
same way.

`_private` takes the attribute name as a **parameter**, which is what keeps `pyright`'s
`reportPrivateUsage` and `ruff`'s `B009` both satisfied — the same idiom the test suite uses.

The corpus is `corpus/mrmr/` — reading material, deliberately untracked; `corpus/manifest.toml`
names what belongs there. Absent, this exits saying so rather than reporting zero.
"""

from __future__ import annotations

import ast
import difflib
from bisect import bisect_right
from collections.abc import Callable, Sequence
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import cast

from pypdf import PdfReader

from weft_chunk import fixed_size
from weft_clean import unicode_normalizer, whitespace
from weft_generate.page import page_for
from weft_kernel.payload import MediaType, Node, SourceId
from weft_pdf.document import PdfPages

#: `index-text`'s own separator and chunker settings, so this measures that document's ladder
#: and not a plausible-looking one. Change either and the numbers stop being about the tree.
SEPARATOR = "\n\n"
SIZE = 512
OVERLAP = 50
STEP = SIZE - OVERLAP

CORPUS = Path("corpus/mrmr")


def _private(module: ModuleType, name: str) -> object:
    """`module`'s private `name`, fetched with the name as a **parameter**.

    That is the whole trick, and it is the tree's own idiom: a literal attribute access trips
    `pyright`'s `reportPrivateUsage`, and a literal `getattr` trips `ruff`'s `B009`. Passing the
    name through a variable satisfies both while leaving the reach entirely visible at the call
    site, which is the point — this is a deliberate reach into a module's inside, and it should
    read like one.
    """
    return getattr(module, name)


def _normalizer(module: ModuleType) -> Callable[[str], str]:
    """One cleaner module's `_normalize`, typed as the string transformation it is."""
    return cast("Callable[[str], str]", _private(module, "_normalize"))


def _windows_of(node: Node) -> Sequence[Node]:
    """`FixedSizeChunker._windows` over `node`, at `index-text`'s own size and overlap."""
    windows = cast("Callable[..., Sequence[Node]]", _private(fixed_size, "_windows"))
    return windows(node, size=SIZE, overlap=OVERLAP)


_UNICODE_NORMALIZE = _normalizer(unicode_normalizer)
_WHITESPACE_NORMALIZE = _normalizer(whitespace)


def _module_source(module: ModuleType) -> str:
    """`module`'s own source text, read off the file it was imported from."""
    path = getattr(module, "__file__", None)
    if path is None:
        raise SystemExit(f"{module.__name__} has no source file to read")
    return Path(path).read_text(encoding="utf-8")


def _assert_the_wrapper_is_one_line() -> None:
    """Check, against the source, that each cleaner's `run()` is the helper this file calls.

    The module docstring claims the measurement is unaffected by calling `_normalize` instead of
    `Cleaner.run`. That is a claim about code, so it is checked against the code rather than
    asserted in prose: every `run()` must call `_normalize` and nothing else that could
    transform content. If a cleaner grows a second step, this fails here rather than quietly
    making every number below a measurement of a ladder that no longer runs.
    """
    for module, cls_name in (
        (unicode_normalizer, "UnicodeNormalizer"),
        (whitespace, "WhitespaceNormalizer"),
    ):
        tree = ast.parse(_module_source(module))
        run = next(
            (
                inner
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef) and node.name == cls_name
                for inner in node.body
                if isinstance(inner, ast.AsyncFunctionDef) and inner.name == "run"
            ),
            None,
        )
        if run is None:
            raise SystemExit(f"{module.__name__}.{cls_name} has no async run() to check")
        called = {
            node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(run)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute)
        }
        #: `Produced` and `NothingToProduce` are outcome constructors and `derive` rebuilds the
        #: node around text `_normalize` already produced — none of the three can change content.
        #: Anything else appearing here is a second transformation, and the point of the check.
        unexpected = called - {"_normalize", "derive", "Produced", "NothingToProduce"}
        if "_normalize" not in called or unexpected:
            raise SystemExit(
                f"{cls_name}.run is no longer one line over _normalize — it also calls "
                f"{sorted(unexpected)}. This script's numbers would be about a ladder that no "
                f"longer runs; fix the script before trusting them."
            )

    windows_source = _module_source(fixed_size)
    if "start += step" not in windows_source or "step = size - overlap" not in windows_source:
        raise SystemExit(
            "FixedSizeChunker._windows no longer advances by size - overlap; this script's "
            "chunk offsets are arithmetic about that loop and would now be wrong."
        )


def _extracted(pdf: Path) -> tuple[list[str], Node]:
    """Each page's text, and the one root `Node` `weft_pdf.extract_documents` would build.

    Built the way that function builds it — `Node.synthetic` plus `PdfPages` over the joined
    content — rather than by calling it, because the extractor wants a `SourceDoc` and a
    registry and this question has nothing to do with either. **That one root node per document
    is the premise position 5 attacks**, and it is visible right here: the page becomes an
    offset table because the pages became one string.
    """
    reader = PdfReader(BytesIO(pdf.read_bytes()))
    texts = [page.extract_text() or "" for page in reader.pages]
    starts: list[int] = []
    offset = 0
    for text in texts:
        starts.append(offset)
        offset += len(text) + len(SEPARATOR)
    root = Node.synthetic(
        content=SEPARATOR.join(texts),
        media_type=MediaType.TEXT,
        reason=f"extracted from '{pdf.name}' by pdf-text",
        sources=frozenset({SourceId(str(pdf))}),
    ).with_ext(PdfPages(backend="pdf-text", starts=tuple(starts)))
    return texts, root


def _cleaned(text: str) -> str:
    """`text` through the two cleaners `index-text` names, in the order it names them."""
    return _WHITESPACE_NORMALIZE(_UNICODE_NORMALIZE(text))


def _chunk_offsets(text: str) -> range:
    """Every `ChunkOffset.start` `FixedSizeChunker` would attach to `text`'s windows."""
    return range(0, len(text), STEP)


def _map_offsets(original: str, cleaned: str, points: Sequence[int]) -> list[int]:
    """Where each offset in `original` really ended up in `cleaned`.

    A real alignment, never a length-of-prefix estimate — the estimate is itself a claim about
    how cleaning composes, and that claim is the thing under test.
    """
    matcher = difflib.SequenceMatcher(None, original, cleaned, autojunk=False)
    blocks = matcher.get_matching_blocks()
    out: list[int] = []
    for point in points:
        mapped = 0
        for block in blocks:
            if block.a <= point < block.a + block.size:
                mapped = block.b + (point - block.a)
                break
            if block.a > point:
                mapped = block.b
                break
            mapped = block.b + block.size
        out.append(mapped)
    return out


def _papers() -> list[Path]:
    if not CORPUS.is_dir():
        raise SystemExit(
            f"'{CORPUS}' is not present. It is reading material and deliberately untracked — "
            f"'corpus/manifest.toml' names what belongs there. Nothing was measured."
        )
    found = sorted(CORPUS.glob("*.pdf"))
    if not found:
        raise SystemExit(f"'{CORPUS}' holds no PDFs. Nothing was measured.")
    return found


def _starts_of(root: Node) -> tuple[int, ...]:
    pages = root.ext_as(PdfPages)
    if pages is None:
        raise RuntimeError("the extracted root carries no PdfPages")
    return pages.starts


def _page_error() -> None:
    print("1. HOW WRONG IS A PAGE CARRIED VERBATIM?\n")
    boundaries_wrong = boundaries_total = chunks_wrong = chunks_total = worst = 0
    for pdf in _papers():
        _pages, root = _extracted(pdf)
        cleaned = _cleaned(root.content)
        starts = _starts_of(root)
        true_starts = _map_offsets(root.content, cleaned, starts)

        bad_boundaries = 0
        for true_start in true_starts:
            probe = true_start + 1
            said, truth = bisect_right(starts, probe), bisect_right(true_starts, probe)
            bad_boundaries += said != truth
            worst = max(worst, abs(said - truth))

        offsets = _chunk_offsets(cleaned)
        bad_chunks = 0
        for offset in offsets:
            said, truth = bisect_right(starts, offset), bisect_right(true_starts, offset)
            bad_chunks += said != truth
            worst = max(worst, abs(said - truth))

        boundaries_wrong += bad_boundaries
        boundaries_total += len(starts)
        chunks_wrong += bad_chunks
        chunks_total += len(offsets)
        drift = (len(root.content) - len(cleaned)) / len(root.content) * 100
        print(
            f"   {pdf.name[:38]:<40} pages={len(starts):>3} boundaries wrong="
            f"{bad_boundaries:>3}/{len(starts):<3} chunks wrong={bad_chunks:>4}/"
            f"{len(offsets):<4} ({bad_chunks / len(offsets) * 100:5.1f}%) drift={drift:+.2f}%",
            flush=True,
        )
    print()
    print(f"   WORST PAGE ERROR: {worst} pages")
    print(f"   page boundaries misplaced: {boundaries_wrong}/{boundaries_total}")
    print(
        f"   CHUNKS CARRYING THE WRONG PAGE: {chunks_wrong}/{chunks_total} "
        f"({chunks_wrong / chunks_total * 100:.1f}%)"
    )


def _survival() -> None:
    """Which rung drops `PdfPages` — run one cleaner at a time, because the finding is *which*.

    A probe that ran both at once could not tell a gradual loss from an immediate one, and the
    answer turns out to be immediate.
    """
    print("\n2. WHERE DOES PdfPages ACTUALLY DIE?\n")
    pdf = _papers()[0]
    _pages, root = _extracted(pdf)
    print(f"   {pdf.name[:60]}")
    print(f"   after extract:           ext = {sorted(root.ext)}")
    after_uni = root.derive(content=_UNICODE_NORMALIZE(root.content))
    print(f"   after unicode-normalize: ext = {sorted(after_uni.ext)}")
    after_ws = after_uni.derive(content=_WHITESPACE_NORMALIZE(after_uni.content))
    print(f"   after whitespace:        ext = {sorted(after_ws.ext)}")

    chunks = _windows_of(after_ws)
    print(f"   after chunk ({len(chunks):>3} chunks):  ext = {sorted(chunks[0].ext)}")
    print()
    print(f"   page_for(first chunk)              = {page_for(chunks[0])}")
    print(f"   page_for(first chunk, no cleaners) = {page_for(_windows_of(root)[0])}")


def _position_five_price() -> None:
    print("\n3. WHAT DOES POSITION 5 COST?\n")
    per_document = per_page = short_tails = 0
    for pdf in _papers():
        pages, root = _extracted(pdf)
        per_document += len(_chunk_offsets(_cleaned(root.content)))
        for text in pages:
            cleaned_page = _cleaned(text)
            if not cleaned_page:
                continue
            offsets = _chunk_offsets(cleaned_page)
            per_page += len(offsets)
            if len(cleaned_page) - offsets[-1] < SIZE // 2:
                short_tails += 1
    print(f"   chunks today (one root node per document): {per_document}")
    print(
        f"   chunks with one root node per page:        {per_page}  "
        f"({(per_page / per_document - 1) * 100:+.1f}%)"
    )
    print(f"   pages whose tail chunk is under half a window: {short_tails}")


def main() -> None:
    _assert_the_wrapper_is_one_line()
    _page_error()
    _survival()
    _position_five_price()


if __name__ == "__main__":
    main()
