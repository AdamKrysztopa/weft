"""The store conformance assertions are importable by a stranger — ledger task **26.4**.

`tests/integration/test_store_conformance.py` is **1,064 lines and 27 tests**, one suite run
against two backends that share no code, and it lives under `tests/` — so it is in no distribution
and the third party writing the second store that several deferred gates are waiting on cannot
import a line of it. Four documents promise a kit an author can install. `12-roadmap.md` §5e owns
the argument and withdrew the refusal that had stood since Phase 2.

**Two things make the published shape a fact rather than a preference, and both are measured.**

*`pytest` is not a runtime dependency of `weft-rag`.* Its `dependencies` are `weft-kernel`, `ftfy`,
`rouge-score`, `psycopg[binary]`, `pgvector`, `pyyaml`, `opentelemetry-api` and `packaging`. A
published module that imports `pytest` at module scope therefore fails to import for **every**
install — the same import-time defect §5e names for `qdrant_client`, arriving from a direction §5e
did not anticipate. So the assertions are **plain async functions that raise `AssertionError`**,
not a pytest base class and not a pytest plugin: either of those would make `pytest` a runtime
dependency of the wheel, or hide the kit behind an extra every user of it has to remember.

*`qdrant_client` is behind the `[qdrant]` extra and `psycopg` is not.* So the published half may
not name Qdrant at module scope, while pgvector's driver is already there for everyone. Neither
belongs in the kit regardless — the kit asks the contract's questions and never the backend's —
but it is why the containers, the DSNs, the collection setup and teardown stay in `tests/`.

**And the deepest coupling is the type.** `ConformanceStore = PgVectorStore | QdrantStore` is a
union of this repository's two concrete classes, not a protocol, and every one of the 27 tests
carries it. A stranger's store cannot satisfy that annotation whatever it implements. Un-picking it
is why this task and *"the assertions are importable"* are one task rather than two: the typing is
only assertable by handing a store that is neither backend to an assertion and watching it accept,
and until the extraction happens there is no assertion to hand it to.

**What this file does not test.** Whether a store is asked only the questions its capabilities can
answer is task `26.5`; the in-memory store is `26.6`. Here a double satisfies everything the one
check under test needs, and the check is called directly.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Final

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId
from weft_store import Page, Removed, SourceRecord
from weft_store.contract import STORE_CONTRACT_VERSION, Cursor

#: Modules the published kit may reach at import time. `psycopg` and `pgvector` are absent
#: deliberately even though they are runtime dependencies: the kit asks the contract's questions
#: and never the backend's, so naming a driver at all would be the coupling this task removes.
_FORBIDDEN_AT_IMPORT: Final[frozenset[str]] = frozenset(
    {"pytest", "qdrant_client", "psycopg", "pgvector", "weft_qdrant"}
)


class _DictStore:
    """A store that is neither `PgVectorStore` nor `QdrantStore` — the whole point.

    A dict and nothing else. It satisfies the part of `NodeStore` the check under test reaches,
    and it is deliberately **not** the in-memory store task `26.6` builds: that one is a shipped
    plugin with its own registration and its own vector search, and using it here would make this
    test depend on the task after it.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.records: dict[SourceId, SourceRecord] = {}

    async def add(self, nodes: Sequence[Node]) -> None:
        for node in nodes:
            self.nodes[node.id] = node

    async def flush(self) -> None:
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self.nodes[i] for i in ids if i in self.nodes)

    async def count(self) -> int:
        return len(self.nodes)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        return Page[Node](items=tuple(self.nodes.values()), next_cursor=None)

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def put_source(self, record: SourceRecord) -> None:
        self.records[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return self.records.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self.records.values())

    async def delete_source(self, source_id: SourceId) -> Removed:
        kept = {k: v for k, v in self.nodes.items() if source_id not in v.lineage.sources}
        gone = len(self.nodes) - len(kept)
        self.nodes = kept
        self.records.pop(source_id, None)
        return Removed(source_id=source_id, node_count=gone)

    version: ClassVar[str] = STORE_CONTRACT_VERSION


class _ForgetfulStore(_DictStore):
    """A store that accepts a node and does not keep it.

    The control. A published kit that passes for every store is worse than no kit, because a pack
    author reads a pass as proof and ships. This is the one double that separates *the checks run*
    from *the checks check*.
    """

    async def add(self, nodes: Sequence[Node]) -> None:
        del nodes


async def test_a_store_that_is_neither_backend_passes_a_published_check() -> None:
    """The happy path, and the property the whole phase exists for.

    Called directly rather than through pytest collection: a third party's store is not in this
    repository's suite, so what has to work is the *function*.
    """
    # Arrange
    from weft_store.conformance import (
        check_a_node_round_trips_through_the_store_with_its_lineage_and_its_ext,
    )

    store = _DictStore()

    # Act / Assert — a passing check returns None and raises nothing.
    assert (
        await check_a_node_round_trips_through_the_store_with_its_lineage_and_its_ext(store) is None
    )


async def test_a_store_that_loses_what_it_was_given_fails_the_check() -> None:
    """The error case, and the one that makes the test above mean something.

    `docs/internal/lessons.md` `L6.29`: a check that cannot fail is indistinguishable from one that
    is not looking. Here the cost of getting it wrong lands on somebody outside this repository,
    who has no way to tell a vacuous pass from a real one.
    """
    # Arrange
    from weft_store.conformance import (
        check_a_node_round_trips_through_the_store_with_its_lineage_and_its_ext,
    )

    store = _ForgetfulStore()

    # Act / Assert
    with pytest.raises(AssertionError):
        await check_a_node_round_trips_through_the_store_with_its_lineage_and_its_ext(store)


def test_the_kit_names_no_test_runner_and_no_backend_driver_at_import_time() -> None:
    """The constraint that decides the kit's shape, asserted rather than intended.

    Read from the module's own `import` statements rather than from `sys.modules` after importing
    it: by the time this test runs, `pytest` and `qdrant_client` are already imported by the suite
    around it, so an in-process check would pass against a module that imports both — `L5.6`'s
    one-source shape wearing an import's clothes.

    The list is not only about what is installable. `psycopg` and `pgvector` **are** runtime
    dependencies of `weft-rag` and are forbidden here anyway, because a kit that names a driver has
    stopped asking the contract's questions.
    """
    # Arrange
    source = Path(__file__).resolve().parents[3] / "packages/weft-rag/src/weft_store/conformance.py"
    assert source.is_file(), f"the published kit is not at {source}"

    # Act — every module named by a top-level import, dotted roots included.
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            imported.add(node.module.split(".")[0])

    # Assert
    assert not imported & _FORBIDDEN_AT_IMPORT, (
        f"the published kit imports {sorted(imported & _FORBIDDEN_AT_IMPORT)}. pytest is in no "
        "dependency list of weft-rag and qdrant_client is behind the [qdrant] extra, so either "
        "makes the kit unimportable for a real installation; a driver name means it has stopped "
        "asking the contract's questions"
    )


def test_the_forbidden_import_check_is_not_vacuous() -> None:
    """The walk finds imports at all, so the assertion above is about a real set.

    A parser that silently matched nothing would make that test pass for the worst possible
    reason, and the kit legitimately imports things — `weft_kernel.payload` at least — so an empty
    result is evidence of a broken walk rather than of a clean module.
    """
    # Arrange
    source = Path(__file__).resolve().parents[3] / "packages/weft-rag/src/weft_store/conformance.py"

    # Act
    tree = ast.parse(source.read_text(encoding="utf-8"))
    roots = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0
    }

    # Assert — it reads real imports, and the kernel's payload types are among them.
    assert "weft_kernel" in roots, f"the import walk found {sorted(roots)}"


def test_the_kit_publishes_the_corpus_its_checks_assert_over() -> None:
    """A check a caller cannot supply inputs to is a check a caller cannot debug.

    The three-node corpus is chosen so that every `FilterOp` separates the nodes differently, and a
    pack author reading a failure needs to see what was stored. Published beside the checks rather
    than hidden inside them.
    """
    # Arrange
    from weft_store.conformance import conformance_corpus

    # Act
    corpus = conformance_corpus()

    # Assert — three nodes, and they are distinguishable, which one node could not show.
    assert len(corpus) == 3
    assert len({node.content for node in corpus}) == 3
