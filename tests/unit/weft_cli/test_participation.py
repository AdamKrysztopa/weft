"""Unit tests for `weft_cli.participation`.

Mirrors `packages/weft-rag/src/weft_cli/participation.py`. Task **6.18**, which discharges
G13's first repair: `docs/02-extension-model.md` §1 → *Extended by G13*, *"the configured
`[services] store`, plus every `NodeStore` named by a pipeline in the project's catalogue or
by a persisted run record"*.

**What is actually under test here is a widening, and the edge that matters is the one it must
not cross.** Task 5.1a narrowed the `NodeStore` fan-out to the single store `[services] store`
names, so a project with pgvector and Qdrant both installed does not connect to a database the
operator does not use. That narrowing stays true of a store nothing selects and nothing names;
what it got wrong is the graph store, which registers under `NodeStore` too and is named by the
`kg` pipeline that writes to it. So the tests below check both directions: a store a document
or a run names joins, and a store registered but named by nothing does not.

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


def test_a_store_a_catalogue_pipeline_names_joins_the_configured_one() -> None:
    # Arrange
    registry = _registry()
    catalogue = {"kg": _kg_pipeline()}

    # Act
    in_use = stores_in_use(
        configured="pgvector", registry=registry, catalogue=catalogue, records=()
    )

    # Assert
    assert in_use == frozenset({"pgvector", "example-graph"})


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

    # Act
    in_use = stores_in_use(
        configured="pgvector", registry=registry, catalogue={"kg": _kg_pipeline()}, records=()
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

    # Act
    in_use = stores_in_use(
        configured="pgvector", registry=registry, catalogue={"kg": _kg_pipeline()}, records=()
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

    # Act
    in_use = stores_in_use(
        configured="pgvector", registry=registry, catalogue={"kg-plus": derived}, records=()
    )

    # Assert
    assert in_use == frozenset({"pgvector", "example-graph"})


def test_the_configured_store_is_in_use_whatever_else_is() -> None:
    # Arrange
    registry = _registry()

    # Act
    in_use = stores_in_use(configured="pgvector", registry=registry, catalogue={}, records=())

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
