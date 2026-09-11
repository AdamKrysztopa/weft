"""`FilesystemBlobStore` — the shipped `BlobStore`, over a plain directory. Ledger task `9.4`.

Three async methods and no pipeline position, over a root an operator names in
`[packs.blob] root`. What this module adds beyond the round trip:

**A blob root carries its own layout version, checked at open and refused on mismatch.** `S11`
(`docs/internal/README.md`) names the blob root the *seventh persistence surface*: `ExtModel.
__schema_version__` versions the `BlobRef` a `Node` carries, and says nothing about the layout
that reference resolves *through* on disk. The rule `S11` settles is one per persistence root a
pack owns outside the node store — carried in the root itself, checked at every operation that
touches it, and refused with a named remedy rather than guessed at, because guessing here means
reading somebody's bytes from a layout that is not the one that wrote them. `<root>/
.weft-blob-layout` is that carrier: a fresh root — one with no such file and no blobs — is
adopted rather than refused, because refusing an empty directory an operator just pointed this
pack at would make first use impossible.

**A key never escapes the root, checked here and not only in `weft_blob.keys`.** `keys.py`
derives every first-party key and cannot produce a traversal, but `put` and `delete_prefix` both
take a bare `str`, and a third-party caller may compose one by hand — so the refusal lives at the
boundary that would actually suffer a bad key, not only at the helper that is easy to use
correctly.

**Every filesystem call runs off the event loop, via `asyncio.to_thread`.** G6, and
`weft_pdf.pdf_layout`'s module docstring states the identical offload shape for CPU-bound work:
"a CPU-bound stage is still `async def` and offloads its own blocking work." This is a *service*
rather than a stage, so it passes through no seam wrap and nothing catches a blocking call on
its behalf — `weft_kernel.blocking.guard`, the same detector the seam installs for a stage, is
armed directly against this module's own tests instead.

**`delete_source` sums `delete_prefix` over every tenant directory under the root.** It receives
no `Context` and therefore no `tenant_id` — deleting a source means deleting it everywhere it
appears, exactly the shape `weft_store.pgvector_store.PgVectorStore.delete_source` already has
(it carries no tenant column at all: `DELETE FROM weft_nodes WHERE %s = ANY(sources)`). Walking
every tenant directory and reusing `delete_prefix` for each is what keeps this store from ever
disagreeing with itself about where a source's blobs live — the identical derived-key argument
`keys.py` makes for `put` and `delete_prefix` extended to a third caller.
"""

import asyncio
import shutil
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from weft_blob.contract import BlobUri
from weft_blob.keys import source_prefix
from weft_kernel.errors import WeftError
from weft_kernel.payload import SourceId
from weft_store import Removed

#: The layout this store writes and reads. Bumped whenever the on-disk shape of a root — the
#: key format, the layout marker itself, anything a reader would need to know to make sense of
#: an existing root — changes in a way an older reader would misinterpret.
BLOB_LAYOUT_VERSION = "1"

#: Hidden so it never collides with a tenant directory name (`keys._checked_tenant_id` refuses
#: any tenant id containing `/`, but nothing refuses `.weft-blob-layout` as one — this name is
#: simply never derived by `keys.blob_key`, which produces only digest and ordinal segments).
_LAYOUT_FILE_NAME = ".weft-blob-layout"


class BlobKeyRefusedError(WeftError):
    """A key or prefix is absolute, or contains a `..` segment — plain `WeftError`, not a member
    of the `UnresolvedNameError` family: nothing here is a name failing to resolve against an
    enumerable set of alternatives, the identical distinction
    `weft_cli.service_roles.DuplicateServiceRoleError`'s own docstring draws for its case. There
    is no `valid_options` to offer; the fix is composing a key that is a plain relative path.
    """


class BlobNotFoundError(WeftError):
    """`open` was asked for a uri nothing ever wrote, or that was removed outside this store.

    Never a silent `b""` — an empty answer here would be indistinguishable from a real empty
    blob, so a caller embedding it would never learn the difference.
    """


class BlobLayoutVersionError(WeftError):
    """The root's recorded layout version does not match `BLOB_LAYOUT_VERSION` — `S11`'s
    seventh-surface rule, enforced at the one place it can be: before this store reads or writes
    anything else in the root. Plain `WeftError`, for the identical reason `BlobKeyRefusedError`
    states: a version mismatch is two facts disagreeing, not a name failing to resolve.
    """


class FilesystemBlobSettings(BaseModel):
    """`[packs.blob] root` — required, with no default, following `[packs.store] dsn`'s own
    precedent (`weft_store.pgvector_store.PgVectorSettings.dsn`): a pack cannot invent where an
    operator's bytes live, so there is nothing sane to default to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    root: Path


class FilesystemBlobStore:
    """The shipped `BlobStore`. Satisfies the Protocol structurally — this class never imports
    it — exactly the path any third-party store pack takes, and additionally implements
    `delete_source` so it joins `weft delete`'s fan-out with nothing declared beyond that method.

    `put` on an existing key overwrites rather than versions. Keys are derived
    (`weft_blob.keys`), so a re-extraction of an unchanged source writes the same key again; the
    alternative is a root that grows without bound across every re-index, with no ledger saying
    which copy is the live one.
    """

    def __init__(self, settings: FilesystemBlobSettings, config: object = None) -> None:
        del config  # nothing at the stage level this service needs — it is not a stage
        self._root = settings.root

    async def put(self, key: str, data: bytes, media_type: str) -> BlobUri:
        del media_type  # carried in `BlobRef`, not by this contract's own methods
        path = self._checked_relative_path(key)
        return await asyncio.to_thread(self._put_sync, path, data)

    async def open(self, uri: BlobUri) -> bytes:
        path = self._path_from_uri(uri)
        return await asyncio.to_thread(self._open_sync, path, uri)

    async def delete_prefix(self, prefix: str) -> int:
        path = self._checked_relative_path(prefix)
        return await asyncio.to_thread(self._delete_prefix_sync, path)

    async def delete_source(self, source_id: SourceId) -> Removed:
        """Sum `delete_prefix` over every tenant directory under the root — see the module
        docstring. `node_count=0` is honest: this participant never touched a node.
        """
        tenant_ids = await asyncio.to_thread(self._tenant_ids_sync)
        removed = 0
        for tenant_id in tenant_ids:
            removed += await self.delete_prefix(
                source_prefix(tenant_id=tenant_id, source_id=source_id)
            )
        return Removed(source_id=source_id, node_count=0, removed={"blob": removed})

    def _checked_relative_path(self, value: str) -> Path:
        """Refuse a `str` that would resolve outside `self._root`, or name the root itself — see
        the module docstring's note that `keys.py` cannot be the only guard for a boundary
        strangers reach directly.

        The empty string is refused for its own reason: it resolves to the root, so
        `delete_prefix("")` would take every tenant and the layout marker with it. A caller that
        means *everything* can name what it means; an empty string arriving at a `destroy`-class
        operation is far more likely to be a variable nobody set.
        """
        if not value.strip("/"):
            raise BlobKeyRefusedError(
                "an empty blob key or prefix is refused: it names the configured root itself, "
                "and as a prefix it would reap every tenant in it. Name what is meant."
            )
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise BlobKeyRefusedError(
                f"{value!r} is refused: a blob key or prefix must be a relative path with no "
                f"'..' segment, so it cannot resolve outside the configured root"
            )
        return self._root / candidate

    def _path_from_uri(self, uri: BlobUri) -> Path:
        """The path a uri names, refused unless it lies inside this store's own root.

        **A `BlobUri` is data, not an instruction.** It reaches `open` from a `BlobRef` in a
        persisted node's `ext` — a row somebody else may have written — so resolving whatever
        path it names would make this method an arbitrary file read. `weft_kernel.payload.
        applicability._FactRef`'s docstring makes the identical argument one layer up, about a
        persisted class reference and `import`; the answer there and here is the same, which is
        to resolve only within what this process already owns and refuse everything else by
        name. Added 2026-09-06 at a review of the diff that first wrote this method, which
        checked the boundary on the writing side and not on the reading one.
        """
        prefix = "file://"
        text = str(uri)
        if not text.startswith(prefix):
            raise BlobNotFoundError(f"{uri!r} is not a uri this store ever produced")
        path = Path(text[len(prefix) :])
        root = self._root.resolve()
        if not path.resolve().is_relative_to(root):
            raise BlobKeyRefusedError(
                f"{uri!r} resolves outside {root}, the root [packs.blob] root names. A blob uri "
                f"is read back from a stored record, so this store resolves only inside its own "
                f"root and refuses anything else rather than reading it."
            )
        return path

    def _layout_path(self) -> Path:
        return self._root / _LAYOUT_FILE_NAME

    def _check_layout_sync(self, *, adopt: bool) -> None:
        """Read the root's recorded layout version and refuse a mismatch. A root with no
        recorded version yet is a fresh root: adopted (the version is written) when `adopt` is
        set — from `put`'s own write path — and left alone otherwise, since there is nothing to
        check a read-only operation against.
        """
        layout_path = self._layout_path()
        if layout_path.is_file():
            found = layout_path.read_text(encoding="utf-8").strip()
            if found != BLOB_LAYOUT_VERSION:
                raise BlobLayoutVersionError(
                    f"{self._root} was written by blob layout version {found!r}; this store is "
                    f"layout version {BLOB_LAYOUT_VERSION!r} and refuses to read or write a "
                    f"root a different layout produced. Point [packs.blob] root at a root this "
                    f"version wrote, or migrate this root's contents to the current layout "
                    f"before reusing it."
                )
            return
        if adopt:
            self._root.mkdir(parents=True, exist_ok=True)
            layout_path.write_text(BLOB_LAYOUT_VERSION, encoding="utf-8")

    def _put_sync(self, path: Path, data: bytes) -> BlobUri:
        self._check_layout_sync(adopt=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return BlobUri(f"file://{path}")

    def _open_sync(self, path: Path, uri: BlobUri) -> bytes:
        self._check_layout_sync(adopt=False)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise BlobNotFoundError(f"no blob was ever written at {uri!r}") from exc

    def _delete_prefix_sync(self, path: Path) -> int:
        self._check_layout_sync(adopt=False)
        if not path.is_dir():
            return 0
        removed = sum(1 for candidate in path.rglob("*") if candidate.is_file())
        shutil.rmtree(path)
        return removed

    def _tenant_ids_sync(self) -> tuple[str, ...]:
        self._check_layout_sync(adopt=False)
        if not self._root.is_dir():
            return ()
        return tuple(
            entry.name
            for entry in self._root.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )
