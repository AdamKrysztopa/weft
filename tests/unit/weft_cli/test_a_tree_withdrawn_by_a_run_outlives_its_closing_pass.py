"""Carried repair R43.47: a run's closing `repair` pass spares the tree that same run withdrew.

Carried repair **R43.47** — a tree a `weft index` run withdrew outlives that run's own closing
`repair` pass.

R43.29 withdraws a superseded corpus-layer tree rather than deleting it, so a query that opened
before the publish keeps reading it; its nodes go "before that layer's next build or by `weft
reconcile`" (`manual/troubleshooting.md`). `weft index` always ends with an automatic `repair`
pass, and that pass reclaimed every withdrawn generation — the one this same run had just withdrawn
too — so the delay lasted only until the command returned. The pass still reclaims a tree an
earlier run withdrew.

The store is `test_generation_fallbacks_are_reported`'s withdrawing and carrying double, made a
`Reconcilable` participant so the closing pass reaches it, over the same two corpus-scoped layers.
"""

from collections.abc import Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import ClassVar

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    LAYER,
    CountingEmbedder,
    GenerationStore,
    ScriptedModel,
    llm_section,
    make_ctx,
    write_corpus,
)
from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_index import Expander, Revisable
from weft_index.adrap import AdrapJoiner
from weft_index.payload import RaptorFacts
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import RaptorSummarizer
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import MediaType, Node, NodeId, SourceId
from weft_kernel.registry import Registry
from weft_llm.contract import LLMProvider
from weft_prompts.contract import Prompt
from weft_prompts.typed_prompt import PromptText
from weft_store import NodeStore
from weft_store.contract import (
    Filter,
    FilterOp,
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
_SUMMARIES = Filter(op=FilterOp.EXISTS, field=f"ext.{RaptorFacts.__namespace__}.clusters_found")
_OTHER_PROMPT = "summarize-cluster-other-tree"
_CONVERGED = "  pgvector (weft-store): examined 0, removed 0, backfilled 0"


class _ClosingPassStore(GenerationStore):
    """`GenerationWithdrawing`, `GenerationCarrying` and `Reconcilable` on the double."""

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

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        return ReconcileReport(mode=mode)

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(mode=mode, description="nothing pending")


class _OtherTreePrompt(SummarizeClusterPrompt):
    """The second layer's prompt, prefixed so its summary digests never match the first layer's.

    A request that differs from `summarize-cluster`'s, so the two layers share no summary —
    `corpus_build_doubles.TersePrompt` sends the same request, and the scripted model digests it.
    """

    name: ClassVar[str] = _OTHER_PROMPT
    texts: ClassVar[Mapping[str, PromptText]] = {
        locale: PromptText(system=text.system, user=f"The other tree.\n{text.user}")
        for locale, text in SummarizeClusterPrompt.texts.items()
    }


def _write_layers(project: Path, *, incremental: bool) -> None:
    """Give the project two layer pipelines whose trees share no node, full or incremental.

    Two corpus-scoped `raptor` layers under requests that differ; with `incremental`, each
    declares an `adrap` join.
    """
    (project / "pipelines").mkdir(exist_ok=True)
    for name, prompt in ((LAYER, SUMMARIZE_CLUSTER_NAME), (_SECOND, _OTHER_PROMPT)):
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


def _registry(store: GenerationStore) -> Registry:
    """Build the registry with `adrap` and the store registered by its class.

    `corpus_build_doubles.registry_for` with `adrap`, the store registered by its class so the
    closing pass finds it `Reconcilable` — `registry_for`'s factory function hides the class.
    """
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", CountingEmbedder, distribution="weft-embed")
    registry.add(
        NodeStore, "pgvector", partial(_ClosingPassStore, store.state), distribution="weft-store"
    )
    registry.add(Expander, "raptor", RaptorSummarizer, distribution="weft-index")
    registry.add(Prompt, SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt, distribution="weft-index")
    registry.add(Prompt, _OTHER_PROMPT, _OtherTreePrompt, distribution="weft-index")
    registry.add(LLMProvider, "scripted", ScriptedModel, distribution="weft-llm")
    registry.add(Revisable, "adrap", AdrapJoiner, distribution="weft-index")
    return registry


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    return write_corpus(tmp_path)


def _deps(registry: Registry) -> Dependencies:
    return Dependencies(
        registry=registry,
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index", "llm")
        ),
        services=ServiceSelection(store="pgvector"),
        llm=llm_section("m1"),
    )


async def _index(store: _ClosingPassStore, corpus: Path, *, layers: str) -> render.Rendered:
    ctx = make_ctx()
    ctx.services.add(Dependencies, _deps(_registry(store)))
    outcome = await commands.IndexCommand().run(
        commands.IndexArgs.model_validate({"path": str(corpus), "layers": layers}), ctx
    )
    rendered = render.render_outcome(outcome)
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    return rendered


async def _grown(
    store: _ClosingPassStore, corpus: Path, *, label: str, layers: str = _BOTH
) -> render.Rendered:
    """Drive one more labelled index run, so its summaries are told apart from earlier runs'.

    One more document, then `weft index --layers`: each named layer is stale by addition, so
    the run rebuilds or joins it and withdraws the tree it replaces.
    """
    (corpus / f"{label}.txt").write_text(f"a document that arrived for the {label} run.")
    ScriptedModel.label = label
    return await _index(store, corpus, layers=layers)


async def _reconcile(store: _ClosingPassStore) -> render.Rendered:
    registry = Registry()
    registry.add(
        NodeStore, "pgvector", partial(_ClosingPassStore, store.state), distribution="weft-store"
    )
    ctx = make_ctx()
    ctx.services.add(
        Dependencies,
        Dependencies(
            registry=registry,
            reports=(
                PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),
            ),
            services=ServiceSelection(store="pgvector"),
        ),
    )
    outcome = await commands.ReconcileCommand().run(
        commands.ReconcileArgs(mode=ReconcileMode.REPAIR), ctx
    )
    return render.render_outcome(outcome)


def _published(store: GenerationStore, layer: str) -> GenerationId:
    (live,) = [
        g
        for g, r in store.state.generations.items()
        if r.layer == layer and r.status is GenerationStatus.PUBLISHED
    ]
    return live


def _status(store: GenerationStore, generation: GenerationId) -> GenerationStatus | None:
    record = store.state.generations.get(generation)
    return None if record is None else record.status


def _tree(store: GenerationStore, generation: GenerationId) -> set[NodeId]:
    return {i for i, members in store.state.members.items() if generation in members}


def _pass_lines(rendered: render.Rendered) -> list[str]:
    return [
        line for line in (rendered.stdout or "").splitlines() if line.startswith("  pgvector (")
    ]


async def _summaries_seen_by(handle: GenerationStore) -> set[NodeId]:
    """Every summary `handle` finds; its first call fixes its manifest."""
    seen: set[NodeId] = set()
    page = await handle.matching(_SUMMARIES)
    seen |= {node.id for node in page.items}
    while page.next_cursor is not None:
        page = await handle.matching(_SUMMARIES, page.next_cursor)
        seen |= {node.id for node in page.items}
    return seen


def _reclaimed(layer: str, nodes: int) -> str:
    return f"layer '{layer}': reclaimed {nodes} node(s) from withdrawn generations"


def _reclaimed_lines(rendered: render.Rendered) -> list[str]:
    return [line for line in (rendered.stdout or "").splitlines() if ": reclaimed " in line]


_REBUILD_AND_JOIN = pytest.mark.parametrize("incremental", [False, True], ids=["rebuild", "join"])


@_REBUILD_AND_JOIN
async def test_a_tree_the_run_withdrew_is_still_withdrawn_and_stored_after_its_closing_pass(
    corpus: Path, tmp_path: Path, *, incremental: bool
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=incremental)
    store = _ClosingPassStore()
    await _index(store, corpus, layers=_BOTH)
    old = {layer: _published(store, layer) for layer in (LAYER, _SECOND)}
    old_trees = {layer: _tree(store, generation) for layer, generation in old.items()}

    # Act
    rendered = await _grown(store, corpus, label="second")

    # Assert
    assert {layer: _status(store, g) for layer, g in old.items()} == {
        LAYER: GenerationStatus.WITHDRAWN,
        _SECOND: GenerationStatus.WITHDRAWN,
    }, store.state.generations
    for layer, tree in old_trees.items():
        assert tree <= set(store.state.nodes), f"{layer}: the withdrawn tree lost nodes"
        assert _tree(store, old[layer]) == tree, f"{layer}: the withdrawn tree lost members"
    assert _pass_lines(rendered) == [_CONVERGED]


@_REBUILD_AND_JOIN
async def test_a_reader_that_opened_before_the_run_keeps_its_tree_after_the_run_ends(
    corpus: Path, tmp_path: Path, *, incremental: bool
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=incremental)
    store = _ClosingPassStore()
    await _index(store, corpus, layers=_BOTH)
    reader = _ClosingPassStore(store.state)
    before = await _summaries_seen_by(reader)

    # Act
    await _grown(store, corpus, label="second")

    # Assert
    assert before
    assert await _summaries_seen_by(reader) == before, "an open reader lost its tree"


@_REBUILD_AND_JOIN
async def test_the_next_build_reclaims_the_tree_the_run_before_it_withdrew(
    corpus: Path, tmp_path: Path, *, incremental: bool
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=incremental)
    store = _ClosingPassStore()
    await _index(store, corpus, layers=_BOTH)
    old = {layer: _published(store, layer) for layer in (LAYER, _SECOND)}
    old_trees = {layer: _tree(store, generation) for layer, generation in old.items()}
    await _grown(store, corpus, label="second")
    middle = {layer: _published(store, layer) for layer in (LAYER, _SECOND)}
    own = {layer: old_trees[layer] - _tree(store, middle[layer]) for layer in old}

    # Act
    rendered = await _grown(store, corpus, label="third")

    # Assert
    assert sorted(_reclaimed_lines(rendered)) == sorted(
        _reclaimed(layer, len(nodes)) for layer, nodes in own.items() if nodes
    )
    assert not set(old.values()) & set(store.state.generations)
    assert not (own[LAYER] | own[_SECOND]) & set(store.state.nodes)
    assert {_status(store, g) for g in middle.values()} == {GenerationStatus.WITHDRAWN}


async def test_an_explicit_reconcile_reclaims_the_tree_the_index_run_withdrew(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    _write_layers(tmp_path, incremental=False)
    store = _ClosingPassStore()
    await _index(store, corpus, layers=_BOTH)
    old = {layer: _published(store, layer) for layer in (LAYER, _SECOND)}
    old_trees = {layer: _tree(store, generation) for layer, generation in old.items()}
    await _grown(store, corpus, label="second")
    own = {
        node_id
        for layer in old
        for node_id in old_trees[layer] - _tree(store, _published(store, layer))
    }

    # Act
    rendered = await _reconcile(store)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert own, "the withdrawn trees hold no node of their own"
    assert _pass_lines(rendered) == [f"{_CONVERGED}, reclaimed {len(own)}"]
    assert not set(old.values()) & set(store.state.generations)
    assert not own & set(store.state.nodes)


def _summary(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="R43.47",
        sources=frozenset({SourceId("doc0")}),
    )


async def _withdrawn_earlier(store: _ClosingPassStore, layer: str) -> GenerationId:
    """A tree of `layer` published and withdrawn outside this run, holding two nodes of its own."""
    record = await store.open_generation(layer)
    await (await store.bind_generation(record.id)).add([_summary("earlier a"), _summary("b")])
    await store.publish_generation(record.id)
    await store.withdraw_generation(record.id)
    return record.id


async def test_the_closing_pass_still_reclaims_a_tree_an_earlier_run_withdrew(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange — `_SECOND` holds a tree withdrawn before this run; the run builds `LAYER` alone.
    _write_layers(tmp_path, incremental=False)
    store = _ClosingPassStore()
    await _index(store, corpus, layers=_BOTH)
    earlier = await _withdrawn_earlier(store, _SECOND)
    earlier_tree = _tree(store, earlier)

    # Act
    rendered = await _grown(store, corpus, label="second", layers=LAYER)

    # Assert
    assert earlier not in store.state.generations
    assert not earlier_tree & set(store.state.nodes)
    assert any(line.startswith(f"{_CONVERGED}, reclaimed ") for line in _pass_lines(rendered))


async def test_naming_a_layer_the_run_does_not_rebuild_does_not_spare_its_earlier_tree(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange — both layers are current, so a run naming both rebuilds neither and withdraws
    # nothing; what the closing pass spares is what the run withdrew, not what it named.
    _write_layers(tmp_path, incremental=False)
    store = _ClosingPassStore()
    await _index(store, corpus, layers=_BOTH)
    earlier = await _withdrawn_earlier(store, _SECOND)
    earlier_tree = _tree(store, earlier)

    # Act
    rendered = await _index(store, corpus, layers=_BOTH)

    # Assert
    assert earlier not in store.state.generations
    assert _pass_lines(rendered) == [f"{_CONVERGED}, reclaimed {len(earlier_tree)}"]


async def test_the_closing_pass_reclaims_an_earlier_runs_tree_and_keeps_its_own(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange — a run of `_SECOND` alone withdraws its first tree; the next run builds `LAYER`.
    _write_layers(tmp_path, incremental=False)
    store = _ClosingPassStore()
    await _index(store, corpus, layers=_BOTH)
    first_second = _published(store, _SECOND)
    await _grown(store, corpus, label="second", layers=_SECOND)
    earlier_own = _tree(store, first_second) - _tree(store, _published(store, _SECOND))
    first_layer = _published(store, LAYER)

    # Act
    rendered = await _grown(store, corpus, label="third", layers=LAYER)

    # Assert
    assert _status(store, first_layer) is GenerationStatus.WITHDRAWN, store.state.generations
    assert first_second not in store.state.generations
    assert earlier_own, "the earlier tree holds no node of its own"
    assert _pass_lines(rendered) == [f"{_CONVERGED}, reclaimed {len(earlier_own)}"]
