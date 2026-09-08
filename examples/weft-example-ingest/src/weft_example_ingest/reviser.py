"""`ExampleStoredCountReviser` — a stranger's `Revisable`, ledger task **10.23**.

Fitness function 9 clause (c) is why this exists: a capability the first-party packs have and
an out-of-tree pack cannot reach is the privileged path requirement 4 forbids, and this pack is
the stranger. `weft_index.contract.Revisable` is the contract grilling session **G15**'s *Read*
face settled — a stage that revises what is **already stored**, not only the payload it was
handed — and what it does that an `Expander` may not is read the corpus.

**The read is `ctx.require(NodeStore)` and nothing else**, which is the whole of the route G13
settled for `reconcile`: the primary store, out of the context, no new type and no kernel line.
This class never imports `Revisable`; it satisfies it structurally, the same path every plugin
in this pack takes.

What it *does* with the corpus is deliberately the smallest honest thing — it attaches, to each
node it was handed, how many nodes the store already held when this run began. A first-party
`adrap` uses the same read to cluster a new document into an existing tree; the point a
stranger has to prove is that the read is reachable at all, not that it is clever.
"""

from collections.abc import Sequence

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Node, NothingToProduce, Outcome, Produced
from weft_store.contract import NodeStore

#: The name this reviser is registered and selectable under — see `weft_example_ingest.register`.
NAME = "example-stored-count"


class StoredCount(ExtModel):
    """How many nodes the corpus already held when the run that produced this node began."""

    __namespace__ = "weft-example-ingest-stored-count"
    __schema_version__ = "1.0.0"

    before: int


class ExampleStoredCountReviser:
    """Reads the corpus through the context, and states what it found on every node it returns.

    Satisfies `weft_index.contract.Revisable` structurally — this class never imports it.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        if not payload:
            return NothingToProduce(reason="no node to revise")
        store = ctx.require(NodeStore)
        before = await store.count()
        return Produced(value=tuple(node.with_ext(StoredCount(before=before)) for node in payload))
