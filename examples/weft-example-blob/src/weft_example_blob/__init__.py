"""A stranger's blob-store pack — proof of weft's fitness function 9, clause (c).

Nothing under weft's own `packages/` or `testing/` names this distribution, this module, or the
plugin name below. It is installed from a wheel into an environment that cannot see weft's source
tree, and it registers against a contract it did not write, through the one public entry point
weft's own first-party packs use — no shortcut, no private import path.

`docs/07-extension-cost.md` §1 names the canonical files: this one, the implementation
(`memory_store.py`), the `pyproject.toml` beside them and this pack's own tests. There is no
fifth: a pack implementing somebody else's contract writes no `contract.py`.
"""

from pydantic import BaseModel, ConfigDict

from weft_blob import BlobStore
from weft_example_blob.memory_store import InMemoryBlobStore, UnknownBlobError
from weft_kernel.discovery import Disclosure, PackRegistrar

#: This pack keeps its bytes in a dict — it reaches nothing outside the process, and says so
#: rather than leaving an operator to infer it from silence. `02` §2 → *The trust model*.
DISCLOSURE = Disclosure(
    network=(),
    filesystem=(),
    subprocess=(),
    note=(
        "Keeps blob bytes in memory for the life of the process and writes nothing anywhere. "
        "An example pack, not a store to point a corpus at."
    ),
)


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `InMemoryBlobStore` as `"example-blob"` for weft's `BlobStore` contract."""
    del settings
    registrar.add(BlobStore, "example-blob", InMemoryBlobStore)


__all__ = [
    "DISCLOSURE",
    "InMemoryBlobStore",
    "Settings",
    "UnknownBlobError",
    "register",
]
