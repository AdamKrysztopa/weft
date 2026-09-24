"""Carried repair R43.38: `weft reconcile` says what it reclaimed and what it could not.

Carried repair **R43.38** — `weft reconcile` says what it reclaimed, and a store that cannot
withdraw or carry a generation says so.

`reconcile._converge` discarded the `Removed` each `reclaim_withdrawn` returned. A
`GenerationHolding` store that is not `GenerationWithdrawing` retracts the tree a rebuild replaced
at once, keeping R43.29's torn read, and one that is not `GenerationCarrying` rebuilds a layer stale
by addition in full instead of joining it; both did so silently. Each fallback now prints one
stderr line per store per run, however many layers fell back on it.

Two corpus-scoped layers over one corpus, so "once per run" is asked of two fallbacks. The stores
are `corpus_build_doubles.GenerationStore` plus the withdrawing half of
`test_a_superseded_corpus_layer_is_withdrawn`'s double and the carrying half of
`test_corpus_layer_joins_through_adrap`'s, each implementing its protocol's whole effect.

Carried repair **R43.43** — `weft index` says what its corpus builds reclaimed. Every build binding
its generations reclaims the layer's withdrawn ones and discarded the `Removed`, R43.38's defect
left on that caller. Each layer that reclaimed nodes now prints one stdout line beside its other
layer lines, and `--json` carries the count.
"""

import json
from collections.abc import Sequence
from functools import partial
from pathlib import Path

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    LAYER,
    TERSE_PROMPT,
    GenerationStore,
    ScriptedModel,
    State,
    llm_section,
    make_ctx,
    registry_for,
    write_corpus,
    write_two_store_base,
)
from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_command.contract import CommandResult
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_index import Revisable
from weft_index.adrap import AdrapJoiner
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import MediaType, Node, NodeId, Outcome, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore
from weft_store.contract import (
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    NotAPublishedGenerationError,
    NotAPublishedMemberError,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
)

_SECOND = "enrich-with-terse-tree"
_BOTH = f"{LAYER},{_SECOND}"


def _cannot_withdraw(stage: str, plugin: str) -> str:
    return (
        f"  store stage '{stage}' ({plugin}) cannot withdraw a generation "
        "(GenerationWithdrawing), so a layer tree this run replaced was retracted at once — "
        "a query still reading it may have lost it."
    )


def _cannot_carry(stage: str, plugin: str) -> str:
    return (
        f"  store stage '{stage}' ({plugin}) cannot carry a generation forward "
        "(GenerationCarrying), so a layer this run could have joined was rebuilt in full instead."
    )


class _WithdrawingStore(GenerationStore):
    """`GenerationWithdrawing` on the double: a withdraw changes no node, a reclaim retracts."""

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


class _CarryingStore(GenerationStore):
    """`GenerationCarrying.carry_forward` on the double: membership added, nothing rewritten."""

    async def carry_forward(self, into: GenerationId, node_ids: Sequence[NodeId]) -> int:
        self._known(into)
        live = {
            g for g, r in self.state.generations.items() if r.status is GenerationStatus.PUBLISHED
        }
        distinct = list(dict.fromkeys(node_ids))
        refused = [i for i in distinct if not self.state.members.get(i, set()) & live]
        if refused:
            raise NotAPublishedMemberError(into, node_ids=refused)
        for node_id in distinct:
            self.state.members[node_id].add(into)
        return len(distinct)


class _EveryWayStore(_WithdrawingStore, _CarryingStore):
    """`GenerationHolding`, `GenerationWithdrawing` and `GenerationCarrying` at once."""


class _ReconcilingWithdrawingStore(_WithdrawingStore):
    """A `Reconcilable` participant with nothing of its own to converge."""

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        return ReconcileReport(mode=mode)

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(mode=mode, description="nothing pending")


def _write_layers(project: Path, *, incremental: bool) -> None:
    """Write two corpus-scoped `raptor` layers, `LAYER` and `_SECOND`.

    Two corpus-scoped `raptor` layers, `LAYER` and `_SECOND`; with `incremental`, each declares
    an `adrap` join. `TersePrompt` sends the same request, so both trees hold the same summary ids
    (measured) — the reclaim tests seed their withdrawn trees for that reason.
    """
    (project / "pipelines").mkdir(exist_ok=True)
    for name, prompt in ((LAYER, SUMMARIZE_CLUSTER_NAME), (_SECOND, TERSE_PROMPT)):
        shared = (
            "      cluster_size: 2\n"
            "      similarity_threshold: -1.0\n"
            "      max_concurrent_summaries: 1\n"
            f"      prompt: {prompt}\n"
        )
        join = f"  - id: join\n    use: adrap\n    with:\n{shared}" if incremental else ""
        declared = "  layer.incremental: join\n" if incremental else ""
        (project / "pipelines" / f"{name}.yaml").write_text(
            f"name: {name}\n"
            f"vars:\n  layer.scope: corpus\n{declared}"
            "stages:\n"
            f"  - id: raptor\n    use: raptor\n    with:\n{shared}"
            f"{join}"
        )


def _with_adrap(registry: Registry) -> None:
    registry.add(Revisable, "adrap", AdrapJoiner, distribution="weft-index")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    return write_corpus(tmp_path)


async def _index_outcome(
    store: GenerationStore,
    corpus: Path,
    *,
    second: GenerationStore | None = None,
    **flags: object,
) -> Outcome[CommandResult]:
    deps = Dependencies(
        registry=registry_for(store, second=second, extra=_with_adrap),
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index", "llm")
        ),
        services=ServiceSelection(store="pgvector"),
        llm=llm_section("m1"),
    )
    ctx = make_ctx()
    ctx.services.add(Dependencies, deps)
    return await commands.IndexCommand().run(
        commands.IndexArgs.model_validate({"path": str(corpus), **flags}), ctx
    )


async def _index_command(
    store: GenerationStore,
    corpus: Path,
    *,
    second: GenerationStore | None = None,
    **flags: object,
) -> render.Rendered:
    return render.render_outcome(await _index_outcome(store, corpus, second=second, **flags))


async def _built_then_grown(
    store: GenerationStore,
    corpus: Path,
    *,
    second: GenerationStore | None = None,
    **flags: object,
) -> render.Rendered:
    """Build both layers, add one document, then run `weft index` again.

    Both layers built, one document added, then `weft index` again: each layer is stale by
    addition, so the second run rebuilds or joins both and supersedes both published trees.
    """
    first = await _index_command(store, corpus, second=second, layers=_BOTH, **flags)
    assert first.exit_code is ExitCode.SUCCESS, first.stderr
    (corpus / "late.txt").write_text("a document that arrived after both layers were built.")
    ScriptedModel.label = "second"
    return await _index_command(store, corpus, second=second, layers=_BOTH, **flags)


def _lines(text: str | None, protocol: str) -> list[str]:
    return [line for line in (text or "").splitlines() if f"({protocol})" in line]


def _both_layers_published_twice(store: GenerationStore) -> bool:
    live = [
        r.layer for r in store.state.generations.values() if r.status is GenerationStatus.PUBLISHED
    ]
    return store.state.opened == 4 and sorted(live) == sorted([LAYER, _SECOND])


async def test_a_store_that_cannot_withdraw_says_so_once_for_every_layer_it_retracted(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=False)
    store = GenerationStore()

    # Act
    rendered = await _built_then_grown(store, corpus)

    # Assert
    assert _both_layers_published_twice(store), store.state.generations
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert _lines(rendered.stderr, "GenerationWithdrawing") == [
        _cannot_withdraw("store", "pgvector")
    ]


async def test_a_first_build_replaces_no_tree_and_says_nothing_about_withdrawing(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=False)
    store = GenerationStore()

    # Act
    rendered = await _index_command(store, corpus, layers=_BOTH)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert _lines(rendered.stderr, "GenerationWithdrawing") == []


async def test_only_the_store_that_cannot_withdraw_is_named(corpus: Path, tmp_path: Path) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=False)
    write_two_store_base(tmp_path)
    store, second = _WithdrawingStore(), GenerationStore()

    # Act
    rendered = await _built_then_grown(store, corpus, second=second, pipeline="index-two-stores")

    # Assert
    assert _both_layers_published_twice(second), second.state.generations
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert _lines(rendered.stderr, "GenerationWithdrawing") == [
        _cannot_withdraw("second-store", "second")
    ]


async def test_a_store_that_cannot_carry_says_once_why_its_joins_were_rebuilt(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=True)
    store = _WithdrawingStore()

    # Act
    rendered = await _built_then_grown(store, corpus)

    # Assert
    assert _both_layers_published_twice(store), store.state.generations
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert "joined" not in (rendered.stdout or "")
    assert _lines(rendered.stderr, "GenerationCarrying") == [_cannot_carry("store", "pgvector")]
    assert _lines(rendered.stderr, "GenerationWithdrawing") == []


async def test_a_layer_with_no_join_to_fall_back_from_says_nothing_about_carrying(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=False)
    store = _WithdrawingStore()

    # Act
    rendered = await _built_then_grown(store, corpus)

    # Assert
    assert _both_layers_published_twice(store), store.state.generations
    assert _lines(rendered.stderr, "GenerationCarrying") == []


async def test_a_store_that_withdraws_and_carries_says_neither(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=True)
    store = _EveryWayStore()

    # Act
    rendered = await _built_then_grown(store, corpus)

    # Assert — both layers joined, and each join withdrew the tree it replaced.
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    joined = [line for line in (rendered.stdout or "").splitlines() if ": joined " in line]
    assert [line.split("'")[1] for line in joined] == [LAYER, _SECOND]
    withdrawn = [
        r.layer for r in store.state.generations.values() if r.status is GenerationStatus.WITHDRAWN
    ]
    assert sorted(withdrawn) == sorted([LAYER, _SECOND])
    assert _lines(rendered.stderr, "GenerationCarrying") == []
    assert _lines(rendered.stderr, "GenerationWithdrawing") == []


def _summary(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="R43.38",
        sources=frozenset({SourceId("doc0")}),
    )


async def _tree(store: _WithdrawingStore, layer: str, nodes: Sequence[Node]) -> GenerationId:
    record = await store.open_generation(layer)
    await (await store.bind_generation(record.id)).add(list(nodes))
    await store.publish_generation(record.id)
    return record.id


async def _reconcile_repair(state: State) -> render.Rendered:
    registry = Registry()
    registry.add(
        NodeStore,
        "pgvector",
        partial(_ReconcilingWithdrawingStore, state),
        distribution="weft-store",
    )
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="pgvector"),
    )
    ctx = make_ctx()
    ctx.services.add(Dependencies, deps)
    outcome = await commands.ReconcileCommand().run(
        commands.ReconcileArgs(mode=ReconcileMode.REPAIR), ctx
    )
    return render.render_outcome(outcome)


async def test_reconcile_prints_how_many_nodes_it_reclaimed_across_every_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — `LAYER`'s withdrawn tree holds one node of its own and one its successor shares;
    # `_SECOND`'s holds two of its own. Reclaiming removes 1 + 2.
    monkeypatch.chdir(tmp_path)
    state = State()
    store = _ReconcilingWithdrawingStore(state)
    shared = _summary("kept by both trees")
    old_first = await _tree(store, LAYER, [_summary("only the old first tree"), shared])
    await _tree(store, LAYER, [shared, _summary("only the new first tree")])
    old_second = await _tree(store, _SECOND, [_summary("old second, a"), _summary("old second, b")])
    await _tree(store, _SECOND, [_summary("the new second tree")])
    await store.withdraw_generation(old_first)
    await store.withdraw_generation(old_second)

    # Act
    rendered = await _reconcile_repair(state)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert rendered.stdout is not None
    assert (
        "  pgvector (weft-store): examined 0, removed 0, backfilled 0, reclaimed 3"
        in rendered.stdout.splitlines()
    )
    assert old_first not in state.generations
    assert old_second not in state.generations
    assert shared.id in state.nodes


async def test_reconcile_with_nothing_withdrawn_prints_the_line_it_always_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    state = State()
    await _tree(_ReconcilingWithdrawingStore(state), LAYER, [_summary("the only tree")])

    # Act
    rendered = await _reconcile_repair(state)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert rendered.stdout is not None
    assert (
        "  pgvector (weft-store): examined 0, removed 0, backfilled 0"
        in rendered.stdout.splitlines()
    )


def _reclaimed(layer: str, nodes: int) -> str:
    return f"layer '{layer}': reclaimed {nodes} node(s) from withdrawn generations"


def _reclaimed_lines(rendered: render.Rendered) -> list[str]:
    return [line for line in (rendered.stdout or "").splitlines() if ": reclaimed " in line]


class _RecordingStore(_EveryWayStore):
    """Every `Removed` a `reclaim_withdrawn` returned, by layer, so a zero is seen to be asked."""

    def __init__(self, state: State | None = None, generation: GenerationId | None = None) -> None:
        super().__init__(state, generation)
        self.reclaims: list[tuple[str, int]] = []

    async def reclaim_withdrawn(self, layer: str) -> Removed:
        removed = await super().reclaim_withdrawn(layer)
        self.reclaims.append((layer, removed.node_count))
        return removed


def _published(store: GenerationStore, layer: str) -> GenerationId:
    (live,) = [
        g
        for g, r in store.state.generations.items()
        if r.layer == layer and r.status is GenerationStatus.PUBLISHED
    ]
    return live


async def _withdrawn_trees(store: _RecordingStore) -> tuple[GenerationId, GenerationId]:
    """Seed one withdrawn tree per layer.

    A withdrawn tree per layer: `LAYER`'s holds one node of its own and one its published tree
    also holds, `_SECOND`'s two of its own — reclaiming removes 1 and 2, from two trees of two.
    """
    shared = next(
        store.state.nodes[i]
        for i, members in store.state.members.items()
        if _published(store, LAYER) in members
    )
    first = await _tree(store, LAYER, [_summary("only the withdrawn first tree"), shared])
    second = await _tree(store, _SECOND, [_summary("withdrawn second, a"), _summary("b")])
    await store.withdraw_generation(first)
    await store.withdraw_generation(second)
    return first, second


async def _built_withdrawn_then_grown(
    store: _RecordingStore, corpus: Path, *, as_json: bool = False
) -> tuple[render.Rendered, tuple[GenerationId, GenerationId]]:
    built = await _index_command(store, corpus, layers=_BOTH)
    assert built.exit_code is ExitCode.SUCCESS, built.stderr
    withdrawn = await _withdrawn_trees(store)
    store.reclaims.clear()
    (corpus / "late.txt").write_text("a document that arrived after both layers were built.")
    ScriptedModel.label = "second"
    outcome = await _index_outcome(store, corpus, layers=_BOTH)
    rendered = render.render_outcome(outcome, as_json=as_json)
    return rendered, withdrawn


async def test_a_rebuild_prints_how_many_nodes_each_layer_reclaimed(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=False)
    store = _RecordingStore()

    # Act
    rendered, withdrawn = await _built_withdrawn_then_grown(store, corpus)

    # Assert
    assert not set(withdrawn) & set(store.state.generations), store.state.generations
    assert sorted(store.reclaims) == sorted([(LAYER, 1), (_SECOND, 2)])
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert "joined" not in (rendered.stdout or "")
    assert sorted(_reclaimed_lines(rendered)) == sorted(
        [_reclaimed(LAYER, 1), _reclaimed(_SECOND, 2)]
    )


async def test_a_join_prints_how_many_nodes_each_layer_reclaimed(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=True)
    store = _RecordingStore()

    # Act
    rendered, withdrawn = await _built_withdrawn_then_grown(store, corpus)

    # Assert
    assert not set(withdrawn) & set(store.state.generations), store.state.generations
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    joined = [line for line in (rendered.stdout or "").splitlines() if ": joined " in line]
    assert sorted(line.split("'")[1] for line in joined) == sorted([LAYER, _SECOND])
    assert sorted(_reclaimed_lines(rendered)) == sorted(
        [_reclaimed(LAYER, 1), _reclaimed(_SECOND, 2)]
    )


async def test_json_carries_what_each_layer_reclaimed(corpus: Path, tmp_path: Path) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=False)
    store = _RecordingStore()

    # Act
    rendered, _ = await _built_withdrawn_then_grown(store, corpus, as_json=True)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert rendered.stdout is not None
    carried = json.loads(rendered.stdout)["layers_reclaimed"]
    assert sorted(carried, key=lambda entry: entry["layer"]) == sorted(
        [{"layer": LAYER, "nodes": 1}, {"layer": _SECOND, "nodes": 2}],
        key=lambda entry: entry["layer"],
    )


async def test_a_build_that_reclaimed_nothing_says_nothing_about_reclaiming(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange — neither run's binds find a withdrawn tree: the grown run withdraws the trees it
    # replaces only after, for the next build to reclaim.
    _write_layers(tmp_path, incremental=False)
    store = _RecordingStore()

    # Act
    first = render.render_outcome(await _index_outcome(store, corpus, layers=_BOTH), as_json=True)
    first_reclaims = list(store.reclaims)
    (corpus / "late.txt").write_text("a document that arrived after both layers were built.")
    ScriptedModel.label = "second"
    store.reclaims.clear()
    rendered = await _index_command(store, corpus, layers=_BOTH)

    # Assert
    assert sorted(first_reclaims) == sorted([(LAYER, 0), (_SECOND, 0)])
    assert first.stdout is not None
    assert json.loads(first.stdout)["layers_reclaimed"] == []
    assert _both_layers_published_twice(store), store.state.generations
    assert sorted(store.reclaims) == sorted([(LAYER, 0), (_SECOND, 0)])
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert _reclaimed_lines(rendered) == []
