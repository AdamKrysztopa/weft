"""Unit tests for `weft_cli.participation`.

Mirrors `packages/weft-rag/src/weft_cli/participation.py`. Task **6.18** widened the
`NodeStore` fan-out from the one store `[services] store` names to *"every `NodeStore` named
by a pipeline in the project's catalogue or by a persisted run record"* (`docs/02-extension-
model.md` §1 → *Extended by G13*); carried repair **R11.2** narrows the first half of that
sentence, and this file is where the two edges of the narrowing are checked.

**What changed, and why the old edge stopped holding.** 6.18's rule read the *whole* catalogue
— `weft_cli.pipeline_catalogue.full_catalogue`, which is every project-local document **plus
every document every installed pack contributes**. That inference — a store named by a shipped
pipeline is a store this project uses — held only while installing a store pack was a
deliberate act. `G19` folded `weft-qdrant` into the `weft-rag` wheel, so every install now
carries it, and the moment a shipped `index-qdrant` named `qdrant` every unrelated project on
earth acquired a Qdrant participant: `weft index corpus` exited **1** with *"failed: qdrant
(weft-rag) — ResponseHandlingException"* and the README's own quickstart stopped working
(`docs/lessons.md` `L11.21`).

**So the subject is now the project's own documents.** `project` is what
`load_pipeline_catalogue` read out of `pipelines/`; `catalogue` is every pipeline there is, and
it is consulted for exactly one thing — walking a project document's `extends:` chain, so a
project that derives from a shipped rung still counts the stores that rung names. A contributed
document nothing in the project derives from names no store this project uses.

**`load_run_records` refuses a file it cannot read rather than skipping it**, and that is the
property its error test exists for. A run record that will not parse might be the one naming
the store this deletion has to reach, so skipping it would let derived data survive its source
silently — `docs/lessons.md` L5.9's rule, that an empty answer means *"I did not find it"* and
never *"it is not there"*, applied to a directory sweep.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest

from weft_cli.participation import (
    UnreadableRunRecordError,
    load_run_records,
    stores_in_use,
)
from weft_eval.run_record import CorpusIdentity, RunRecord, write_run_record
from weft_kernel.pipeline import InsertOperator, Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_store import NodeStore


@runtime_checkable
class _Extractor(Protocol):
    """Some other contract entirely — a name a pipeline uses that is not a store."""

    async def extract(self) -> None: ...


class _Store:
    """Stands in for any registered `NodeStore`. Nothing here is built or called."""

    def __init__(self, config: object = None) -> None:
        del config


class _OtherStore(_Store):
    """A second registered `NodeStore` — the graph store's position in `02` §4's table."""


class _Text:
    """A plugin registered under a contract that is not `NodeStore`."""

    def __init__(self, config: object = None) -> None:
        del config


def _registry() -> Registry:
    registry = Registry()
    registry.add(NodeStore, "pgvector", _Store, distribution="weft-store")
    registry.add(NodeStore, "example-graph", _OtherStore, distribution="weft-example-graph")
    registry.add(NodeStore, "qdrant", _Store, distribution="weft-qdrant")
    registry.add(_Extractor, "text", _Text, distribution="weft-extract")
    return registry


def _kg_pipeline() -> Pipeline:
    """The shape `examples/weft-example-graph`'s own `kg.yaml` has: an ordinary ingest path
    whose last stage writes to a second `NodeStore`.
    """
    return Pipeline(
        name="kg",
        stages=(
            StageDeclaration(id="extract", use="text"),
            StageDeclaration(id="store", use="pgvector"),
            StageDeclaration(id="graph-store", use="example-graph"),
        ),
    )


def _shipped_qdrant_rung() -> Pipeline:
    """`index-qdrant`'s shape — a document an installed pack contributes, naming a store.

    The subject of R11.2: this is in `catalogue` and never in `project`, and the store it
    names is one no project that has not derived from it has ever written to.
    """
    return Pipeline(
        name="index-qdrant",
        extends="index-text",
        replace=(StageDeclaration(id="store", use="qdrant"),),
    )


def _run_record(*, stage_use: str) -> RunRecord:
    return RunRecord(
        recorded_at="2026-08-22T00:00:00Z",
        resolved_pipeline=ResolvedPipeline(
            name="kg",
            stages=(
                ResolvedStage(
                    id="graph-store",
                    contract="NodeStore",
                    use=stage_use,
                    distribution="weft-example-graph",
                    provenance="kg",
                ),
            ),
        ),
        corpus=CorpusIdentity(name="docs", digest="abc123"),
    )


def test_a_store_a_project_document_names_joins_the_configured_one() -> None:
    # Arrange — the project wrote `pipelines/kg.yaml` itself, so the store it names is one
    # this project has run data through.
    registry = _registry()
    project = {"kg": _kg_pipeline()}

    # Act
    in_use = stores_in_use(
        configured="pgvector",
        registry=registry,
        project=project,
        catalogue=project,
        records=(),
    )

    # Assert
    assert in_use == frozenset({"pgvector", "example-graph"})


def test_a_store_only_a_contributed_document_names_stays_out() -> None:
    """**R11.2's whole point.** `index-qdrant` is installed and routable, and this project has
    neither derived from it nor run it. Before the narrowing this put `qdrant` into every
    project's participant set, so `weft delete` and `weft index`'s repair pass both connected
    to a database the operator never asked for — `docs/lessons.md` `L11.21`.
    """
    # Arrange
    registry = _registry()
    contributed = {"index-qdrant": _shipped_qdrant_rung()}

    # Act
    in_use = stores_in_use(
        configured="pgvector",
        registry=registry,
        project={},
        catalogue=contributed,
        records=(),
    )

    # Assert
    assert in_use == frozenset({"pgvector"})


def test_a_store_named_only_by_an_ancestor_of_a_project_document_joins() -> None:
    """*"What its own documents derive from"* — the clause that keeps the narrowing honest.

    The project's own document adds one stage and says nothing about a store; the store it
    writes to is named by the shipped rung it extends. Reading the project document alone
    would miss it, and missing it is the silent orphan G7 built the fan-out to prevent.
    """
    # Arrange
    registry = _registry()
    project = {
        "mine": Pipeline(
            name="mine",
            extends="index-qdrant",
            insert=(
                InsertOperator(
                    after="store", stage=StageDeclaration(id="second", use="example-graph")
                ),
            ),
        )
    }
    catalogue = {**project, "index-qdrant": _shipped_qdrant_rung()}

    # Act
    in_use = stores_in_use(
        configured="pgvector",
        registry=registry,
        project=project,
        catalogue=catalogue,
        records=(),
    )

    # Assert — `qdrant` arrives through the chain, `example-graph` through the project's own
    # operator block, and both are stores this project genuinely writes to.
    assert in_use == frozenset({"pgvector", "qdrant", "example-graph"})


def test_a_chain_that_names_a_parent_nothing_holds_stops_rather_than_raising() -> None:
    """An `extends:` naming no known pipeline cannot run at all, so it reaches no store.

    `weft_kernel.resolution.UnknownParentPipelineError` is what refuses such a document, by
    name, on every command that resolves one; `weft delete` resolves none, and refusing a
    deletion because an unrelated document is broken would reap nothing rather than too
    little. The walk stops at the missing parent and the project's own stages still count.
    """
    # Arrange
    registry = _registry()
    project = {
        "orphan": Pipeline(
            name="orphan",
            extends="a-pipeline-nothing-holds",
            insert=(
                InsertOperator(
                    after="store", stage=StageDeclaration(id="second", use="example-graph")
                ),
            ),
        )
    }

    # Act
    in_use = stores_in_use(
        configured="pgvector",
        registry=registry,
        project=project,
        catalogue=project,
        records=(),
    )

    # Assert
    assert in_use == frozenset({"pgvector", "example-graph"})


def test_an_extends_cycle_terminates() -> None:
    """A cycle in `extends:` must not hang this walk, and the assertion is that it returns.

    `weft_kernel.resolution` refuses a cycle on every path that *resolves* a document, and
    this function resolves none — so termination has to be this walk's own property rather
    than something upstream is trusted to have refused already.
    """
    # Arrange
    registry = _registry()
    project = {
        "a": Pipeline(name="a", extends="b", replace=(StageDeclaration(id="s", use="qdrant"),)),
        "b": Pipeline(
            name="b", extends="a", replace=(StageDeclaration(id="s", use="example-graph"),)
        ),
    }

    # Act
    in_use = stores_in_use(
        configured="pgvector",
        registry=registry,
        project=project,
        catalogue=project,
        records=(),
    )

    # Assert
    assert in_use == frozenset({"pgvector", "qdrant", "example-graph"})


def test_a_store_only_a_persisted_run_names_joins() -> None:
    """The catalogue is empty and the document is gone; the run history is the only record
    that this project ever wrote to that store, and `02` §1 makes it a participant anyway.
    """
    # Arrange
    registry = _registry()

    # Act
    in_use = stores_in_use(
        configured="pgvector",
        registry=registry,
        project={},
        catalogue={},
        records=(_run_record(stage_use="example-graph"),),
    )

    # Assert
    assert in_use == frozenset({"pgvector", "example-graph"})


def test_a_registered_store_nothing_names_stays_out() -> None:
    """Task 5.1a's narrowing, kept: `qdrant` is installed and registered, no document and no
    run names it, and connecting to it would be the operator's unused database.
    """
    # Arrange
    registry = _registry()
    project = {"kg": _kg_pipeline()}

    # Act
    in_use = stores_in_use(
        configured="pgvector",
        registry=registry,
        project=project,
        catalogue=project,
        records=(),
    )

    # Assert
    assert "qdrant" not in in_use


def test_a_named_plugin_that_is_not_a_store_is_not_a_store() -> None:
    """`kg` names `text` as well, and `text` is registered under another contract entirely.
    Membership is decided against what is registered under `NodeStore`, never against the set
    of names a document happens to mention.
    """
    # Arrange
    registry = _registry()
    project = {"kg": _kg_pipeline()}

    # Act
    in_use = stores_in_use(
        configured="pgvector",
        registry=registry,
        project=project,
        catalogue=project,
        records=(),
    )

    # Assert
    assert "text" not in in_use


def test_a_store_named_by_an_operator_block_counts_as_named() -> None:
    """A derived pipeline names its stores in `insert:`/`replace:` rather than in `stages:`,
    and a store a derivation adds is one this project runs data through just the same.
    """
    # Arrange
    registry = _registry()
    derived = Pipeline(
        name="kg-plus",
        extends="kg",
        insert=(
            InsertOperator(after="store", stage=StageDeclaration(id="graph", use="example-graph")),
        ),
    )
    project = {"kg-plus": derived}

    # Act
    in_use = stores_in_use(
        configured="pgvector",
        registry=registry,
        project=project,
        catalogue={**project, "kg": _kg_pipeline()},
        records=(),
    )

    # Assert — `pgvector` from `kg`'s own store stage through the chain, `example-graph` from
    # the operator block, and nothing else.
    assert in_use == frozenset({"pgvector", "example-graph"})


def test_the_configured_store_is_in_use_whatever_else_is() -> None:
    # Arrange
    registry = _registry()

    # Act
    in_use = stores_in_use(
        configured="pgvector", registry=registry, project={}, catalogue={}, records=()
    )

    # Assert
    assert in_use == frozenset({"pgvector"})


def test_run_records_are_read_from_a_directory(tmp_path: Path) -> None:
    # Arrange
    write_run_record(_run_record(stage_use="example-graph"), tmp_path / "run-a.json")
    write_run_record(_run_record(stage_use="qdrant"), tmp_path / "run-b.json")

    # Act
    records = load_run_records(tmp_path)

    # Assert
    assert [record.resolved_pipeline.stages[0].use for record in records] == [
        "example-graph",
        "qdrant",
    ]


def test_a_runs_directory_that_does_not_exist_holds_no_runs(tmp_path: Path) -> None:
    # Act
    records = load_run_records(tmp_path / "never-written")

    # Assert
    assert records == ()


def test_a_run_record_that_will_not_parse_is_refused_by_name(tmp_path: Path) -> None:
    # Arrange
    broken = tmp_path / "run-a.json"
    broken.write_text("{not json at all", encoding="utf-8")

    # Act
    with pytest.raises(UnreadableRunRecordError) as raised:
        load_run_records(tmp_path)

    # Assert
    assert raised.value.path == broken
    assert str(broken) in str(raised.value)
