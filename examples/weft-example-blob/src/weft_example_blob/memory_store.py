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

**Targets — carried repair R34.9.** `bind_target` hands back a second handle over the same
shared storage, bound to a target's own namespace: `default` keeps today's key/uri layout
exactly, so nothing already written changes shape; any other target's bytes live in their own
namespace of the same shared dict, addressed by a `.targets/<name>/` uri prefix the way
`weft_blob.filesystem_store.FilesystemBlobStore` addresses one by a `.targets/<name>/`
directory — so `drop_target` on one handle reaps only that namespace, and a uri any handle
produced still opens from any handle sharing the storage, because `open` resolves against the
shared object rather than against the handle's own binding.
"""

from typing import Self

from weft_kernel.errors import WeftError
from weft_kernel.payload import SourceId
from weft_store import DEFAULT_TARGET, Removed, TargetName, target_name

#: This store's own uri scheme. Nothing in the contract fixes one — `put` answers with whatever
#: address `open` will accept back, and that is the whole of the promise.
_SCHEME = "memory:"

#: A non-`default` target's own namespace is addressed under this uri segment — the identical
#: dot-prefixed convention `FilesystemBlobStore._TARGETS_DIR_NAME` uses, chosen so it can never
#: collide with a key `weft_blob.keys` derives.
_TARGETS_PREFIX = ".targets/"


class UnknownBlobError(WeftError):
    """`open` was asked for a uri this store never wrote.

    A `WeftError` rather than a `KeyError`, because a stranger's pack raising a bare builtin
    gives an operator nothing to act on — and never an empty `bytes`, which would be
    indistinguishable from a real empty blob.
    """


class TargetDropRefusedError(WeftError):
    """Refusal that keeps the live, untargeted blobs out of any target drop's reach.

    `drop_target` was asked to remove `default` — its blobs are the shared storage's own,
    not a target subtree this method owns the removal of, matching
    `FilesystemBlobStore.drop_target`'s own refusal.
    """


class InMemoryBlobStore:
    """Every blob this process was handed, by key, namespaced by target.

    Nothing is persisted and nothing is shared between instances that were not produced by one
    another's `bind_target` — which is the point: a conformance subject with no environment.
    """

    def __init__(
        self,
        config: object = None,
        *,
        _shared: dict[TargetName, dict[str, bytes]] | None = None,
        _target: TargetName = DEFAULT_TARGET,
    ) -> None:
        del config  # a service takes no stage configuration; it has no pipeline position
        self._shared: dict[TargetName, dict[str, bytes]] = (
            _shared if _shared is not None else {DEFAULT_TARGET: {}}
        )
        self._target = _target

    @property
    def _blobs(self) -> dict[str, bytes]:
        return self._shared.setdefault(self._target, {})

    async def bind_target(self, target: TargetName) -> Self:
        """Let an index run write a candidate target's blobs without touching the live ones.

        A second handle over the same shared storage, bound to `target`'s own namespace —
        see the module docstring.
        """
        validated = target_name(str(target))
        return type(self)(_shared=self._shared, _target=validated)

    async def drop_target(self, target: TargetName) -> int:
        """Reclaim a retired target's blobs for `weft target drop`, never the untargeted ones.

        Remove `target`'s whole namespace from the shared storage, returning how many blobs
        it held. `default` is refused: its blobs are the shared storage's own, not a namespace
        this method owns the removal of.
        """
        validated = target_name(str(target))
        if validated == DEFAULT_TARGET:
            raise TargetDropRefusedError(
                f"{validated!r} cannot be dropped through drop_target: default's blobs are the "
                "shared storage's own bytes, not a target namespace this method may remove"
            )
        doomed = self._shared.pop(validated, None)
        return 0 if doomed is None else len(doomed)

    async def put(self, key: str, data: bytes, media_type: str) -> str:
        """Keep `data` under `key` in this handle's namespace.

        Args:
            key: The caller-composed key.
            data: The bytes to keep.
            media_type: Unused; the caller's `BlobRef` carries it.

        Returns:
            The `memory://` uri `open` reads the bytes back by.
        """
        del media_type  # carried on a `BlobRef`, not by this contract's own methods
        self._blobs[key] = data
        if self._target == DEFAULT_TARGET:
            return f"{_SCHEME}{key}"
        return f"{_SCHEME}{_TARGETS_PREFIX}{self._target}/{key}"

    async def open(self, uri: str) -> bytes:
        """Read back the bytes a `put` kept.

        Args:
            uri: A uri `put` returned, from any handle over the same shared storage.

        Returns:
            The kept bytes.

        Raises:
            UnknownBlobError: Nothing was put at `uri` in this store.
        """
        target, key = self._target_and_key_from_uri(uri)
        blobs = self._shared.get(target, {})
        if key not in blobs:
            raise UnknownBlobError(f"no blob was ever put at {uri!r} in this store")
        return blobs[key]

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every blob in this handle's namespace whose key starts with `prefix`.

        Args:
            prefix: The key prefix to reap.

        Returns:
            How many blobs were deleted.
        """
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

    def _target_and_key_from_uri(self, uri: str) -> tuple[TargetName, str]:
        if not uri.startswith(_SCHEME):
            raise UnknownBlobError(f"{uri!r} is not a uri this store ever produced")
        rest = uri.removeprefix(_SCHEME)
        if rest.startswith(_TARGETS_PREFIX):
            remainder = rest.removeprefix(_TARGETS_PREFIX)
            raw_target, _, key = remainder.partition("/")
            return target_name(raw_target), key
        return DEFAULT_TARGET, rest
