"""The `BlobStore` contract — published here, never by the kernel. Ledger task `9.4`.

A **service, not a stage**: no pipeline position, no `run`, no `Stage[In, Out]` base
(`docs/11-multimodal.md:199-203 'weft-blob — a'`). `weft_kernel.seam` wraps stages and `flush` and
nothing
else, which is why nothing on this contract ever produces a `Node` and why the bytes reaching
it never enter the payload — a `weft_vision.Describer` reads them, a chunker or renderer never
does.

**Published from its own pack, and deliberately not from `weft_store`.**
`weft_engine.contract_reference.capability_siblings` enumerates a contract pack's public module, so
a `BlobStore` exported from `weft_store` would be advertised as a store-family capability that no
node
store satisfies — `weft plugins doctor` would then report every node store as missing a capability
it was never meant to have. `weft_blob` is a pack of its own inside the `weft-rag` distribution, the
module home `docs/internal/build-ledger.md` task 9.4 leaves to this brief; `11` §3's revision log
settles that it ships inside the wheel rather than as one of its own.

It joins `weft delete`'s fan-out by satisfying `weft_store.SourceDeletable` structurally and
declaring nothing on this Protocol at all — `weft_cli.fanout.participants_for` walks every
registered contract and asks `issubclass`, so an implementation that adds `delete_source`
participates with no edit here.

`version` is readable off the class (`BlobStore.version`) but carries no `isinstance` weight — the
identical `if TYPE_CHECKING:` / assign-after-the-class-body split `weft_extract.contract`
(`:44-56`) and `weft_store.contract.NodeStore` already use, for the identical reason: `Protocol`
computes `__protocol_attrs__` once, by walking every attribute present in the class body when it
closes, so a `ClassVar` written directly in the body would make `version` a required structural
member and fail a third-party implementation that never restates it.
"""

from typing import TYPE_CHECKING, ClassVar, NewType, Protocol, Self, runtime_checkable

from weft_kernel.context import ServiceRole
from weft_store.contract import TargetName

#: Fitness function 6's subject for this contract — a mechanical fact, read by AST from this
#: file. What a version *means* is G9's, still open; this constant states the shape only.
BLOB_CONTRACT_VERSION = "1.0.0"

#: A blob's address, on the identical footing `weft_kernel.payload.ids.SourceId` and `NodeId`
#: already have: `NewType` over `str`, so it compares, hashes and serialises exactly like the
#: string it is, and a type checker still flags a `NodeId` handed where a `BlobUri` was asked for.
BlobUri = NewType("BlobUri", str)


@runtime_checkable
class BlobStore(Protocol):
    """Store bytes under a caller-composed key, read them back by uri, and reap a prefix.

    Puts bytes under a caller-composed key, opens them back by the returned uri, and reaps a
    prefix on delete. Three methods, and every one of them the whole surface a plugin owes.

    **`put` takes a plain `str` key, not a `weft_blob.keys.BlobUri` or a `SourceId`-shaped
    argument** — the module publishing this contract has no opinion on how a key is derived;
    `weft_blob.keys` is one caller's answer, not part of the capability. A caller composing its
    own key is exactly the case `weft_blob.filesystem_store`'s own boundary check exists for.

    **`media_type` on `put` and nowhere else.** `open` returns the bytes a caller already knows
    the shape of — the `BlobRef.media_type` field carries that fact durably — so the contract
    does not ask a store to remember or return it a second time.
    """

    if TYPE_CHECKING:
        #: Readable as `BlobStore.version`, invisible to `isinstance` — see the module
        #: docstring. Assigned for real below, after the class body closes.
        version: ClassVar[str]

    async def put(self, key: str, data: bytes, media_type: str) -> BlobUri:
        """Store `data` under `key`.

        Args:
            key: The caller-composed key the bytes are stored under.
            data: The bytes to store.
            media_type: What the bytes are; recorded by the caller's `BlobRef`, not returned.

        Returns:
            The uri `open` reads the bytes back by.
        """
        ...

    async def open(self, uri: BlobUri) -> bytes:
        """Read back the bytes a `put` stored.

        Args:
            uri: A uri this store returned from `put`.

        Returns:
            The stored bytes.
        """
        ...

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every blob whose key lies under `prefix`.

        Args:
            prefix: The key prefix to reap.

        Returns:
            How many blobs were deleted.
        """
        ...


BlobStore.version = BLOB_CONTRACT_VERSION


@runtime_checkable
class BlobTargetHolding(Protocol):
    """A blob store that keeps each index target's bytes apart.

    A blob store that keeps each index target's bytes apart — ledger **34.12**, published by
    carried repair **R34.9** so a stranger's store joins `weft target drop`.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def bind_target(self, target: TargetName) -> Self:
        """Return a handle over the same store whose reads and writes land in `target`'s own space.

        Args:
            target: The index target to bind.

        Returns:
            A second handle, bound to `target`.
        """
        ...

    async def drop_target(self, target: TargetName) -> int:
        """Delete everything `target` holds.

        Args:
            target: The index target whose bytes are removed.

        Returns:
            How many blobs were deleted.
        """
        ...


BlobTargetHolding.version = BLOB_CONTRACT_VERSION

#: Ledger task **9.0** — this pack's own declaration that `[services].blob` selects a
#: `BlobStore`. A plain module-level constant beside the Protocol, never a `ClassVar` on
#: `BlobStore` itself, for the identical reason `version` above is assigned after the class body:
#: see `weft_store.contract.STORE_ROLE`'s own note.
BLOB_ROLE = ServiceRole(key="blob", contract=BlobStore)
