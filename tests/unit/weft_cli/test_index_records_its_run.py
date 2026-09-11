"""`weft index` persists a run record, and the repair pass after it reaches what it named.

Carried repair **R11.2**'s second half. The first half narrows
`weft_cli.participation.stores_in_use` to the project's *own* documents, which closes the
hole `G19` opened — a shipped document naming a store made every unrelated project connect to
it (`docs/internal/lessons.md` `L11.21`). That narrowing leaves a hole of its own, and this file is
where it is closed.

**The hole.** `stores_in_use`'s third source is the persisted run history, and until this
change the only command that ever wrote one was `weft eval run`. So a project that indexes
with `weft index --pipeline index-with-cooccurrence` — a rung an installed pack contributes,
with no project-local document of its own — had *no* static evidence that it uses the graph
store: not `[services] store`, not a project document, and not a run record. Its `weft delete`
would then leave every graph row behind, which is precisely the silent orphan G7 built the
fan-out to prevent, arriving from the other side. A reader with one writer is
`docs/internal/lessons.md` L5.15's producing-side/consuming-side shape with the two sides swapped.

**Where the record goes, and why not beside the eval ones.** `weft eval compare --baseline`
selects a baseline's repetitions as *every* persisted run whose `resolved_pipeline.name`
matches (`weft_cli.eval_commands._baseline_repetitions`), and then asks
`weft_eval.falsify.baseline_spreads` for their metric spreads. An index run measures nothing,
so `metrics` is `{}`; dropped into `runs/` beside the eval records it would be selected as a
repetition that cannot answer. `runs/index/` is a directory `runs/*.json` — a non-recursive
glob — cannot see, so the eval surface is untouched and the participation reader is pointed at
both.

**No record for the default four-stage path**, and that is not an omission. A `RunRecord`'s
`resolved_pipeline` is mandatory, the built-in path resolves no document, and the only store it
writes to is `[services] store` — which `stores_in_use` counts unconditionally and always has.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_cli import commands
from weft_cli.eval_commands import DEFAULT_RUNS_DIR, all_run_records
from weft_cli.ingest import IndexResult
from weft_cli.participation import DEFAULT_INDEX_RUNS_DIR, load_run_records
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.services import ServiceSelection
from weft_embed import Embedder
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_kernel.runner import RunSummary
from weft_store import NodeStore, ReconcileEstimate, ReconcileMode, ReconcileReport


class _ReconcilableStore:
    """A `NodeStore` stand-in satisfying `Reconcilable` — copied from
    `tests/unit/weft_cli/test_commands.py`'s double of the same seam rather than written from
    the contract, so the two cannot come to disagree about what the fan-out actually calls.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def reconcile(self, ctx: object, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        return ReconcileReport(mode=mode, examined=1, removed=1)

    async def estimate(self, ctx: object, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(mode=mode, pending=0, description="nothing outstanding")


def _null_factory(config: object) -> object:
    del config
    return object()


def _ctx(deps: Dependencies) -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


def _deps() -> Dependencies:
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _null_factory, distribution="weft-store")
    registry.add(NodeStore, "graph", _ReconcilableStore, distribution="weft-rag")
    reports = tuple(
        PackReport(pack=p, distribution="weft-rag", status=PackStatus.ACTIVE)
        for p in ("extract", "chunk", "embed", "store", "graph")
    )
    return Dependencies(registry=registry, reports=reports, services=ServiceSelection())


def _resolved_naming_the_graph_store() -> ResolvedPipeline:
    """What a contributed rung resolves to: an ordinary store stage and a second one beside it.

    Built the way `tests/unit/weft_cli/test_participation.py` builds a `ResolvedPipeline`,
    which is the only construction of this type in the test tree.
    """
    return ResolvedPipeline(
        name="index-with-graph",
        stages=(
            ResolvedStage(
                id="store",
                contract="NodeStore",
                use="pgvector",
                distribution="weft-rag",
                provenance="index-text",
            ),
            ResolvedStage(
                id="graph-store",
                contract="NodeStore",
                use="graph",
                distribution="weft-rag",
                provenance="index-with-graph",
            ),
        ),
    )


def _patch_run_index(monkeypatch: pytest.MonkeyPatch, *, resolved: ResolvedPipeline | None) -> None:
    summary = RunSummary(produced=1, nothing_to_produce=0, failed=0)

    async def _fake_run_index(*_args: object, **_kwargs: object) -> IndexResult:
        return IndexResult(
            summary=summary,
            stored_count=1,
            resolved_pipeline=resolved,
            document_ids=("doc-a",),
        )

    monkeypatch.setattr(commands, "run_index", _fake_run_index)


async def test_an_index_that_resolved_a_document_persists_a_run_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    _patch_run_index(monkeypatch, resolved=_resolved_naming_the_graph_store())

    # Act
    outcome = await commands.IndexCommand().run(
        commands.IndexArgs(path=str(tmp_path), pipeline="index-with-graph"), _ctx(_deps())
    )

    # Assert — the record exists and carries the pipeline that actually ran, which is the
    # fact `stores_in_use` reads it for.
    assert isinstance(outcome, Produced)
    records = load_run_records(DEFAULT_INDEX_RUNS_DIR)
    assert [record.resolved_pipeline.name for record in records] == ["index-with-graph"]
    assert [stage.use for stage in records[0].resolved_pipeline.stages] == ["pgvector", "graph"]


async def test_an_index_run_record_is_invisible_to_the_eval_baseline_search(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An index run measures nothing, so it must never be selected as a baseline repetition.

    Asked through `weft_cli.eval_commands`' own reader rather than through a second glob
    written here: two implementations of *"which runs does `weft eval compare` consider"*
    could disagree, and this test would then be reporting on the wrong one.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    _patch_run_index(monkeypatch, resolved=_resolved_naming_the_graph_store())

    # Act
    await commands.IndexCommand().run(
        commands.IndexArgs(path=str(tmp_path), pipeline="index-with-graph"), _ctx(_deps())
    )

    # Assert
    assert load_run_records(DEFAULT_INDEX_RUNS_DIR) != ()
    assert all_run_records(DEFAULT_RUNS_DIR) == ()


async def test_the_default_path_persists_no_run_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The built-in four-stage path resolves no document, so there is no `resolved_pipeline`
    to record — and the only store it writes to is `[services] store`, which participation
    counts unconditionally. Writing a record with an invented pipeline would be a fact about
    a document that does not exist.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    _patch_run_index(monkeypatch, resolved=None)

    # Act
    await commands.IndexCommand().run(commands.IndexArgs(path=str(tmp_path)), _ctx(_deps()))

    # Assert
    assert load_run_records(DEFAULT_INDEX_RUNS_DIR) == ()


async def test_the_repair_pass_after_an_index_reaches_the_store_that_run_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """**The property R11.2's second half exists for.** No project document, no `[services]`
    entry, no prior run — the graph store is named only by the contributed rung this
    invocation ran, and the automatic repair pass has to reach it anyway.
    """
    # Arrange
    monkeypatch.chdir(tmp_path)
    _patch_run_index(monkeypatch, resolved=_resolved_naming_the_graph_store())

    # Act
    outcome = await commands.IndexCommand().run(
        commands.IndexArgs(path=str(tmp_path), pipeline="index-with-graph"), _ctx(_deps())
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.IndexCommandResult)
    assert result.reconcile is not None
    assert [outcome.plugin for outcome in result.reconcile.participants] == ["graph"]
