"""Task 43.1: an inventory carries each file's identity and no bytes; a batch loads its own files.

`43.0` measured `discover_source_docs` holding 3.45 GB before the first batch of 1,000 PDFs.
`inventory_source_refs` stream-hashes each file and keeps a `SourceRef` (id, uri, path, size,
sha256). `load_source_docs` reads one batch's files and refuses, by name, a file whose bytes no
longer match the hash its inventory took, so a document is never indexed under a stale identity.
`discover_source_docs` keeps its signature for the callers that want bytes.
"""

import hashlib
from pathlib import Path

import pytest

from weft_extract.text import (
    SourceChangedDuringIndexError,
    SourceRef,
    discover_source_docs,
    inventory_source_refs,
    load_source_docs,
)


def _files(tmp_path: Path) -> dict[str, bytes]:
    contents = {"b.txt": b"second file", "a.txt": b"first", "c.md": b"# third, longer\n" * 50}
    for name, data in contents.items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / "skip.bin").write_bytes(b"not claimed")
    return contents


def test_an_inventory_carries_identity_size_and_hash_and_no_bytes(tmp_path: Path) -> None:
    # Arrange
    contents = _files(tmp_path)

    # Act
    refs = inventory_source_refs(tmp_path, extensions={".txt", ".md"})

    # Assert
    assert [ref.path.name for ref in refs] == ["a.txt", "b.txt", "c.md"]
    for ref in refs:
        data = contents[ref.path.name]
        assert ref.size == len(data)
        assert ref.content_hash == hashlib.sha256(data).hexdigest()
    assert "content" not in SourceRef.model_fields


def test_an_inventory_agrees_with_discovery_on_ids_and_uris(tmp_path: Path) -> None:
    # Arrange
    _files(tmp_path)

    # Act
    refs = inventory_source_refs(tmp_path, extensions={".txt", ".md"})
    docs = discover_source_docs(tmp_path, extensions={".txt", ".md"})

    # Assert
    assert [(r.source_id, r.uri) for r in refs] == [(d.source_id, d.uri) for d in docs]


def test_loading_returns_the_bytes_of_exactly_the_refs_given(tmp_path: Path) -> None:
    # Arrange
    contents = _files(tmp_path)
    refs = inventory_source_refs(tmp_path, extensions={".txt", ".md"})

    # Act
    docs = load_source_docs(refs[1:])

    # Assert
    assert [doc.content for doc in docs] == [contents["b.txt"], contents["c.md"]]
    assert [doc.source_id for doc in docs] == [ref.source_id for ref in refs[1:]]


def test_a_file_changed_after_the_inventory_is_refused_by_name(tmp_path: Path) -> None:
    # Arrange
    _files(tmp_path)
    refs = inventory_source_refs(tmp_path, extensions={".txt", ".md"})
    (tmp_path / "b.txt").write_bytes(b"edited while indexing")

    # Act
    with pytest.raises(SourceChangedDuringIndexError) as raised:
        load_source_docs(refs)

    # Assert
    assert refs[1].uri in str(raised.value)
    assert "changed" in str(raised.value)


def test_a_file_removed_after_the_inventory_is_refused_by_name(tmp_path: Path) -> None:
    # Arrange
    _files(tmp_path)
    refs = inventory_source_refs(tmp_path, extensions={".txt", ".md"})
    (tmp_path / "a.txt").unlink()

    # Act
    with pytest.raises(SourceChangedDuringIndexError) as raised:
        load_source_docs(refs)

    # Assert
    assert refs[0].uri in str(raised.value)
