"""Generates the latency corpus for Phase 29 task **29.0**.

Unlike `fetch_corpus.py`'s manifest of real documents, this corpus is generated: plain-text
documents built from a deterministic word stream so the chunk count `generate` reports is a fact
about `index-text`'s real extractor, cleaners and `fixed-size {size: 512, overlap: 50}` chunker,
not an assertion in a document. It serves *latency only* — hash vectors are not distributed like a
trained model's, so recall measured against this corpus would not transfer. Recall comes from the
29.6 vector set instead.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

#: `docs/02-extension-model.md` §3's own pipeline example: `{size: 512, overlap: 50}` — this
#: corpus is sized against those defaults so its printed count matches the shipped pipeline.
_DEFAULT_SIZE = 512
_DEFAULT_OVERLAP = 50

#: A document of `k * (size - overlap)` characters yields exactly `k` windows under
#: `weft_chunk.fixed_size`'s rule; every document but the last is sized for this many.
_CHUNKS_PER_DOCUMENT = 20


class GeneratedCorpus(BaseModel):
    """What `generate` wrote: where, how much, and the digest that makes it reproducible."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    directory: Path
    documents: int
    chunks: int
    size: int
    overlap: int
    seed: int
    digest: str


def _hash_bytes(*parts: object) -> bytes:
    joined = ":".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode("ascii")).digest()


def _word(seed: int, doc_index: int, word_index: int) -> str:
    digest = _hash_bytes(seed, doc_index, word_index)
    length = 3 + digest[0] % 6
    return "".join(chr(97 + digest[1 + i] % 26) for i in range(length))


def _fill_letter(seed: int, doc_index: int) -> str:
    digest = _hash_bytes(seed, doc_index, "fill")
    return chr(97 + digest[0] % 26)


def _document_text(seed: int, doc_index: int, length: int) -> str:
    """`length` characters of ASCII lowercase words separated by single spaces.

    Built word by word until the joined text reaches `length`, then cut to exactly that many
    characters. A cut that lands on the separating space is replaced with a letter rather than
    dropped, so the result is never shorter than `length` and never ends in whitespace.
    """
    words: list[str] = []
    joined_length = 0
    word_index = 0
    while joined_length < length:
        word = _word(seed, doc_index, word_index)
        word_index += 1
        joined_length += len(word) if not words else len(word) + 1
        words.append(word)
    text = " ".join(words)[:length]
    if text.endswith(" "):
        text = text[:-1] + _fill_letter(seed, doc_index)
    return text


def generate(
    out: Path,
    *,
    chunks: int,
    seed: int = 0,
    size: int = _DEFAULT_SIZE,
    overlap: int = _DEFAULT_OVERLAP,
) -> GeneratedCorpus:
    """Write a generated corpus of `chunks` chunks (under the shipped ingest stages) into `out`."""
    if chunks < 1:
        raise ValueError(f"chunks must be at least 1 (got {chunks})")
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(
            f"{out} already holds files; a corpus is written into an empty directory so "
            "nothing else is mixed into it"
        )
    out.mkdir(parents=True, exist_ok=True)

    step = size - overlap
    full_documents = (chunks - 1) // _CHUNKS_PER_DOCUMENT
    last_document_chunks = chunks - full_documents * _CHUNKS_PER_DOCUMENT
    targets = [_CHUNKS_PER_DOCUMENT] * full_documents + [last_document_chunks]

    for index, target in enumerate(targets, start=1):
        text = _document_text(seed, index, target * step)
        (out / f"doc-{index:06d}.txt").write_text(text, encoding="utf-8")

    hasher = hashlib.sha256()
    for path in sorted(out.iterdir(), key=lambda p: p.name):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())

    return GeneratedCorpus(
        directory=out,
        documents=len(targets),
        chunks=chunks,
        size=size,
        overlap=overlap,
        seed=seed,
        digest=hasher.hexdigest(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    arguments = parser.parse_args(argv)

    try:
        corpus = generate(arguments.out, chunks=arguments.chunks, seed=arguments.seed)
    except (ValueError, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(
        f"generated {corpus.chunks:,} chunks ({corpus.documents:,} documents, "
        f"size {corpus.size}, overlap {corpus.overlap})"
    )
    print(f"corpus digest: {corpus.digest}")
    print(
        "serves latency only: hash vectors are not distributed like a model's, so recall "
        "measured on this corpus does not transfer"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
