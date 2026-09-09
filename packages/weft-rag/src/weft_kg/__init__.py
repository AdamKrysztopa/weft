"""`weft_kg` — publishes the graph traversal contract. Ledger task **11.4**.

Publishes `GraphTraversal`, in `contract.py`, and nothing else: no store, no retriever, no
registration, no pipeline. Those are later tasks — 11.5 registers a `GraphTraversal`
implementation, 11.8 designs the table an `Entity` is actually kept in.

**Declares no `register()` and no entry point.** A `register()` here, with nothing yet to
register, would be a producing side with no consuming side — `docs/lessons.md` L5.15's shape.
This module exists so that a pack implementing `GraphTraversal` — first-party or a stranger —
depends on the pack that publishes the contract it implements, exactly as `02` §1 requires.
"""

from weft_kg.contract import (
    GRAPH_ROLE,
    GRAPH_TRAVERSAL_CONTRACT_VERSION,
    Entity,
    EntityId,
    GraphTraversal,
)

__all__ = [
    "GRAPH_ROLE",
    "GRAPH_TRAVERSAL_CONTRACT_VERSION",
    "Entity",
    "EntityId",
    "GraphTraversal",
]
