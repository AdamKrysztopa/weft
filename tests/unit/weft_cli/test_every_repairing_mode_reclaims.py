"""Carried repair **R43.46** — a bare `weft reconcile` reclaims withdrawn generations.

`reconcile._converge` reclaimed only under `ReconcileMode.REPAIR`, while a bare `weft reconcile`
runs `[reconcile] mode`, `full` by default, and `ReconcileMode` says `full` does what `repair` does
and also backfills. So the command as a person types it never reclaimed. Every mode that repairs
now reclaims; `--dry-run` asks nobody to converge and so reclaims nothing.

Driven through `cli.run_command` with an argparse namespace, so the mode a bare command reaches is
the one `ReconcileCommand` itself resolves. The store double is R43.38's
(`test_generation_fallbacks_are_reported`): `corpus_build_doubles.GenerationStore` with
`GenerationWithdrawing`'s whole effect and a `Reconcilable` with nothing of its own to converge.
"""

import argparse
from collections.abc import Sequence
from functools import partial
from pathlib import Path

import pytest

from tests.unit.weft_cli.corpus_build_doubles import LAYER, GenerationStore, State
from weft_cli import cli, commands
from weft_cli.exit_codes import ExitCode
from weft_cli.render import Rendered
from weft_command.contract import Command
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import MediaType, Node, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore
from weft_store.contract import (
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    NotAPublishedGenerationError,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
)

_SECOND = "enrich-with-terse-tree"
_LINE = "  pgvector (weft-store): examined 0, removed 0, backfilled 0"


class _ReconcilingWithdrawingStore(GenerationStore):
    """`GenerationWithdrawing` on the double, and a participant with nothing else to converge."""

    async def withdraw_generation(self, generation: GenerationId) -> GenerationRecord:
        record = self._known(generation)
        if record.status is not GenerationStatus.PUBLISHED:
            raise NotAPublishedGenerationError(
                generation,
                status=record.status,
                valid_options=tuple(
                    g
                    for g, r in self.state.generations.items()
                    if r.status is GenerationStatus.PUBLISHED
                ),
            )
        withdrawn = record.model_copy(update={"status": GenerationStatus.WITHDRAWN})
        self.state.generations[generation] = withdrawn
        return withdrawn

    async def reclaim_withdrawn(self, layer: str) -> Removed:
        doomed = [
            record.id
            for record in self.state.generations.values()
            if record.layer == layer and record.status is GenerationStatus.WITHDRAWN
        ]
        removed = 0
        for generation in doomed:
            removed += (await GenerationStore.retract_generation(self, generation)).node_count
        return Removed(source_id=SourceId(layer), node_count=removed)

    async def reconcile(self, ctx: object, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        return ReconcileReport(mode=mode)

    async def estimate(self, ctx: object, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(mode=mode, description="nothing pending")


def _summary(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="R43.46",
        sources=frozenset({SourceId("doc0")}),
    )


async def _tree(store: GenerationStore, layer: str, nodes: Sequence[Node]) -> GenerationId:
    record = await store.open_generation(layer)
    await (await store.bind_generation(record.id)).add(list(nodes))
    await store.publish_generation(record.id)
    return record.id


async def _two_withdrawn_trees(state: State) -> tuple[GenerationId, GenerationId, Node]:
    """`LAYER`'s withdrawn tree holds one node of its own and one its successor shares;
    `_SECOND`'s holds two of its own. Reclaiming removes 1 + 2 and keeps the shared node."""
    store = _ReconcilingWithdrawingStore(state)
    shared = _summary("kept by both trees")
    old_first = await _tree(store, LAYER, [_summary("only the old first tree"), shared])
    await _tree(store, LAYER, [shared, _summary("only the new first tree")])
    old_second = await _tree(store, _SECOND, [_summary("old second, a"), _summary("old second, b")])
    await _tree(store, _SECOND, [_summary("the new second tree")])
    await store.withdraw_generation(old_first)
    await store.withdraw_generation(old_second)
    return old_first, old_second, shared


async def _reconcile(state: State, *, mode: ReconcileMode | None, dry_run: bool) -> Rendered:
    registry = Registry()
    registry.add(
        NodeStore,
        "pgvector",
        partial(_ReconcilingWithdrawingStore, state),
        distribution="weft-store",
    )
    registry.add(Command, "reconcile", commands.ReconcileCommand, distribution="weft-rag")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="pgvector"),
    )
    args = argparse.Namespace(mode=mode, dry_run=dry_run, target=None, yes=True)
    return await cli.run_command("reconcile", args, deps)


@pytest.mark.parametrize(
    "mode",
    [None, ReconcileMode.FULL, ReconcileMode.REPAIR],
    ids=["bare", "full", "repair"],
)
async def test_every_mode_that_repairs_reclaims_every_withdrawn_generation(
    mode: ReconcileMode | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — no weft.toml, so a bare `weft reconcile` runs `[reconcile] mode`'s default.
    monkeypatch.chdir(tmp_path)
    state = State()
    old_first, old_second, shared = await _two_withdrawn_trees(state)

    # Act
    rendered = await _reconcile(state, mode=mode, dry_run=False)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert rendered.stdout is not None
    assert rendered.stdout.startswith(f"mode '{(mode or ReconcileMode.FULL).value}'")
    assert f"{_LINE}, reclaimed 3" in rendered.stdout.splitlines()
    assert old_first not in state.generations
    assert old_second not in state.generations
    assert shared.id in state.nodes


async def test_a_bare_reconcile_with_nothing_withdrawn_prints_the_line_it_always_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    state = State()
    only = await _tree(_ReconcilingWithdrawingStore(state), LAYER, [_summary("the only tree")])

    # Act
    rendered = await _reconcile(state, mode=None, dry_run=False)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert rendered.stdout is not None
    assert _LINE in rendered.stdout.splitlines()
    assert state.generations[only].status is GenerationStatus.PUBLISHED


@pytest.mark.parametrize("mode", [None, ReconcileMode.REPAIR], ids=["bare", "repair"])
async def test_a_dry_run_reclaims_nothing(
    mode: ReconcileMode | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    state = State()
    old_first, old_second, _ = await _two_withdrawn_trees(state)
    nodes_before = set(state.nodes)

    # Act
    rendered = await _reconcile(state, mode=mode, dry_run=True)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert rendered.stdout is not None
    assert "reclaimed" not in rendered.stdout
    assert state.generations[old_first].status is GenerationStatus.WITHDRAWN
    assert state.generations[old_second].status is GenerationStatus.WITHDRAWN
    assert set(state.nodes) == nodes_before
