"""`weft_eval.corpus_manifest` — ledger repair **R22.4a**: the corpus manifest, read from the wheel.

`weft eval baseline` needs the manifest's ids, digests, tiers and paths, and
`scripts/fetch_corpus.py` stays standard-library-only because the reproduction archive ships it to
people with no wheel. So one file has two readers, and the first test is what makes that safe: both
read the tracked manifest and must agree on every field they share.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fetch_corpus import MANIFEST
from fetch_corpus import load_manifest as load_manifest_for_fetch

from weft_eval.corpus_manifest import (
    CorpusManifestError,
    DocumentStatus,
    Tier,
    load_manifest,
    verify_document,
)
from weft_kernel.errors import WeftError

_BODY = b"# doc a\n"

_ONE_DOCUMENT = """[corpus]
name = "tiny"

[[document]]
id = "doc-a"
path = "{path}"
format = "markdown"
language = "en"
sha256 = "{sha}"
tier = "{tier}"
source = "https://example.org/doc-a"
"""


def _manifest(
    directory: Path,
    *,
    path: str = "text/doc-a.md",
    tier: str = "fetch",
    drop: str | None = None,
) -> Path:
    body = _ONE_DOCUMENT.format(path=path, sha=hashlib.sha256(_BODY).hexdigest(), tier=tier)
    if drop is not None:
        body = "\n".join(line for line in body.splitlines() if not line.startswith(f"{drop} ="))
    manifest = directory / "manifest.toml"
    manifest.write_text(body, encoding="utf-8")
    return manifest


def test_both_readers_agree_on_the_tracked_manifest() -> None:
    # Arrange
    fetch_name, fetch_documents = load_manifest_for_fetch(MANIFEST)

    # Act
    manifest = load_manifest(MANIFEST)

    # Assert
    assert len(fetch_documents) >= 2
    assert manifest.name == fetch_name
    assert [
        (doc.id, doc.path, doc.format, doc.language, doc.sha256, doc.tier.value)
        for doc in manifest.documents
    ] == [
        (doc.id, doc.path, doc.fmt, doc.language, doc.sha256, doc.tier.value)
        for doc in fetch_documents
    ]


@pytest.mark.parametrize(
    ("on_disk", "expected"),
    [
        (None, DocumentStatus.MISSING),
        (b"# something else\n", DocumentStatus.CORRUPT),
        (_BODY, DocumentStatus.OK),
    ],
)
def test_a_document_is_judged_by_its_bytes(
    tmp_path: Path, on_disk: bytes | None, expected: DocumentStatus
) -> None:
    # Arrange
    document = load_manifest(_manifest(tmp_path)).documents[0]
    if on_disk is not None:
        document.path.parent.mkdir(parents=True)
        document.path.write_bytes(on_disk)

    # Act
    status = verify_document(document)

    # Assert
    assert document.path == (tmp_path / "text" / "doc-a.md").resolve()
    assert status is expected


def test_only_the_operator_tier_cannot_be_reproduced() -> None:
    # Act
    reproducible = {tier: tier.reproducible for tier in Tier}

    # Assert
    assert reproducible == {Tier.GATE: True, Tier.FETCH: True, Tier.OPERATOR: False}


def test_an_unknown_tier_is_refused_naming_the_document_and_every_tier(tmp_path: Path) -> None:
    # Arrange
    manifest = _manifest(tmp_path, tier="borrowed")

    # Act
    with pytest.raises(CorpusManifestError) as caught:
        load_manifest(manifest)

    # Assert
    message = str(caught.value)
    assert isinstance(caught.value, WeftError)
    assert "doc-a" in message
    assert "'borrowed'" in message
    assert all(tier.value in message for tier in Tier)


def test_a_path_outside_the_manifest_directory_is_refused(tmp_path: Path) -> None:
    # Arrange
    manifest = _manifest(tmp_path, path="../elsewhere/doc-a.md")

    # Act
    with pytest.raises(CorpusManifestError) as caught:
        load_manifest(manifest)

    # Assert
    assert "doc-a" in str(caught.value)
    assert "outside" in str(caught.value)


def test_an_entry_missing_a_required_key_names_the_entry_and_the_key(tmp_path: Path) -> None:
    # Arrange
    manifest = _manifest(tmp_path, drop="sha256")

    # Act
    with pytest.raises(CorpusManifestError) as caught:
        load_manifest(manifest)

    # Assert
    assert "doc-a" in str(caught.value)
    assert "sha256" in str(caught.value)


def test_an_absent_manifest_is_refused_naming_where_it_looked(tmp_path: Path) -> None:
    # Arrange
    absent = tmp_path / "no-such-manifest.toml"

    # Act
    with pytest.raises(CorpusManifestError) as caught:
        load_manifest(absent)

    # Assert
    assert str(absent) in str(caught.value)
