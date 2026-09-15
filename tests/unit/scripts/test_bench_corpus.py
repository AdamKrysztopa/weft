"""Unit tests for `scripts/bench_corpus.py` — Phase 29 task **29.0**.

The corpus serves *latency* only (`fix-plans/05` 29.0 as amended by `07`). What this file holds the
script to is that its chunk count is a fact about the shipped ingest stages rather than about the
script's own arithmetic: the count it prints is compared against what `index-text`'s real
extractor, cleaners and chunker produce from the files it wrote.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import bench_corpus
import pytest

from weft_chunk.fixed_size import FixedSizeChunker, FixedSizeChunkerConfig
from weft_clean.unicode_normalizer import UnicodeNormalizer
from weft_clean.whitespace import WhitespaceNormalizer
from weft_extract.text import TextExtractor, discover_source_docs
from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _produced(outcome: Outcome[Sequence[Node]]) -> Sequence[Node]:
    assert isinstance(outcome, Produced), f"expected Produced, got {outcome!r}"
    return outcome.value


async def _chunks_index_text_would_store(directory: Path) -> int:
    docs = discover_source_docs(directory, extensions=(".txt",))
    nodes = _produced(await TextExtractor().run(docs, _ctx()))
    nodes = _produced(await UnicodeNormalizer().run(nodes, _ctx()))
    nodes = _produced(await WhitespaceNormalizer().run(nodes, _ctx()))
    chunker = FixedSizeChunker(config=FixedSizeChunkerConfig(size=512, overlap=50))
    return len(_produced(await chunker.run(nodes, _ctx())))


@pytest.mark.parametrize("chunks", [1, 1_003])
async def test_the_reported_count_is_what_the_shipped_ingest_stages_produce(
    tmp_path: Path, chunks: int
) -> None:
    # Arrange — 1,003 is not a multiple of any plausible per-document count, so a generator that
    # reaches its target only in whole documents cannot pass.
    out = tmp_path / "corpus"

    # Act
    corpus = bench_corpus.generate(out, chunks=chunks, seed=7)

    # Assert
    assert corpus.chunks == chunks
    assert await _chunks_index_text_would_store(out) == chunks
    assert corpus.documents == len(list(out.glob("*.txt")))
    assert corpus.documents >= 1


def test_the_same_seed_writes_the_same_bytes_and_another_seed_does_not(tmp_path: Path) -> None:
    # Arrange / Act
    first = bench_corpus.generate(tmp_path / "a", chunks=300, seed=1)
    again = bench_corpus.generate(tmp_path / "b", chunks=300, seed=1)
    other = bench_corpus.generate(tmp_path / "c", chunks=300, seed=2)

    # Assert
    assert first.digest == again.digest
    assert first.digest != other.digest
    assert sorted(p.read_bytes() for p in (tmp_path / "a").iterdir()) == sorted(
        p.read_bytes() for p in (tmp_path / "b").iterdir()
    )


def test_main_prints_the_count_its_digest_and_what_the_corpus_is_for(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    expected = bench_corpus.generate(tmp_path / "expected", chunks=1_003, seed=3)

    # Act
    code = bench_corpus.main(["--chunks", "1003", "--out", str(tmp_path / "corpus"), "--seed", "3"])

    # Assert
    printed = capsys.readouterr().out
    assert code == 0
    assert "generated 1,003 chunks (" in printed
    assert "size 512, overlap 50)" in printed
    assert f"corpus digest: {expected.digest}" in printed
    assert "latency only" in printed


def test_a_corpus_of_no_chunks_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="chunks must be at least 1"):
        bench_corpus.generate(tmp_path / "corpus", chunks=0, seed=1)


def test_a_directory_already_holding_files_is_refused_rather_than_mixed_into(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    out = tmp_path / "corpus"
    out.mkdir()
    (out / "stale.txt").write_text("left over from another run", encoding="utf-8")

    # Act
    with pytest.raises(FileExistsError, match="already holds files"):
        bench_corpus.generate(out, chunks=10, seed=1)
    code = bench_corpus.main(["--chunks", "10", "--out", str(out)])

    # Assert
    assert code == 2
    assert "already holds files" in capsys.readouterr().err
    assert [p.name for p in out.iterdir()] == ["stale.txt"]
