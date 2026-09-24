"""Building, promoting or dropping one target never changes another target's bytes.

Building, promoting or dropping one target never changes a byte another target's `BlobRef`
resolves to — ledger task **34.12**, owner decision Q-D as revised 2026-09-22.

`default` keeps today's paths, so a root written before targets existed is read with no operator
action and `BLOB_LAYOUT_VERSION` does not move. A candidate writes under `<root>/.targets/<name>/`.
`BlobRef` keys stay target-free: the store bound to a target decides where a key lives. Before
this, a candidate indexed from the same source derived the same key and overwrote the bytes the
live target's figure pointed at.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_blob.filesystem_store import (
    BLOB_LAYOUT_VERSION,
    FilesystemBlobSettings,
    FilesystemBlobStore,
)
from weft_blob.keys import blob_key
from weft_kernel.payload import SourceId
from weft_store.contract import InvalidTargetNameError, TargetName, target_name

_KEY = blob_key(tenant_id="tenant-a", source_id=SourceId("doc"), ordinal=0, extension="png")


def _store(root: Path) -> FilesystemBlobStore:
    return FilesystemBlobStore(FilesystemBlobSettings(root=root))


async def test_a_candidate_writing_the_same_key_leaves_the_live_bytes_alone(
    tmp_path: Path,
) -> None:
    # Arrange
    live = _store(tmp_path)
    candidate = await live.bind_target(target_name("w128"))
    live_uri = await live.put(_KEY, b"figure as the live index extracted it", "image/png")

    # Act
    candidate_uri = await candidate.put(
        _KEY, b"figure as a different layout model saw it", "image/png"
    )

    # Assert
    assert await live.open(live_uri) == b"figure as the live index extracted it"
    assert await candidate.open(candidate_uri) == b"figure as a different layout model saw it"
    assert live_uri != candidate_uri
    assert (tmp_path / _KEY).is_file()
    assert (tmp_path / ".targets" / "w128" / _KEY).is_file()


async def test_deleting_a_source_reaps_only_the_target_it_was_asked_of(tmp_path: Path) -> None:
    # Arrange
    live = _store(tmp_path)
    candidate = await live.bind_target(target_name("w128"))
    live_uri = await live.put(_KEY, b"live", "image/png")
    candidate_uri = await candidate.put(_KEY, b"candidate", "image/png")

    # Act
    await candidate.delete_source(SourceId("doc"))

    # Assert — and `default`'s reap does not walk into `.targets` as though it were a tenant.
    assert await live.open(live_uri) == b"live"
    assert not (tmp_path / ".targets" / "w128" / _KEY).exists()
    candidate_again = await candidate.put(_KEY, b"candidate", "image/png")
    await live.delete_source(SourceId("doc"))
    assert await candidate.open(candidate_again) == b"candidate"
    assert candidate_uri == candidate_again


async def test_dropping_a_target_removes_its_blobs_and_nothing_else(tmp_path: Path) -> None:
    # Arrange
    live = _store(tmp_path)
    candidate = await live.bind_target(target_name("w128"))
    live_uri = await live.put(_KEY, b"live", "image/png")
    await candidate.put(_KEY, b"candidate", "image/png")
    other_key = blob_key(
        tenant_id="tenant-a", source_id=SourceId("doc"), ordinal=1, extension="png"
    )
    await candidate.put(other_key, b"second figure", "image/png")

    # Act
    removed = await live.drop_target(target_name("w128"))

    # Assert
    assert removed == 2
    assert not (tmp_path / ".targets" / "w128").exists()
    assert await live.open(live_uri) == b"live"


async def test_a_root_written_before_targets_is_read_with_no_layout_change(
    tmp_path: Path,
) -> None:
    # Arrange — a root as 2.8.0 left it: one blob and the layout marker at version 1.
    before = _store(tmp_path)
    uri = await before.put(_KEY, b"written before targets", "image/png")

    # Act
    after = _store(tmp_path)

    # Assert
    assert BLOB_LAYOUT_VERSION == "1"
    assert await after.open(uri) == b"written before targets"


async def test_a_malformed_target_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    """A hand-built `TargetName` cannot steer the blob store's directory writes outside its root.

    A target becomes a directory, so the store re-checks a name it is handed rather than
    trusting that whoever built the `TargetName` validated it.
    """
    # Act / Assert
    with pytest.raises(InvalidTargetNameError):
        await _store(tmp_path).bind_target(TargetName("../escape"))
    assert not (tmp_path / ".targets").exists()
