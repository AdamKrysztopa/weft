"""First-party blob storage pack. Ledger task `9.4`.

Publishes the `BlobStore` contract, in `contract.py` — the Protocol and its version, per the
canonical-file convention `docs/07-extension-cost.md` §1 sets for a brand new contract.
Registered through the public entry point, with no shortcut a third party lacks — fitness
function 2. `register()` and the built-in filesystem store (`filesystem_store.py`) arrive
together at this task.

**`BlobRef` reaches rehydration through `register()` itself**, exactly the way `weft_pdf`'s
own `__init__.py` docstring states for `PdfPages`: `register()` calls
`registrar.add_ext_model(BlobRef)`, the same call it makes for `registrar.add(BlobStore, ...)`.
`PackRegistrar` and `ExtModel` are both kernel-owned, so this costs the dependency this pack
would otherwise refuse nothing at all.
"""

from functools import partial
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from weft_blob.contract import BLOB_CONTRACT_VERSION, BLOB_ROLE, BlobStore, BlobUri
from weft_blob.filesystem_store import (
    BLOB_LAYOUT_VERSION,
    BlobKeyRefusedError,
    BlobLayoutVersionError,
    BlobNotFoundError,
    FilesystemBlobSettings,
    FilesystemBlobStore,
)
from weft_blob.payload import BlobRef
from weft_kernel.discovery import Disclosure, PackRegistrar


class Settings(BaseModel):
    """`weft-blob`'s pack settings: one required field, following `[packs.store] dsn`'s
    precedent — a pack cannot invent where an operator's bytes live, so `root` has no default.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    root: Path


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `FilesystemBlobStore` as `"filesystem"` for `BlobStore`, and `BlobRef` as this
    pack's own `ExtModel` — the module docstring.

    `[services].blob` is declared by this pack's module-level `SERVICE_ROLES` below, not here —
    ledger task **9.0**. It is read before settings are validated, so the key still exists on a
    machine where `[packs.blob] root` is unset and this function never runs.

    **`functools.partial`, and a closure will not do.** `weft_kernel.registry.unwrap_factory`
    peels a `partial` to reach the class a factory constructs, and peels nothing else — its own
    docstring says a plugin needing pack settings "has only one shape available to it". Every
    reader that inspects a *class* rather than a constructed instance depends on that, and
    `weft_cli.fanout.participants_for` is one: bound in a closure, this store registers fine,
    resolves fine, and is silently absent from `weft delete`'s fan-out, so a source's blobs are
    never reaped. Found by running the binary — `weft delete` named one participant where it
    should have named two — while forty-four unit tests that construct `FilesystemBlobStore`
    directly all passed (`docs/internal/lessons.md` `L9.55`).
    """
    filesystem_settings = FilesystemBlobSettings(root=settings.root)
    registrar.add(BlobStore, "filesystem", partial(FilesystemBlobStore, filesystem_settings))
    registrar.add_ext_model(BlobRef)


#: Ledger task **9.0** — read by `weft_kernel.discovery._read_service_roles` at import time,
#: before settings are validated, exactly where `DISCLOSURE` below is read. Module-level rather
#: than buffered through `register()` because which `[services]` key this pack declares is a
#: static fact about the pack, not something settings validation should gate — see
#: `weft_store.__init__.SERVICE_ROLES`'s identical note.
SERVICE_ROLES = (BLOB_ROLE,)

#: What this pack touches — `02` §2 → *The trust model*. `filesystem` names the setting rather
#: than a boolean: `[packs.blob] root` is exactly the kind of concrete fact `02` §2 asks a
#: disclosure to carry ("a hostname is information, `network: true` is noise") — here, a
#: directory rather than a hostname.
DISCLOSURE = Disclosure(
    network=(),
    filesystem=("[packs.blob] root — every blob a multimodal extractor produces is written here",),
    subprocess=(),
    note=(
        "Reads and writes blob bytes (figures, tables, any non-text asset a `BlobRef` points "
        "at) as plain files under the configured root, creating the root and its own layout "
        "marker on first use."
    ),
)


__all__ = [
    "BLOB_CONTRACT_VERSION",
    "BLOB_LAYOUT_VERSION",
    "BLOB_ROLE",
    "BlobKeyRefusedError",
    "BlobLayoutVersionError",
    "BlobNotFoundError",
    "BlobRef",
    "BlobStore",
    "BlobUri",
    "DISCLOSURE",
    "FilesystemBlobSettings",
    "FilesystemBlobStore",
    "SERVICE_ROLES",
    "Settings",
    "register",
]
