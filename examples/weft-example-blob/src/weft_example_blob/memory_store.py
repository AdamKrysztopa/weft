"""`InMemoryBlobStore` — a stranger's `BlobStore`, keeping bytes in a dict.

Satisfies `weft_blob.contract.BlobStore` **structurally**: this module never imports the
Protocol, which is the same path `weft_example_chunker.WordChunker` takes for `Chunker` and the
path weft's own `docs/02-extension-model.md` describes for any third-party plugin.

It is deliberately not a second filesystem store. A `BlobStore` whose second implementation
keeps nothing on disk is the cheapest proof the contract is about *a keyspace of bytes* and not
about a directory — and weft's own `docs/11-multimodal.md` names a `bytea`-in-Postgres backend
as something the contract must admit without being changed. If a dict can satisfy it, so can a
column.

It also implements `delete_source`, so it joins `weft delete`'s fan-out by capability with
nothing declared, and answers in the per-kind vocabulary weft's `Removed.removed` opened up: a
blob store that reaped forty blobs and removed no node says exactly that.
"""

from weft_kernel.errors import WeftError
from weft_kernel.payload import SourceId
from weft_store import Removed

#: This store's own uri scheme. Nothing in the contract fixes one — `put` answers with whatever
#: address `open` will accept back, and that is the whole of the promise.
_SCHEME = "memory:"


class UnknownBlobError(WeftError):
    """`open` was asked for a uri this store never wrote.

    A `WeftError` rather than a `KeyError`, because a stranger's pack raising a bare builtin
    gives an operator nothing to act on — and never an empty `bytes`, which would be
    indistinguishable from a real empty blob.
    """


class InMemoryBlobStore:
    """Every blob this process was handed, by key. Nothing is persisted and nothing is shared
    between instances — which is the point: a conformance subject with no environment.
    """

    def __init__(self, config: object = None) -> None:
        del config  # a service takes no stage configuration; it has no pipeline position
        self._blobs: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, media_type: str) -> str:
        del media_type  # carried on a `BlobRef`, not by this contract's own methods
        self._blobs[key] = data
        return f"{_SCHEME}{key}"

    async def open(self, uri: str) -> bytes:
        key = self._key_from_uri(uri)
        if key not in self._blobs:
            raise UnknownBlobError(f"no blob was ever put at {uri!r} in this store")
        return self._blobs[key]

    async def delete_prefix(self, prefix: str) -> int:
        doomed = [key for key in self._blobs if key.startswith(prefix)]
        for key in doomed:
            del self._blobs[key]
        return len(doomed)

    async def delete_source(self, source_id: SourceId) -> Removed:
        """Every blob whose key contains this source's digest segment, reaped and counted.

        This store derives no keys of its own — `put_for_source` below is the one place it does,
        and it goes through `weft_blob.keys` so that a stranger's store and the shipped one
        cannot disagree about where one source's blobs live.
        """
        from weft_blob.keys import source_prefix

        tenants = {key.split("/", 1)[0] for key in self._blobs if "/" in key}
        removed = 0
        for tenant_id in sorted(tenants):
            removed += await self.delete_prefix(
                source_prefix(tenant_id=tenant_id, source_id=source_id)
            )
        return Removed(source_id=source_id, node_count=0, removed={"blob": removed})

    async def put_for_source(
        self, source_id: SourceId, *, ordinal: int, data: bytes, media_type: str
    ) -> str:
        """A convenience this pack's own tests use — not part of the contract, and named so.

        A real extractor composes its key through `weft_blob.keys.blob_key` and calls `put`;
        this wraps the same two lines so the test below reads as what it is measuring.
        """
        from weft_blob.keys import blob_key

        key = blob_key(tenant_id="t", source_id=source_id, ordinal=ordinal, extension="bin")
        return await self.put(key, data, media_type)

    def _key_from_uri(self, uri: str) -> str:
        if not uri.startswith(_SCHEME):
            raise UnknownBlobError(f"{uri!r} is not a uri this store ever produced")
        return uri.removeprefix(_SCHEME)
