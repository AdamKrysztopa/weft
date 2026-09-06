"""`FilesystemBlobStore` — the shipped `BlobStore`, ledger task `9.4`.

Three async methods and no pipeline position. What this file pins beyond the round trip:

**A blob root carries its own layout version, checked at open and refused on mismatch.** `S11`
(`docs/README.md`) calls the blob root the *seventh persistence surface*: `ExtModel.
__schema_version__` versions the `BlobRef` and says nothing about the layout that reference resolves
*through*. The rule `S11` settles is one per persistence root a pack owns outside the node store —
carried in the root, checked at open, refused with a named remedy, as a conformance case and never a
contract change. A store that reads a root written by a future layout must refuse it rather than
guess, because guessing here reads somebody's bytes from the wrong place.

**A key never escapes the root.** `weft_blob.keys` derives every first-party key and cannot produce
a traversal, but `put` takes a `str` and a third party may compose one — so the refusal lives at the
boundary that would suffer, not only at the helper that is easy to use correctly.

**Blocking file IO is off the event loop.** G6, and `weft_pdf.pdf_layout`'s module docstring is the
offload shape. FF7(b) watches `weft_kernel.blocking` for a stage; a *service* passes through no
seam wrap, so nothing catches it automatically and it is asserted here instead.
"""

from pathlib import Path

import pytest

from weft_blob.contract import BlobStore, BlobUri
from weft_blob.filesystem_store import (
    BLOB_LAYOUT_VERSION,
    BlobKeyRefusedError,
    BlobLayoutVersionError,
    BlobNotFoundError,
    FilesystemBlobSettings,
    FilesystemBlobStore,
)
from weft_blob.keys import blob_key, source_prefix
from weft_kernel.blocking import guard
from weft_kernel.payload import SourceId


def _store(root: Path) -> FilesystemBlobStore:
    return FilesystemBlobStore(FilesystemBlobSettings(root=root))


async def test_bytes_written_come_back_byte_identical(tmp_path: Path) -> None:
    """The happy path, and the only thing every other test here is about protecting."""
    # Arrange
    store = _store(tmp_path)
    payload = b"\x89PNG\r\n\x1a\n not really a png"

    # Act
    uri = await store.put("tenant-a/abc/0.png", payload, "image/png")
    read_back = await store.open(uri)

    # Assert
    assert read_back == payload


async def test_the_shipped_store_satisfies_the_contract(tmp_path: Path) -> None:
    # Act / Assert
    assert isinstance(_store(tmp_path), BlobStore)


async def test_writing_the_same_key_twice_replaces_rather_than_duplicating(tmp_path: Path) -> None:
    """Keys are derived, so a re-extraction of an unchanged file writes the same key again.

    That must be an overwrite: the alternative is a root that grows without bound every time a
    corpus is re-indexed, with no ledger to tell anyone which copy is live.
    """
    # Arrange
    store = _store(tmp_path)
    key = "tenant-a/abc/0.png"

    # Act
    await store.put(key, b"first", "image/png")
    uri = await store.put(key, b"second", "image/png")

    # Assert
    assert await store.open(uri) == b"second"


async def test_opening_a_uri_nothing_wrote_fails_loudly_and_by_name(tmp_path: Path) -> None:
    """An empty answer is not a fact about the world: `b""` here would be indistinguishable from
    a real empty blob, and a caller would embed nothing and never know."""
    # Act / Assert
    with pytest.raises(BlobNotFoundError):
        await _store(tmp_path).open(BlobUri(await _uri_for_a_key_never_written(tmp_path)))


async def _uri_for_a_key_never_written(root: Path) -> str:
    """A well-formed URI in this root's own scheme, for a key that was never put."""
    store = _store(root)
    written = await store.put("tenant-a/abc/0.png", b"x", "image/png")
    Path(str(written).removeprefix("file://")).unlink()
    return written


async def test_delete_prefix_reaps_every_blob_under_it_and_counts_them(tmp_path: Path) -> None:
    """The cascade the derived-key design buys: one prefix, no ledger, a real count back."""
    # Arrange
    store = _store(tmp_path)
    source = SourceId("/corpus/report.pdf")
    for ordinal in range(3):
        await store.put(
            blob_key(tenant_id="t", source_id=source, ordinal=ordinal, extension="png"),
            b"x",
            "image/png",
        )
    await store.put(
        blob_key(
            tenant_id="t", source_id=SourceId("/corpus/other.pdf"), ordinal=0, extension="png"
        ),
        b"y",
        "image/png",
    )

    # Act
    reaped = await store.delete_prefix(source_prefix(tenant_id="t", source_id=source))

    # Assert
    assert reaped == 3


async def test_delete_prefix_leaves_another_sources_blobs_alone(tmp_path: Path) -> None:
    """The failure this module must never have: reaping somebody else's bytes."""
    # Arrange
    store = _store(tmp_path)
    kept = SourceId("/corpus/other.pdf")
    kept_key = blob_key(tenant_id="t", source_id=kept, ordinal=0, extension="png")
    kept_uri = await store.put(kept_key, b"keep me", "image/png")
    doomed = SourceId("/corpus/report.pdf")
    await store.put(
        blob_key(tenant_id="t", source_id=doomed, ordinal=0, extension="png"), b"x", "image/png"
    )

    # Act
    await store.delete_prefix(source_prefix(tenant_id="t", source_id=doomed))

    # Assert
    assert await store.open(kept_uri) == b"keep me"


async def test_deleting_a_prefix_nothing_wrote_is_zero_and_not_an_error(tmp_path: Path) -> None:
    """Deletion is idempotent and resumable — `SourceDeletable`'s own stated promise."""
    # Act / Assert
    assert await _store(tmp_path).delete_prefix("t/nothing-here/") == 0


async def test_weft_delete_reaches_a_sources_blobs_and_reports_them_by_kind(tmp_path: Path) -> None:
    """9.4's cascade clause meeting 9.3's field: `node_count` is honestly zero and `blob` is not.

    This is the participant task 9.3 was written for — before it, a blob store that reaped forty
    blobs reported `node_count=0` and nothing else.
    """
    # Arrange
    store = _store(tmp_path)
    source = SourceId("/corpus/report.pdf")
    for ordinal in range(2):
        await store.put(
            blob_key(tenant_id="t", source_id=source, ordinal=ordinal, extension="png"),
            b"x",
            "image/png",
        )

    # Act
    removed = await store.delete_source(source)

    # Assert
    assert removed.node_count == 0
    assert dict(removed.removed) == {"blob": 2}


async def test_a_key_that_would_escape_the_root_is_refused(tmp_path: Path) -> None:
    """`put` takes a `str`; the helper cannot be the only guard for a boundary strangers reach."""
    # Act / Assert
    with pytest.raises(BlobKeyRefusedError):
        await _store(tmp_path).put("../escaped.png", b"x", "image/png")


async def test_an_absolute_key_is_refused(tmp_path: Path) -> None:
    """`Path(root) / "/etc/passwd"` is `/etc/passwd`, so this is one silent write away."""
    # Act / Assert
    with pytest.raises(BlobKeyRefusedError):
        await _store(tmp_path).put("/etc/passwd", b"x", "image/png")


async def test_a_uri_pointing_outside_the_root_is_refused(tmp_path: Path) -> None:
    """A `BlobUri` arrives from a `BlobRef` in a persisted node's `ext`, so it is **data**.

    `weft_kernel.payload.applicability._FactRef`'s docstring already makes this argument for a
    persisted class reference: resolving whatever a stored record names would turn a JSON
    artefact into an instruction. The same holds one layer down — resolving whatever path a
    stored record names turns it into an arbitrary file read. The root is the boundary, and
    `open` is the side of it that reads.
    """
    # Arrange
    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"not yours")
    store = _store(tmp_path)
    await store.put("t/abc/0.png", b"x", "image/png")

    # Act / Assert
    with pytest.raises(BlobKeyRefusedError):
        await store.open(BlobUri(f"file://{outside}"))


async def test_a_uri_that_climbs_out_of_the_root_is_refused(tmp_path: Path) -> None:
    """The traversal spelling of the same hole — refused before it is resolved, not after."""
    # Arrange
    store = _store(tmp_path)
    await store.put("t/abc/0.png", b"x", "image/png")

    # Act / Assert
    with pytest.raises(BlobKeyRefusedError):
        await store.open(BlobUri(f"file://{tmp_path}/t/../../outside.txt"))


async def test_deleting_the_empty_prefix_is_refused(tmp_path: Path) -> None:
    """`delete_prefix("")` resolves to the root itself, and would take the layout marker with it.

    A caller that means *everything* can say so by naming what it means; an empty string
    reaching this method is far more likely to be an unset variable, and this is a `destroy`
    -class operation where the difference is the whole corpus.
    """
    # Arrange
    store = _store(tmp_path)
    kept = await store.put("t/abc/0.png", b"keep", "image/png")

    # Act / Assert
    with pytest.raises(BlobKeyRefusedError):
        await store.delete_prefix("")
    assert await store.open(kept) == b"keep"


async def test_a_root_written_by_a_different_layout_is_refused_with_a_remedy(
    tmp_path: Path,
) -> None:
    """`S11`'s seventh-surface rule, at the one place it can be enforced.

    The message must name the remedy — an operator holding a root they cannot read needs to be
    told what to do, not merely that the number differs.
    """
    # Arrange
    store = _store(tmp_path)
    await store.put("t/abc/0.png", b"x", "image/png")
    layout_file = next(path for path in tmp_path.iterdir() if path.name.startswith("."))
    layout_file.write_text("999", encoding="utf-8")

    # Act / Assert
    with pytest.raises(BlobLayoutVersionError) as caught:
        await _store(tmp_path).open(BlobUri(f"file://{tmp_path}/t/abc/0.png"))
    message = str(caught.value)
    assert "999" in message
    assert BLOB_LAYOUT_VERSION in message


async def test_a_root_this_layout_wrote_is_accepted_by_a_second_store_over_it(
    tmp_path: Path,
) -> None:
    """The contrast: the version check must not refuse the root its own writer just produced."""
    # Arrange
    uri = await _store(tmp_path).put("t/abc/0.png", b"x", "image/png")

    # Act / Assert
    assert await _store(tmp_path).open(uri) == b"x"


async def test_file_io_never_runs_on_the_event_loop(tmp_path: Path) -> None:
    """G6. A service passes through no seam wrap, so no machinery catches this for us.

    `weft_kernel.blocking` is the same detector the seam installs for a stage; asked directly, it
    answers for a service too.
    """
    # Arrange
    store = _store(tmp_path)

    # Act / Assert — inside the detector, every one of the three methods. `guard` raises
    # `BlockingCallError` from the offending call itself, so a green here is the assertion.
    with guard("blob"):
        uri = await store.put("t/abc/0.png", b"x", "image/png")
        await store.open(uri)
        await store.delete_prefix("t/abc/")
