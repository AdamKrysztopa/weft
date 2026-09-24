"""`scripts/open_ragbench.py` and its rendering in `scripts/fetch_corpus.py` — ledger task **38.3**.

Open RAGBench is the question set Phase 38 measures on, and its questions are labelled against the
dataset's own processed documents. So those documents become a `fetch`-tier corpus under V1's own
rule: pinned to the dataset revision, both halves checksummed — the JSON the dataset serves and the
markdown this repository writes from it — and no byte of either tracked. `fetch_corpus.py` already
pins a fetched source and a rendered document separately for Wikipedia; this adds a second
rendering to the same machinery rather than a second fetcher.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import fetch_corpus
import open_ragbench
import pytest
from open_ragbench import RAGBENCH_REVISION

from weft_eval.corpus_manifest import load_manifest as load_manifest_from_wheel

_TABLE = "| a | b |\n|---|---|\n| 1 | 2 |"


def _document(identifier: str) -> dict[str, object]:
    return {
        "title": "Multiple Imputation of\n  Hierarchical Data",
        "id": identifier,
        "authors": ["A. Author"],
        "categories": ["stat.ME"],
        "abstract": "An abstract that is also section zero.",
        "updated": "2025-03-28T13:22:33Z",
        "published": "2024-01-03T18:31:23Z",
        "sections": [
            {
                "section_id": 0,
                "text": "#### Abstract\n\nAn abstract that is also section zero.\n",
                "tables": {},
                "images": {"img-0.jpeg": "data:image/jpeg;base64,/9j/AAAA"},
            },
            {
                "section_id": 1,
                "text": "# 3. Methods. \n\n3.1. Notation. We consider $x_i$.",
                "tables": {"table_0": _TABLE},
                "images": {
                    "img-1.jpeg": "data:image/jpeg;base64,/9j/BBBB",
                    "img-2.jpeg": "data:image/jpeg;base64,/9j/CCCC",
                },
            },
        ],
    }


def _dataset(root: Path, identifiers: tuple[str, ...] = ("2401.01872v2", "2402.00001v1")) -> Path:
    """A dataset directory in `vectara/open_ragbench`'s own `pdf/arxiv/` layout."""
    arxiv = root / "open_ragbench" / "pdf" / "arxiv"
    (arxiv / "corpus").mkdir(parents=True)
    for identifier in identifiers:
        (arxiv / "corpus" / f"{identifier}.json").write_text(
            json.dumps(_document(identifier)), encoding="utf-8"
        )
    for name in ("queries.json", "qrels.json", "answers.json", "pdf_urls.json"):
        (arxiv / name).write_text(json.dumps({"q": name}), encoding="utf-8")
    return arxiv


def test_a_document_renders_its_title_then_every_section_verbatim_with_its_tables() -> None:
    # Arrange
    body = json.dumps(_document("2401.01872v2")).encode("utf-8")

    # Act
    rendered = open_ragbench.render_document(body)

    # Assert
    text = rendered.text
    assert text.startswith("# Multiple Imputation of Hierarchical Data\n\n")
    first = text.index("#### Abstract\n\nAn abstract that is also section zero.")
    second = text.index("# 3. Methods. \n\n3.1. Notation. We consider $x_i$.")
    table = text.index(_TABLE)
    assert first < second < table
    assert "base64" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_a_rendering_states_the_images_it_dropped() -> None:
    """A figure is a data URI in the dataset and nothing in a markdown corpus.

    The count is the document's own account of what rendering cost it, the way `math_blocks_dropped`
    is.
    """
    # Act
    rendered = open_ragbench.render_document(json.dumps(_document("x")).encode("utf-8"))

    # Assert
    assert rendered.images_dropped == 3


def test_rendering_is_a_pure_function_of_the_bytes() -> None:
    # Arrange
    body = json.dumps(_document("2401.01872v2")).encode("utf-8")

    # Act / Assert
    assert open_ragbench.render_document(body) == open_ragbench.render_document(body)


def test_the_manifest_pins_every_document_twice_and_every_question_file_once(
    tmp_path: Path,
) -> None:
    # Arrange
    dataset = _dataset(tmp_path)
    manifest = tmp_path / "corpus" / "open-ragbench.toml"
    manifest.parent.mkdir()

    # Act
    manifest.write_text(open_ragbench.manifest_text(dataset), encoding="utf-8")
    name, documents = fetch_corpus.load_manifest(manifest)
    raw = tomllib.loads(manifest.read_text(encoding="utf-8"))

    # Assert
    assert name == "open-ragbench-arxiv"
    assert [document.id for document in documents] == ["2401.01872v2", "2402.00001v1"]
    for document in documents:
        source_bytes = (dataset / "corpus" / f"{document.id}.json").read_bytes()
        rendered = open_ragbench.render_document(source_bytes)
        assert document.tier is fetch_corpus.Tier.FETCH
        assert RAGBENCH_REVISION in document.source
        assert document.source.endswith(f"/pdf/arxiv/corpus/{document.id}.json")
        assert document.source_sha256 == hashlib.sha256(source_bytes).hexdigest()
        assert document.sha256 == hashlib.sha256(rendered.text.encode("utf-8")).hexdigest()
        assert document.render is open_ragbench.OpenRagbenchRendering.MARKDOWN
        assert document.images_dropped == rendered.images_dropped
        assert (
            document.path == (tmp_path / "corpus" / "open-ragbench" / f"{document.id}.md").resolve()
        )
    pinned = {entry["name"]: entry for entry in raw["dataset_file"]}
    assert set(pinned) == {"queries.json", "qrels.json", "answers.json", "pdf_urls.json"}
    for file_name, entry in pinned.items():
        assert entry["sha256"] == hashlib.sha256((dataset / file_name).read_bytes()).hexdigest()
        assert RAGBENCH_REVISION in entry["source"]
    assert raw["dataset"]["revision"] == RAGBENCH_REVISION


def test_the_manifest_reads_through_the_wheels_own_manifest_reader(tmp_path: Path) -> None:
    """Keeps one manifest reader: the script's output must parse through the wheel's own.

    `weft eval run --manifest` and the experiment runner read manifests through
    `weft_eval.corpus_manifest`, not through this script.
    """
    # Arrange
    dataset = _dataset(tmp_path)
    manifest = tmp_path / "corpus" / "open-ragbench.toml"
    manifest.parent.mkdir()
    manifest.write_text(open_ragbench.manifest_text(dataset), encoding="utf-8")

    # Act
    read = load_manifest_from_wheel(manifest)

    # Assert
    assert read.name == "open-ragbench-arxiv"
    assert {document.id for document in read.documents} == {"2401.01872v2", "2402.00001v1"}


def test_fetch_renders_from_a_local_copy_of_the_pinned_source_and_verifies_both_halves(
    tmp_path: Path,
) -> None:
    """The dataset is already on disk from Phase 29.

    A local copy is only as good as its digest, so it is checked against `source_sha256` exactly as
    downloaded bytes are — and reading it is not a request, so no polite delay is paid for it.
    """
    # Arrange
    dataset = _dataset(tmp_path)
    manifest = tmp_path / "corpus" / "open-ragbench.toml"
    manifest.parent.mkdir()
    manifest.write_text(open_ragbench.manifest_text(dataset), encoding="utf-8")

    # Act
    fetched = fetch_corpus.main(
        ["fetch", "--manifest", str(manifest), "--source-dir", str(dataset / "corpus")]
    )
    verified = fetch_corpus.main(["verify", "--manifest", str(manifest)])

    # Assert
    assert fetched == 0
    assert verified == 0
    written = (tmp_path / "corpus" / "open-ragbench" / "2401.01872v2.md").read_bytes()
    source = (dataset / "corpus" / "2401.01872v2.json").read_bytes()
    assert written == open_ragbench.render_document(source).text.encode("utf-8")


def test_a_local_copy_that_is_not_the_pinned_source_is_refused_before_rendering(
    tmp_path: Path,
) -> None:
    # Arrange
    dataset = _dataset(tmp_path)
    manifest = tmp_path / "corpus" / "open-ragbench.toml"
    manifest.parent.mkdir()
    manifest.write_text(open_ragbench.manifest_text(dataset), encoding="utf-8")
    tampered = dataset / "corpus" / "2401.01872v2.json"
    tampered.write_text(tampered.read_text(encoding="utf-8").replace("Methods", "Method"))
    _, documents = fetch_corpus.load_manifest(manifest)
    (document,) = (d for d in documents if d.id == "2401.01872v2")

    # Act
    result = fetch_corpus.fetch_one(document, source_dir=dataset / "corpus")

    # Assert
    assert result.status is fetch_corpus.Status.CORRUPT
    assert "before rendering" in result.detail
    assert not document.path.exists()


def test_a_rendering_that_drops_a_different_number_of_images_is_refused(tmp_path: Path) -> None:
    # Arrange
    dataset = _dataset(tmp_path, ("2401.01872v2",))
    manifest = tmp_path / "corpus" / "open-ragbench.toml"
    manifest.parent.mkdir()
    manifest.write_text(
        open_ragbench.manifest_text(dataset).replace("images_dropped = 3", "images_dropped = 2"),
        encoding="utf-8",
    )
    (document,) = fetch_corpus.load_manifest(manifest)[1]

    # Act
    result = fetch_corpus.fetch_one(document, source_dir=dataset / "corpus")

    # Assert
    assert result.status is fetch_corpus.Status.CORRUPT
    assert "image" in result.detail


def test_an_unknown_rendering_is_refused_listing_every_rendering_that_exists(
    tmp_path: Path,
) -> None:
    # Arrange
    dataset = _dataset(tmp_path, ("2401.01872v2",))
    manifest = tmp_path / "corpus" / "open-ragbench.toml"
    manifest.parent.mkdir()
    manifest.write_text(
        open_ragbench.manifest_text(dataset).replace(
            'render = "open-ragbench-md"', 'render = "open-ragbench-html"'
        ),
        encoding="utf-8",
    )

    # Act
    with pytest.raises(ValueError, match="open-ragbench-html") as caught:
        fetch_corpus.load_manifest(manifest)

    # Assert
    assert "open-ragbench-md" in str(caught.value)
    assert "wikitext-md" in str(caught.value)


# --- Ledger 38.8: the raw PDFs as a second corpus --------------------------------------------


def _pdfs(root: Path, identifiers: tuple[str, ...]) -> Path:
    """The downloaded PDFs, laid out under the corpus directory as this repository does it.

    The downloaded PDFs, under the corpus directory as in this repository's own layout — a
    manifest refuses a document that resolves outside its directory, and a link resolves.
    """
    directory = root / "corpus" / "open_ragbench" / "pdfs"
    directory.mkdir(parents=True)
    for identifier in identifiers:
        (directory / f"{identifier}.pdf").write_bytes(f"%PDF-1.4 {identifier}".encode())
    return directory


def test_staging_links_every_pdf_but_the_excluded_ones(tmp_path: Path) -> None:
    # Arrange
    pdfs = _pdfs(tmp_path, ("2401.00001v1", "2401.00002v1", "2407.07009v2"))
    stage = tmp_path / "corpus" / "open-ragbench-pdf"

    # Act
    staged = open_ragbench.stage_pdfs(
        pdfs, stage, excluded={"2407.07009v2": "pdf-text refuses page 16: no text layer"}
    )

    # Assert
    assert staged == ("2401.00001v1", "2401.00002v1")
    assert sorted(path.name for path in stage.iterdir()) == ["2401.00001v1.pdf", "2401.00002v1.pdf"]
    assert (stage / "2401.00001v1.pdf").read_bytes() == b"%PDF-1.4 2401.00001v1"


def test_the_pdf_manifest_pins_each_staged_pdf_at_its_arxiv_version(tmp_path: Path) -> None:
    # Arrange
    pdfs = _pdfs(tmp_path, ("2401.00001v1", "2401.00002v1", "2407.07009v2"))
    corpus = tmp_path / "corpus"
    stage = corpus / "open-ragbench-pdf"
    excluded = {"2407.07009v2": "pdf-text refuses page 16: no text layer"}
    open_ragbench.stage_pdfs(pdfs, stage, excluded=excluded)
    manifest = corpus / "open-ragbench-pdf.toml"

    # Act
    manifest.write_text(
        open_ragbench.pdf_manifest_text(stage, manifest_dir=corpus, excluded=excluded),
        encoding="utf-8",
    )
    name, documents = fetch_corpus.load_manifest(manifest)

    # Assert
    assert name == "open-ragbench-arxiv-pdf"
    assert [document.id for document in documents] == ["2401.00001v1", "2401.00002v1"]
    for document in documents:
        body = (pdfs / f"{document.id}.pdf").read_bytes()
        assert document.tier is fetch_corpus.Tier.FETCH
        assert document.source == f"https://arxiv.org/pdf/{document.id}"
        assert document.sha256 == hashlib.sha256(body).hexdigest()
        assert document.path == (stage / f"{document.id}.pdf").resolve()
    assert {document.id for document in load_manifest_from_wheel(manifest).documents} == {
        "2401.00001v1",
        "2401.00002v1",
    }


def test_the_pdf_manifest_says_which_pdfs_it_left_out_and_why(tmp_path: Path) -> None:
    # Arrange
    pdfs = _pdfs(tmp_path, ("2401.00001v1", "2412.00651v1"))
    corpus = tmp_path / "corpus"
    stage = corpus / "open-ragbench-pdf"
    excluded = {"2412.00651v1": "pdf-text refuses page 4: an unpaired surrogate"}
    open_ragbench.stage_pdfs(pdfs, stage, excluded=excluded)

    # Act
    text = open_ragbench.pdf_manifest_text(stage, manifest_dir=corpus, excluded=excluded)

    # Assert
    assert "2412.00651v1: pdf-text refuses page 4: an unpaired surrogate" in text
