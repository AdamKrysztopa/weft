"""First-party Qdrant store pack — a backend in its own distribution, publishing nothing.

`weft-store` publishes the store contract family and this pack registers under
it; nothing here publishes a contract of its own, because nothing about one
engine needs one. It is a separate distribution for two reasons, and neither is
taxonomy. **A driver is a dependency**: putting `qdrant-client` in the pack that
publishes the contract would make every install of `NodeStore` pay for it. **And
a second backend must be exactly as ordinary as a stranger's** — `01` → *Runtime
shape*: "`weft-store-qdrant` is an ordinary add-on with no privileged status,
which means a customer can write a store for their own infrastructure without
asking." Registering it inside `weft-store` would leave the contract satisfied
only inside the package that publishes it, which is the guess ledger task 2.6
exists to remove.

**Three tiers, deliberately not four.** See `weft_qdrant.store` for why there is
no `TextSearch` here and why a shim to add one would be worse than the refusal.

**Registered through the same public `weft.packs` entry point a third party
uses**, with nothing extra for being first-party — fitness function 2.
"""

from functools import partial

from weft_kernel.discovery import Disclosure, PackRegistrar
from weft_qdrant.settings import QdrantSettings
from weft_qdrant.store import QdrantStore, VectorWidthMismatchError, to_qdrant_filter
from weft_store.contract import NodeStore

#: The one name this pack registers, spelled once so a document, a test and the registration
#: cannot disagree about it.
NAME = "qdrant"


#: What this pack touches — ledger task **6.31**, `02` §2 → *The trust model*.
#:
#: The address is `[packs.weft-qdrant] url`, defaulting to a local deployment, so the disclosure
#: names the setting and its default rather than pretending to know where an operator points it.
#: Informational only: `02` §2 is explicit that a disclosure is "a disclosure to the operator,
#: never a claim weft checks".
DISCLOSURE = Disclosure(
    network=("whatever [packs.weft-qdrant] url names — http://localhost:6333 by default",),
    filesystem=(),
    subprocess=(),
    note=(
        "Stores and searches node vectors in a Qdrant deployment, authenticating with "
        "[packs.weft-qdrant] api_key when one is set. Node content and embeddings are written to "
        "that deployment and read back from it."
    ),
)


def register(registrar: PackRegistrar, settings: QdrantSettings) -> None:
    """Register `QdrantStore` as `"qdrant"` for `NodeStore`.

    `settings` is bound in through `functools.partial`, exactly as `weft_store`
    binds its connection string, so `Runner.resolve`'s `entry.factory(spec.config)`
    call becomes `QdrantStore(settings, spec.config)` — the deployment from the
    pack's settings block, and a stage-level `with:` this store has no use for.
    """
    registrar.add(NodeStore, NAME, partial(QdrantStore, settings))


__all__ = [
    "NAME",
    "QdrantSettings",
    "QdrantStore",
    "VectorWidthMismatchError",
    "register",
    "to_qdrant_filter",
]
