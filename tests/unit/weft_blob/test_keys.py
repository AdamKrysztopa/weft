"""Blob keys are derived, and derived from something safe to derive from — ledger task `9.4`.

`docs/11-multimodal.md:213-217 'packages/weft-'` settles that keys are **derived, never allocated**:
`{tenant_id}/{source_id}/{ordinal}.{ext}`, so a cascade delete is one prefix and no ledger table
exists to drift. That argument is what removes a whole component from this phase, and it survives
here unchanged.

**What did not survive is interpolating `source_id` literally.** Measured 2026-09-06 by indexing a
directory through the shipped binary and reading `weft_sources`: a real `SourceId` is
`/private/tmp/.../corpus/doc.txt`. `SourceId` is `NewType("SourceId", str)` and constrains nothing,
and the ingest path assigns the source's URI — so the layout as written puts a leading `/` and every
interior separator into a storage key, and a source whose path contains `..` walks out of the
configured root without anyone attacking anything (`docs/internal/lessons.md` `L9.53`).

So the source segment is a **hex digest of the source id**. Every property the design argued for is
kept: the key is derived, one function derives it, and `source_prefix` derives the same segment the
same way, so `put` and `delete_prefix` cannot disagree about where a source's blobs live. What is
given up is a human-readable path on disk, which nothing in the design asked for.
"""

import hashlib

import pytest

from weft_blob.keys import blob_key, source_prefix
from weft_kernel.payload import SourceId


def test_a_key_is_the_same_every_time_it_is_derived() -> None:
    """Derived, never allocated: no counter, no table, no first-writer-wins."""
    # Arrange
    tenant, source, ordinal = "tenant-a", SourceId("/corpus/report.pdf"), 3

    # Act
    first = blob_key(tenant_id=tenant, source_id=source, ordinal=ordinal, extension="png")
    second = blob_key(tenant_id=tenant, source_id=source, ordinal=ordinal, extension="png")

    # Assert
    assert first == second


def test_a_key_lies_under_its_own_source_prefix() -> None:
    """The property cascade delete rests on — one prefix reaches every blob of one source."""
    # Arrange
    tenant, source = "tenant-a", SourceId("/corpus/report.pdf")

    # Act
    keys = [
        blob_key(tenant_id=tenant, source_id=source, ordinal=n, extension="png") for n in (0, 7)
    ]
    prefix = source_prefix(tenant_id=tenant, source_id=source)

    # Assert
    assert all(key.startswith(prefix) for key in keys)


def test_two_sources_do_not_share_a_prefix() -> None:
    """Otherwise deleting one source reaps another's blobs, which is the worst outcome here."""
    # Act
    first = source_prefix(tenant_id="tenant-a", source_id=SourceId("/corpus/a.pdf"))
    second = source_prefix(tenant_id="tenant-a", source_id=SourceId("/corpus/b.pdf"))

    # Assert
    assert first != second
    assert not first.startswith(second)
    assert not second.startswith(first)


def test_two_tenants_do_not_share_a_prefix() -> None:
    """`tenant_id` is on the passport and this is the first place it becomes durable."""
    # Act
    first = source_prefix(tenant_id="tenant-a", source_id=SourceId("/corpus/a.pdf"))
    second = source_prefix(tenant_id="tenant-b", source_id=SourceId("/corpus/a.pdf"))

    # Assert
    assert first != second


@pytest.mark.parametrize(
    "source_id",
    [
        "/private/var/corpus/doc.txt",
        "../../etc/passwd",
        "a/b/c",
        "..",
        "with spaces and é",
    ],
)
def test_a_source_id_that_is_a_path_produces_one_flat_safe_segment(source_id: str) -> None:
    """The measured case, and the reason the segment is a digest at all.

    Whatever a source id turns out to be, its segment carries no separator and no traversal — a
    key is a name in a keyspace, never a path a caller composed.
    """
    # Act
    key = blob_key(tenant_id="tenant-a", source_id=SourceId(source_id), ordinal=0, extension="png")

    # Assert
    segments = key.split("/")
    assert segments[0] == "tenant-a"
    assert len(segments) == 3, f"expected tenant/source/name, got {segments}"
    assert ".." not in segments


def test_the_source_segment_is_a_digest_of_the_whole_source_id() -> None:
    """Stated as the fact rather than as a format: two ids differing anywhere differ here.

    Asserted against `hashlib` rather than against a literal, so this pins *that* the whole id is
    digested and not which prefix length someone chose.
    """
    # Arrange
    source = SourceId("/corpus/report.pdf")

    # Act
    segment = source_prefix(tenant_id="tenant-a", source_id=source).split("/")[1]

    # Assert
    assert hashlib.sha256(source.encode("utf-8")).hexdigest().startswith(segment)


def test_a_tenant_id_that_is_not_a_safe_segment_is_refused_loudly() -> None:
    """`tenant_id` is *not* digested — an operator reads it on disk — so it is checked instead.

    A silent sanitisation would make two tenants collide into one directory, which is the one
    failure in this module that loses data belonging to somebody else.
    """
    # Act / Assert
    with pytest.raises(ValueError, match="tenant"):
        blob_key(
            tenant_id="../escape", source_id=SourceId("/corpus/a.pdf"), ordinal=0, extension="png"
        )


def test_a_negative_ordinal_is_refused() -> None:
    """An ordinal is a position an extractor assigned; a negative one is a bug upstream."""
    # Act / Assert
    with pytest.raises(ValueError, match="ordinal"):
        blob_key(
            tenant_id="tenant-a", source_id=SourceId("/corpus/a.pdf"), ordinal=-1, extension="png"
        )
