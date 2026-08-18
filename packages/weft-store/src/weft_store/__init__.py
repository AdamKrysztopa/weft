"""First-party storage pack.

Publishes the store contract family settled in G4, in `contract.py` —
`NodeStore` and `VectorSearch` at Phase 0 (`docs/06-phase-0-build.md` step
7 scopes the family to the two capabilities Phase 0 has a built-in for);
`TextSearch` and `MetadataFilter` join later, derived at registration by
`isinstance` rather than declared. pgvector is the floor. `register()` and
the built-in pgvector store (`pgvector_store.py`) arrive at step 8.
"""

from weft_store.contract import (
    FILTER_AST_VERSION,
    STORE_CONTRACT_VERSION,
    Cursor,
    Filter,
    FilterOp,
    FilterValue,
    NodeStore,
    Page,
    Removed,
    Scored,
    SourceRecord,
    SourceStatus,
    VectorSearch,
)
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore, register

# Re-exported because `docs/02-extension-model.md` §1 names it as the call a pack shipping its own
# `ExtModel` makes so its nodes survive a round trip through a store. A documented extension point
# reachable only through a submodule path is a documented extension point that will be got wrong.
from weft_store.rehydrate import register_ext_model, rehydrate_ext

__all__ = [
    "FILTER_AST_VERSION",
    "STORE_CONTRACT_VERSION",
    "Cursor",
    "Filter",
    "FilterOp",
    "FilterValue",
    "NodeStore",
    "Page",
    "PgVectorSettings",
    "PgVectorStore",
    "Removed",
    "Scored",
    "SourceRecord",
    "SourceStatus",
    "VectorSearch",
    "register",
    "register_ext_model",
    "rehydrate_ext",
]
