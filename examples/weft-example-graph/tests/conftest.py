"""This pack's own test setup — no Docker required for `test_extraction.py`/`test_enhancer.py`/
`test_register.py`; `test_store.py`/`test_retriever.py`/`test_commands.py` skip, with a reason,
against the same Postgres `docs/build-ledger.md`'s own conformance kit already needs
(`WEFT_DATABASE_URL`, `docker compose up -d` at the repository root).
"""

from weft_example_graph.payload import GraphData

from weft_store.rehydrate import register_ext_model

# `rehydrate_ext` (used by `weft_example_graph.store.GraphStore.get`/`.scan`) reads this pack's own
# namespace back off a shared, module-level registry — `weft_store.rehydrate`'s own module
# docstring — exactly as a real `weft` process would have it after `discover()` runs. A bare
# `uv run pytest` here never calls `discover()`, so this pack's own test suite registers it
# once, itself, the same explicit call `docs/02-extension-model.md` section 1 describes for
# any caller that "builds a registry without running full discovery."
register_ext_model(GraphData)
