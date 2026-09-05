"""First-party storage pack.

Publishes the store contract family settled in G4, in `contract.py` —
`NodeStore` and `VectorSearch` at Phase 0 (`docs/06-phase-0-build.md` step
7 scopes the family to the two capabilities Phase 0 has a built-in for),
`TextSearch` at Phase 2 task 2.5 and `MetadataFilter` at task 2.6, each when a
store implementing it arrived, and `SourceDeletable` and `Reconcilable` at
tasks 5.1a and 5.1b — the two whose implementors are mostly *not* stores, so
that deleting a source reaches every pack holding data derived from it, and so
that what deletion missed converges later. Every one of them is derived at registration by
`isinstance` rather than declared. What a `Filter` may name, and which
operator each kind of field admits, is `fields.py` — published beside the
family because two stores translating a filter must not come to disagree about
what it means. pgvector is the floor. `register()` and the built-in pgvector
store (`pgvector_store.py`) arrive at step 8.

**Every capability Protocol is re-exported here, not only from `contract`.**
A capability nothing registers under a name is found by walking this module's
`__all__` — that is how `weft_cli.contract_reference` picks `VectorSearch` up
beside `NodeStore`, and how a run assembler asks what capabilities this pack's
family actually contains. One exported from `contract` alone is invisible to
both, with no test to notice.
"""

from weft_kernel.discovery import Disclosure
from weft_store.contract import (
    FILTER_AST_VERSION,
    RECONCILE_REPORT_SCHEMA_VERSION,
    STORE_CONTRACT_VERSION,
    Cursor,
    Filter,
    FilterOp,
    FilterValue,
    MetadataFilter,
    NodeStore,
    Page,
    Reconcilable,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
    Scored,
    SourceDeletable,
    SourceRecord,
    SourceStatus,
    TextSearch,
    UnhandledFilterOpError,
    VectorSearch,
)
from weft_store.fields import (
    FieldKind,
    FieldPath,
    FilterOpMismatchError,
    NodeField,
    UnaddressableFieldError,
    field_for,
    parse_field_path,
)
from weft_store.pgvector_store import (
    PgVectorSettings,
    PgVectorStore,
    TextQueryMode,
    TextRank,
    register,
)

# Re-exported because `docs/02-extension-model.md` §1 names it as the call a pack shipping its own
# `ExtModel` makes so its nodes survive a round trip through a store. A documented extension point
# reachable only through a submodule path is a documented extension point that will be got wrong.
# `register_from_reports` — task 5.2g — is the generic consumer `weft-cli` calls once, after
# `discover()`, so a pack author's own `register()` calling `registrar.add_ext_model` is the only
# call most packs ever need to make; `register_ext_model` stays published for the caller that
# builds a registry without running full discovery (a test, `docs/02`'s own worked example).
from weft_store.rehydrate import register_ext_model, register_from_reports, rehydrate_ext

#: What this pack touches — ledger task **6.31**, `02` §2 → *The trust model*.
#:
#: **It lives here and not in `pgvector_store`** because the kernel reads `DISCLOSURE` off the
#: module a pack's entry point names, and `weft-store`'s is `weft_store:register` — the package,
#: not the module `register` is defined in.
#:
#: `psycopg` opens a socket, so this pack reaches outward whether or not the database is on the
#: same machine; `[packs.store] dsn` decides where, and a DSN is exactly the kind of concrete
#: string `02` §2 asks a disclosure to carry rather than a boolean ("a hostname is information,
#: `network: true` is noise"). The credential inside it is never printed — `dsn` is a `SecretStr`
#: and this names the setting, not its value. Informational only: `02` §2 is explicit that a
#: disclosure is "a disclosure to the operator, never a claim weft checks".
DISCLOSURE = Disclosure(
    network=("the PostgreSQL server [packs.store] dsn names (WEFT_DATABASE_URL by default)",),
    filesystem=(),
    subprocess=(),
    note=(
        "Reads and writes node content, embeddings and source records in PostgreSQL with "
        "pgvector, creating its own tables on first use. This is where an indexed corpus lives, "
        "so everything indexed is stored there in full."
    ),
)

__all__ = [
    "FILTER_AST_VERSION",
    "RECONCILE_REPORT_SCHEMA_VERSION",
    "STORE_CONTRACT_VERSION",
    "Cursor",
    "FieldKind",
    "FieldPath",
    "Filter",
    "FilterOp",
    "FilterOpMismatchError",
    "FilterValue",
    "MetadataFilter",
    "NodeField",
    "NodeStore",
    "Page",
    "PgVectorSettings",
    "PgVectorStore",
    "Reconcilable",
    "ReconcileEstimate",
    "ReconcileMode",
    "ReconcileReport",
    "Removed",
    "Scored",
    "SourceDeletable",
    "SourceRecord",
    "SourceStatus",
    "TextQueryMode",
    "TextRank",
    "TextSearch",
    "UnaddressableFieldError",
    "UnhandledFilterOpError",
    "VectorSearch",
    "field_for",
    "parse_field_path",
    "register",
    "register_ext_model",
    "register_from_reports",
    "rehydrate_ext",
]
