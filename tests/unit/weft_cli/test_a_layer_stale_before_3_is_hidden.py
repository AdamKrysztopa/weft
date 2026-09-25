"""Carried repair **R43.53** — a corpus layer already `STALE` before 3.0.0 is hidden from reads too.

Task 43.30 hides a layer's published generation at the moment `demote_layer_records` demotes it.
Under 2.x a demotion rewrote only the source records, so a store upgraded with a layer already
`STALE` still serves that layer's `PUBLISHED` generation, and nothing demotes it again. The seeded
state is exactly that: a layer built, then one record rewritten `STALE` with the generation left
alone. `weft reconcile` repairs it, and so does the closing pass every `weft index` runs.
"""

from pathlib import Path

import pytest
from pydantic import BaseModel

from tests.unit.weft_cli.corpus_build_doubles import (
    LAYER,
    ClosingPassStore,
    GenerationStore,
    ScriptedModel,
    llm_section,
    make_ctx,
    published,
    registry_for,
    visible_summaries,
    write_corpus,
    write_layer,
)
from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_store.contract import LayerStatus, ReconcileEstimate, ReconcileMode, ReconcileReport


class _ReconcilingStore(GenerationStore):
    """A `Reconcilable` participant that holds generations and cannot withdraw one."""

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        return ReconcileReport(mode=mode)

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(mode=mode, description="nothing pending")


_STORES = pytest.mark.parametrize(
    "store_class", [ClosingPassStore, _ReconcilingStore], ids=["withdraws", "cannot-withdraw"]
)


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    write_layer(tmp_path)
    return write_corpus(tmp_path)


def _deps(store: GenerationStore) -> Dependencies:
    return Dependencies(
        registry=registry_for(store),
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index", "llm")
        ),
        services=ServiceSelection(store="pgvector"),
        llm=llm_section("m1"),
    )


async def _run(
    store: GenerationStore,
    command: commands.IndexCommand | commands.ReconcileCommand,
    args: BaseModel,
) -> render.Rendered:
    ctx = make_ctx()
    ctx.services.add(Dependencies, _deps(store))
    rendered = render.render_outcome(await command.run(args, ctx))
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    return rendered


async def _index(store: GenerationStore, corpus: Path, layers: str) -> render.Rendered:
    args = commands.IndexArgs.model_validate({"path": str(corpus), "layers": layers})
    return await _run(store, commands.IndexCommand(), args)


async def _reconcile(
    store: GenerationStore, *, mode: ReconcileMode | None, dry_run: bool = False
) -> render.Rendered:
    args = commands.ReconcileArgs(mode=mode, dry_run=dry_run)
    return await _run(store, commands.ReconcileCommand(), args)


def _stale_as_2x_left_it(store: GenerationStore) -> None:
    """Rewrite one source's record of `LAYER` `STALE`, leaving its generation `PUBLISHED`."""
    source_id, record = next(iter(store.state.records.items()))
    layers = tuple(
        entry.model_copy(update={"status": LayerStatus.STALE}) if entry.name == LAYER else entry
        for entry in record.layers
    )
    assert layers != record.layers
    store.state.records[source_id] = record.model_copy(update={"layers": layers})


async def _built_then_staled(store_class: type[GenerationStore], corpus: Path) -> GenerationStore:
    store = store_class()
    await _index(store, corpus, LAYER)
    _stale_as_2x_left_it(store)
    assert visible_summaries(store)
    return store


@_STORES
@pytest.mark.parametrize(
    "mode", [None, ReconcileMode.REPAIR, ReconcileMode.FULL], ids=["bare", "repair", "full"]
)
async def test_reconcile_hides_a_layer_already_stale(
    corpus: Path, store_class: type[GenerationStore], mode: ReconcileMode | None
) -> None:
    # Arrange
    store = await _built_then_staled(store_class, corpus)

    # Act
    await _reconcile(store, mode=mode)

    # Assert
    assert visible_summaries(store) == []
    assert published(store) == []


@_STORES
async def test_the_pass_closing_weft_index_hides_it_and_a_rebuild_serves_it_again(
    corpus: Path, store_class: type[GenerationStore]
) -> None:
    # Arrange
    store = await _built_then_staled(store_class, corpus)

    # Act
    await _index(store, corpus, "none")
    hidden = visible_summaries(store)
    await _index(store, corpus, LAYER)

    # Assert
    assert hidden == []
    assert visible_summaries(store)
    assert len(published(store)) == 1


@_STORES
async def test_reconcile_leaves_a_layer_active_everywhere_served(
    corpus: Path, store_class: type[GenerationStore]
) -> None:
    # Arrange
    store = store_class()
    await _index(store, corpus, LAYER)
    before = {node.id for node in visible_summaries(store)}

    # Act
    await _reconcile(store, mode=ReconcileMode.REPAIR)

    # Assert
    assert before
    assert {node.id for node in visible_summaries(store)} == before


@_STORES
async def test_a_dry_run_hides_nothing(corpus: Path, store_class: type[GenerationStore]) -> None:
    # Arrange
    store = await _built_then_staled(store_class, corpus)

    # Act
    await _reconcile(store, mode=ReconcileMode.REPAIR, dry_run=True)

    # Assert
    assert visible_summaries(store)
    assert len(published(store)) == 1
