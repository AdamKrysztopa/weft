"""Blob keys are derived, and derived from something safe to derive from. Ledger task `9.4`.

`docs/11-multimodal.md:213-217 'packages/weft-'` settles that keys are **derived, never allocated**:
`{tenant_id}/{source_id}/{ordinal}.{ext}`, so a cascade delete is one prefix
(`source_prefix`) and no ledger table exists to drift between what was written and what
`delete_prefix` is asked to reap.

**The `source_id` segment is a hex digest of the source id, not the source id itself, and
that is a repair rather than a preference.** Measured 2026-09-06 by indexing a directory
through the shipped binary and reading `weft_sources`: a real `SourceId` is
`/private/tmp/.../corpus/doc.txt` — `SourceId` is `NewType("SourceId", str)` and constrains
nothing about its shape, and the ingest path assigns it the source's own URI. Interpolating
that literally into a key puts a leading `/` and every interior separator into a storage
path, and a source whose id happens to contain `..` walks a write straight out of whatever
root an operator configured, with nobody attacking anything (`docs/lessons.md` `L9.53`).

Every property the layout was designed for survives the repair unchanged: the key is still
derived rather than allocated, `blob_key` is still the one function that produces it, and
`source_prefix` derives the identical segment through the same digest — so `put` and
`delete_prefix` cannot disagree about where one source's blobs live, which is the whole
reason a cascade delete can be a single prefix at all. What is given up is a human-readable
path on disk, which nothing in the design actually asked for.

`tenant_id` is **not** digested. An operator reads it directly off the filesystem layout —
`weft_blob.filesystem_store.FilesystemBlobStore.delete_source` walks the root by tenant
directory name — so it is *checked* instead of hashed: an empty tenant id, or one containing
`/` or `..`, is refused rather than silently folded into some other tenant's directory. A
digest would make that refusal impossible to state (two different tenant ids never collide by
construction, so there would be nothing to check), and a collision here is the one failure in
this module that loses data belonging to somebody else.
"""

import hashlib

from weft_kernel.payload import SourceId

#: Half of a sha256 hex digest (64 hex characters) truncated to 32. Collision-resistant enough
#: for the number of distinct sources any one tenant will ever hold — the property this design
#: needs is "two different source ids produce two different segments", not cryptographic
#: uniqueness against an adversary picking source ids to collide — and short enough that a key
#: printed by `weft plugins doctor` or listed on disk stays legible.
_DIGEST_PREFIX_LENGTH = 32


def _source_segment(source_id: SourceId) -> str:
    """The one place a `SourceId` becomes a storage-safe segment — see the module docstring."""
    return hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:_DIGEST_PREFIX_LENGTH]


def _checked_tenant_id(tenant_id: str) -> str:
    """Refuse, never sanitise — a silently rewritten `tenant_id` could fold two tenants into
    one directory, which is the one failure this module must never produce.
    """
    if not tenant_id or "/" in tenant_id or ".." in tenant_id:
        raise ValueError(
            f"tenant_id must be a single non-empty path segment with no '/' and no '..'; "
            f"got {tenant_id!r}"
        )
    return tenant_id


def blob_key(*, tenant_id: str, source_id: SourceId, ordinal: int, extension: str) -> str:
    """`{tenant_id}/{digest of source_id}/{ordinal}.{extension}` — always three segments.

    Deterministic and side-effect-free: the same four arguments always produce the same key,
    which is what lets a re-extraction of an unchanged source overwrite its own blobs rather
    than accumulate duplicates nothing ever reaps.
    """
    checked_tenant_id = _checked_tenant_id(tenant_id)
    if ordinal < 0:
        raise ValueError(f"ordinal must not be negative; got {ordinal}")
    return f"{checked_tenant_id}/{_source_segment(source_id)}/{ordinal}.{extension}"


def source_prefix(*, tenant_id: str, source_id: SourceId) -> str:
    """The prefix every blob `blob_key` derives for this `(tenant_id, source_id)` pair lies
    under — derived through the identical digest `blob_key` uses, so the two can never
    disagree about where a source's blobs live.
    """
    checked_tenant_id = _checked_tenant_id(tenant_id)
    return f"{checked_tenant_id}/{_source_segment(source_id)}/"
