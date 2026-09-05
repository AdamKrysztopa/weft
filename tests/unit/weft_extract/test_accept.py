"""Unit tests for `weft_extract.accept`.

Mirrors `packages/weft-rag/src/weft_extract/accept.py`. Repair for a
reviewer finding, and the shape of the defect matters more than the function:
ingest used to filter on `weft_extract.text.EXTENSIONS`, one pack's module
constant, so shipping `weft-pdf` left `.pdf` **silently invisible** to
`weft index` — a run over nine PDFs that discovered nothing and exited 0.
`docs/11-multimodal.md:205` predicted it by line number.

The fix is `docs/02-extension-model.md` §1's own rule applied — capability is
derived, never declared — so these tests are all one assertion in different
clothes: what ingest accepts is a function of what actually registered, and
nothing else. A stand-in third-party extractor stands in for the pack nobody
here wrote, because that is the case the constant could never have covered.
"""

from pathlib import Path

from weft_extract.accept import claimed_extensions, present_suffixes
from weft_extract.contract import Extractor
from weft_extract.text import TextExtractor, discover_source_docs
from weft_kernel.registry import Registry


class _EpubExtractor:
    """A third-party extractor this repository does not ship — the case that matters."""

    extensions: tuple[str, ...] = (".epub",)


class _ArchiveExtractor:
    """A second claimant for one suffix, which is what makes selection a real question."""

    extensions: tuple[str, ...] = (".epub",)


class _StreamExtractor:
    """An extractor that reads from somewhere that is not a filesystem, so claims nothing."""


def _registry() -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Extractor, "epub", _EpubExtractor, distribution="acme-epub")
    return registry


def test_the_accept_set_is_the_union_of_what_actually_registered() -> None:
    # Act
    claims = claimed_extensions(_registry())

    # Assert — `.epub` is here because a pack registered it, not because anything in
    # this repository was edited to know about it.
    assert claims == {".epub": ("epub",), ".md": ("text",), ".txt": ("text",)}


def test_a_suffix_two_extractors_claim_names_both_of_them() -> None:
    # Arrange
    registry = _registry()
    registry.add(Extractor, "archive", _ArchiveExtractor, distribution="acme-archive")

    # Act
    claims = claimed_extensions(registry)

    # Assert — sorted, so a caller reporting the ambiguity prints a stable list.
    assert claims[".epub"] == ("archive", "epub")


def test_an_extractor_that_claims_no_extension_contributes_nothing() -> None:
    # Arrange — an extractor reading from an object store satisfies the same contract
    # and has no file suffix to declare. Reading `extensions` defensively is what lets
    # it register at all.
    registry = Registry()
    registry.add(Extractor, "stream", _StreamExtractor, distribution="acme-stream")

    # Act / Assert
    assert claimed_extensions(registry) == {}


def test_discovery_reads_the_accept_set_it_is_given_rather_than_one_packs_constant(
    tmp_path: Path,
) -> None:
    # Arrange
    (tmp_path / "notes.md").write_text("markdown")
    (tmp_path / "book.epub").write_bytes(b"epub")

    # Act
    docs = discover_source_docs(tmp_path, extensions=frozenset({".epub"}))

    # Assert
    assert [doc.uri.rsplit("/", 1)[-1] for doc in docs] == ["book.epub"]


def test_what_is_present_is_reported_so_unreadable_files_can_be_named(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "notes.md").write_text("markdown")
    (tmp_path / "slides.pptx").write_bytes(b"not claimed")
    (tmp_path / "LICENSE").write_text("no suffix at all")

    # Act
    present = present_suffixes(tmp_path)

    # Assert — a directory whose files nobody can read must be able to say so; the
    # alternative is the silent, successful no-op this whole repair is about. A file
    # with no suffix is not a format anyone failed to install, so it is not named.
    assert present == frozenset({".md", ".pptx"})
    assert present - frozenset({".md"}) == frozenset({".pptx"})
