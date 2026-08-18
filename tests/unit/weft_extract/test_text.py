"""Unit tests for `weft_extract.text`.

Mirrors `packages/weft-extract/src/weft_extract/text.py`. Covers the happy
path (`.txt` and `.md` files under a directory become `SourceDoc`s, which
`TextExtractor` then turns into root `Node`s), the edge case of an empty
batch (`NothingToProduce`), and the error case of a file that is not valid
UTF-8 (`Failed`, naming the file, never a silent drop).
"""

from collections.abc import Sequence
from pathlib import Path

from weft_extract.contract import SourceDoc
from weft_extract.text import TextExtractor, discover_source_docs
from weft_kernel.context import Context
from weft_kernel.payload import Failed, Node, NothingToProduce, Outcome, Produced, SourceId


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def test_discover_source_docs_finds_only_txt_and_md_files(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "b.md").write_text("# heading", encoding="utf-8")
    (tmp_path / "c.pdf").write_bytes(b"%PDF-1.4 not really")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "d.txt").write_text("nested", encoding="utf-8")

    # Act — the accept set is passed in, never read off this pack's own constant; see
    # `weft_extract.accept` for the defect that made it an argument.
    docs = discover_source_docs(tmp_path, extensions=TextExtractor.extensions)

    # Assert
    uris = {doc.uri for doc in docs}
    assert len(docs) == 3
    assert any(uri.endswith("a.txt") for uri in uris)
    assert any(uri.endswith("b.md") for uri in uris)
    assert any(uri.endswith("d.txt") for uri in uris)
    assert not any(uri.endswith("c.pdf") for uri in uris)


async def test_run_extracts_one_root_node_per_source_document() -> None:
    # Arrange
    extractor = TextExtractor()
    doc = SourceDoc(source_id=SourceId("doc-1"), uri="file:///a.txt", content=b"hello world")

    # Act
    outcome: Outcome[Sequence[Node]] = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    [node] = outcome.value
    assert node.content == "hello world"
    assert node.lineage.parents == ()
    assert node.lineage.sources == frozenset({SourceId("doc-1")})


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    extractor = TextExtractor()

    # Act
    outcome = await extractor.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no source documents to extract")


async def test_run_fails_naming_the_uri_of_a_document_that_is_not_valid_utf8() -> None:
    # Arrange
    extractor = TextExtractor()
    doc = SourceDoc(source_id=SourceId("doc-1"), uri="file:///bad.txt", content=b"\xff\xfe\x00")

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "bad.txt" in outcome.reason
