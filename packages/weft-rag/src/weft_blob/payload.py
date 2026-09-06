"""`BlobRef` — the durable half of a blob, carried in `Node.ext`. Ledger task `9.4`.

`docs/11-multimodal.md` §2.4: bytes never enter a payload — a `BlobStore.put` call moves them
out, and only their address and shape survive into a `Node`. This is that address: a `BlobUri`
an `Extractor` or a later stage resolved through `BlobStore.put`, and the media type needed to
interpret the bytes `open` returns.

**Not transient.** `ExtModel.__transient__` defaults `False` and this class does not override
it: `weft_kernel.seam`'s transient-stripping only ever removes an `ExtModel` a pack marked as
never meant to leave the process it was built in (a decode buffer, a raw model response). A
`BlobRef` is the opposite of that — it is the *only* surviving pointer to bytes that already
left the payload for good, so stripping it here would leave an `IMAGE` or `TABLE` node in the
store with nothing behind it, unrecoverable rather than merely re-derivable.
"""

from weft_blob.contract import BlobUri
from weft_kernel.payload import ExtModel


class BlobRef(ExtModel):
    """`uri`: where `BlobStore.open` finds the bytes again. `media_type`: what they are.

    No `size` or checksum field — `FilesystemBlobStore` overwrites a re-extracted blob at its
    own derived key rather than versioning it (see that module's docstring), so a stored size
    would go stale exactly when the blob it describes changes and nothing here would notice.
    """

    __namespace__ = "weft-blob"
    __schema_version__ = "1.0.0"

    uri: BlobUri
    media_type: str
