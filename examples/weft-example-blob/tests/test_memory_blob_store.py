"""This pack's own tests — the fourth canonical file `docs/07-extension-cost.md` names.

`InMemoryBlobStore` is a stranger's `BlobStore`: it satisfies the Protocol structurally, imports it
only to name it in nothing at all, and keeps its bytes in a dict. It exists because weft's fitness
function 9(c) requires every published contract to have an implementation from outside the
workspace — and because a `BlobStore` whose second implementation is not a filesystem is the
cheapest proof that the contract is about *a keyspace of bytes* and not about a directory.

Collected by weft's own gate through its `examples-tests` step, and still runnable on its own with
`uv run pytest` from inside this directory, which is how a stranger runs it.
"""

import pytest
from weft_example_blob.memory_store import InMemoryBlobStore, UnknownBlobError

from weft_kernel.payload import SourceId


async def test_bytes_written_come_back_byte_identical() -> None:
    # Arrange
    store = InMemoryBlobStore()

    # Act
    uri = await store.put("t/abc/0.png", b"pixels", "image/png")

    # Assert
    assert await store.open(uri) == b"pixels"


async def test_opening_something_never_written_fails_rather_than_answering_empty() -> None:
    """An empty answer is not a fact about the world — weft's own rule, and it applies to a
    stranger's implementation exactly as much as to the shipped one."""
    # Act / Assert
    with pytest.raises(UnknownBlobError):
        await InMemoryBlobStore().open("memory:nothing-here")


async def test_a_prefix_delete_reaps_only_what_is_under_it() -> None:
    # Arrange
    store = InMemoryBlobStore()
    kept = await store.put("t/other/0.png", b"keep", "image/png")
    await store.put("t/doomed/0.png", b"go", "image/png")
    await store.put("t/doomed/1.png", b"go", "image/png")

    # Act
    reaped = await store.delete_prefix("t/doomed/")

    # Assert
    assert reaped == 2
    assert await store.open(kept) == b"keep"


async def test_deleting_a_prefix_nothing_wrote_is_zero_and_not_an_error() -> None:
    """Deletion is idempotent, so a fan-out re-run after a partial failure can finish the job."""
    # Act / Assert
    assert await InMemoryBlobStore().delete_prefix("t/nothing/") == 0


async def test_it_reports_what_it_removed_by_kind_when_a_source_is_deleted() -> None:
    """The stranger joins `weft delete`'s fan-out by satisfying `SourceDeletable`, declaring
    nothing — and answers in the per-kind vocabulary weft's task 9.3 opened up."""
    # Arrange
    store = InMemoryBlobStore()
    source = SourceId("/corpus/report.pdf")
    await store.put_for_source(source, ordinal=0, data=b"a", media_type="image/png")
    await store.put_for_source(source, ordinal=1, data=b"b", media_type="image/png")

    # Act
    removed = await store.delete_source(source)

    # Assert
    assert removed.node_count == 0
    assert dict(removed.removed) == {"blob": 2}
