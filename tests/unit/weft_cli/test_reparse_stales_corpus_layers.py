"""Carried repair R43.41: `weft index` stales a corpus layer whose source it released for re-parse.

Carried repair **R43.41** — a corpus layer is never served whole after a covered source is
re-parsed.

`weft index` releases a changed, failed-again or interrupted source's earlier parse with
`delete_source`, and a store's `delete_source` removes every summary that names the source
(`weft_store.conformance.check_delete_source_removes_exactly_the_nodes_carrying_it`). Before this
repair only `weft delete` marked the corpus layers it holed `LayerStatus.STALE` (task 43.21,
R43.33), so a re-parse that failed left the remaining records `ACTIVE` and the layer read ready
over a tree missing a cluster; one that succeeded left them `ACTIVE` and the next `--layers` run
joined only the re-parsed source's leaves into that holed tree.

Leaves are embedded by direction, as in `test_corpus_layer_joins_through_adrap`: `NORTHWARD` and
`EASTWARD` documents form one cluster each, so the tree over the six starts with two summaries.
"""

import asyncio
from collections.abc import Iterator, Sequence
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from typing import ClassVar, cast

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    GenerationStore,
    ScriptedModel,
    State,
    llm_section,
)
from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli import cli, commands, render
from weft_cli.exit_codes import ExitCode
from weft_command.contract import Command
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
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
from weft_kernel.payload import Failed, Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_kernel.registry import Registry
from weft_llm.contract import LLMProvider
from weft_prompts.contract import Prompt
from weft_store import NodeStore
from weft_store.contract import (
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    LayerStatus,
    Removed,
)

_LAYER = "enrich-with-tree"
_FIRST = ("n1", "n2", "n3", "e1", "e2", "e3")
_WIDTH = 8
_DIRECTIONS = {"NORTHWARD": 0, "EASTWARD": 1, "UPWARD": 2}
_ELSEWHERE = 3
_UNREADABLE = "UNREADABLE"


def _direction(content: str) -> Vector:
    axis = next((i for word, i in _DIRECTIONS.items() if word in content), _ELSEWHERE)
    return Vector(values=tuple(1.0 if i == axis else 0.0 for i in range(_WIDTH)))


class _DirectionEmbedder(HashEmbedder):
    """A leaf's vector is the axis its text names; a summary names none and gets its own."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=tuple(n.with_embedding(_direction(n.content)) for n in payload))


class _Chunker(FixedSizeChunker):
    """Drives a source's re-parse to fail in each of the three ways `weft index` must survive.

    `fixed-size`, which cannot read a document saying `UNREADABLE` — by returning `Failed`,
    by raising, or by being cancelled mid-call, as `mode` says.
    """

    mode: ClassVar[str] = "failed"

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        if any(_UNREADABLE in node.content for node in payload):
            if _Chunker.mode == "raises":
                raise RuntimeError(f"cannot chunk {_UNREADABLE}")
            if _Chunker.mode == "cancelled":
                raise asyncio.CancelledError
            return Failed(reason=f"cannot chunk {_UNREADABLE}")
        return await super().run(payload, ctx)


class _Handed:
    """Which layer stage was handed how many leaves, per call."""

    calls: ClassVar[list[tuple[str, int]]] = []


class _Raptor(RaptorSummarizer):
    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        _Handed.calls.append(("raptor", len(payload)))
        return await super().run(payload, ctx)


class _Adrap(AdrapJoiner):
    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        _Handed.calls.append(("adrap", len(payload)))
        return await super().run(payload, ctx)


def _published_at(record: GenerationRecord) -> float:
    return record.published_at.timestamp() if record.published_at is not None else 0.0


class _Store(GenerationStore):
    """A join store registered as a class, recording each layer status at `delete_source`.

    `test_corpus_layer_joins_through_adrap._JoinStore` — `carry_forward`, a reader of each
    layer's newest published generation, a `supersede` that deletes what it replaces — registered
    as a class over one class-held `State`, as `test_delete_stales_corpus_layers._Store` is, so
    `weft delete`'s fan-out counts it. `released` records, at each `delete_source`, the corpus
    layer's status on every other source's record.
    """

    shared: ClassVar[State] = State()
    published: ClassVar[int] = 0
    released: ClassVar[list[tuple[SourceId, dict[SourceId, LayerStatus]]]] = []

    def __init__(self, config: object = None, generation: GenerationId | None = None) -> None:
        del config
        super().__init__(_Store.shared, generation)

    def _touch(self) -> frozenset[str]:
        if self._published is None:
            newest: dict[str, GenerationRecord] = {}
            for record in self._state.generations.values():
                if record.status is not GenerationStatus.PUBLISHED:
                    continue
                held = newest.get(record.layer)
                if held is None or _published_at(record) > _published_at(held):
                    newest[record.layer] = record
            self._published = frozenset(record.id for record in newest.values())
        return self._published

    async def publish_generation(self, generation: GenerationId) -> GenerationRecord:
        _Store.published += 1
        base = await super().publish_generation(generation)
        record = base.model_copy(
            update={"published_at": base.opened_at + timedelta(hours=_Store.published)}
        )
        self._state.generations[generation] = record
        return record

    async def carry_forward(self, into: GenerationId, node_ids: Sequence[NodeId]) -> int:
        self._known(into)
        distinct = list(dict.fromkeys(node_ids))
        for node_id in distinct:
            self._state.members[node_id].add(into)
        return len(distinct)

    async def supersede(self, old: NodeId, new: Node) -> None:
        await self.add([new])
        self._state.nodes.pop(old, None)
        self._state.members.pop(old, None)

    async def delete_source(self, source_id: SourceId) -> Removed:
        others = {
            record.id: entry.status
            for record in self._state.records.values()
            if record.id != source_id
            for entry in record.layers
            if entry.name == _LAYER
        }
        _Store.released.append((source_id, others))
        return await super().delete_source(source_id)


def _registry() -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _Chunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", _DirectionEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _Store, distribution="weft-store")
    registry.add(Expander, "raptor", _Raptor, distribution="weft-index")
    registry.add(Revisable, "adrap", _Adrap, distribution="weft-index")
    registry.add(Prompt, SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt, distribution="weft-index")
    registry.add(LLMProvider, "scripted", ScriptedModel, distribution="weft-llm")
    registry.add(Command, "ask", commands.AskCommand, distribution="weft-rag")
    registry.add(Command, "delete", commands.DeleteCommand, distribution="weft-rag")
    registry.add(Command, "index", commands.IndexCommand, distribution="weft-rag")
    return registry


def _deps() -> Dependencies:
    return Dependencies(
        registry=_registry(),
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index", "llm")
        ),
        services=ServiceSelection(store="pgvector"),
        llm=llm_section("m1"),
    )


async def _cli(*argv: str) -> render.Rendered:
    """What an operator types, through the shipped parser and `cli.run_command`."""
    deps = _deps()
    args = cli.build_parser(deps.registry).parse_args(list(argv))
    return await cli.run_command(argv[0], args, deps)


def _write_layer(project: Path) -> None:
    shared = (
        "      cluster_size: 8\n"
        "      similarity_threshold: 0.5\n"
        "      max_concurrent_summaries: 1\n"
    )
    (project / "pipelines").mkdir(exist_ok=True)
    (project / "pipelines" / f"{_LAYER}.yaml").write_text(
        f"name: {_LAYER}\n"
        "vars:\n  layer.scope: corpus\n  layer.incremental: join\n"
        "stages:\n"
        f"  - id: raptor\n    use: raptor\n    with:\n{shared}"
        f"  - id: join\n    use: adrap\n    with:\n{shared}"
    )


def _write(corpus: Path, name: str, *, says: str = "") -> None:
    words = {"n": "NORTHWARD", "e": "EASTWARD"}
    (corpus / f"{name}.txt").write_text(f"document {name} points {words[name[0]]}{says}.")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in _FIRST:
        _write(docs, name)
    _write_layer(tmp_path)
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    monkeypatch.setattr(_Store, "shared", State())
    monkeypatch.setattr(_Store, "published", 0)
    monkeypatch.setattr(_Store, "released", [])
    monkeypatch.setattr(_Handed, "calls", [])
    monkeypatch.setattr(_Chunker, "mode", "failed")
    yield docs
    ScriptedModel.reset()


async def _built(corpus: Path) -> GenerationRecord:
    """The tree over `_FIRST`, published, with the stage and release logs cleared after it."""
    rendered = await _cli("index", str(corpus), "--layers", _LAYER)
    assert rendered.exit_code is ExitCode.SUCCESS
    (built,) = _published()
    assert len(_visible_summaries()) == 2, "the arrangement should build one tree of two clusters"
    _Handed.calls = []
    _Store.released = []
    return built


def _published() -> list[GenerationRecord]:
    return [g for g in _Store.shared.generations.values() if g.status is GenerationStatus.PUBLISHED]


def _visible_summaries() -> list[Node]:
    """Every summary a fresh reader is served: one its layer's newest publish holds."""
    newest = max(_published(), key=_published_at)
    return [
        node
        for node in _Store.shared.nodes.values()
        if node.ext_as(RaptorFacts) is not None
        and newest.id in _Store.shared.members.get(node.id, set())
    ]


def _names(sources: frozenset[SourceId] | set[SourceId]) -> set[str]:
    by_id = {
        r.id: r.uri.rsplit("/", 1)[-1].removesuffix(".txt") for r in _Store.shared.records.values()
    }
    return {by_id[s] for s in sources if s in by_id}


def _covered() -> set[str]:
    """Every source some summary of the served tree names."""
    return _names({s for summary in _visible_summaries() for s in summary.lineage.sources})


def _layer_statuses() -> dict[str, LayerStatus]:
    return {
        record.uri.rsplit("/", 1)[-1].removesuffix(".txt"): entry.status
        for record in _Store.shared.records.values()
        for entry in record.layers
        if entry.name == _LAYER
    }


def _stale_line() -> str:
    return render.stale_deleted_layer_line(_LAYER)


def _summarised_leaf_texts() -> list[str]:
    return [
        _Store.shared.nodes[parent].content
        for summary in _visible_summaries()
        for parent in summary.lineage.parents
        if parent in _Store.shared.nodes
    ]


class _Routed:
    """`run_routed_ask`, answering nothing and keeping the `ready_layers` it was offered."""

    def __init__(self) -> None:
        self.ready: frozenset[str] | None = None

    async def __call__(self, *_args: object, **kwargs: object) -> tuple[str, object]:
        ready = kwargs.get("ready_layers")
        assert isinstance(ready, frozenset)
        self.ready = cast("frozenset[str]", ready)
        raise _RoutedError


class _RoutedError(Exception):
    pass


async def _ready_for_routing(monkeypatch: pytest.MonkeyPatch) -> frozenset[str] | None:
    """The layers `weft ask` offers the router as ready, read where the router reads them."""
    routed = _Routed()
    monkeypatch.setattr(commands, "run_routed_ask", routed)
    with suppress(_RoutedError):
        await _cli("ask", "what does the corpus say?")
    return routed.ready


_REMAINING = {"n1", "n3", "e1", "e2", "e3"}
_EVERY = {*_REMAINING, "n2"}


async def _reparse(corpus: Path, *argv: str) -> render.Rendered:
    _write(corpus, "n2", says=" anew")
    return await _cli("index", str(corpus), *argv)


async def _reparse_then_layers(corpus: Path) -> render.Rendered:
    await _reparse(corpus)
    return await _cli("index", str(corpus), "--layers", _LAYER)


async def _delete_then_layers(corpus: Path) -> render.Rendered:
    (removed,) = (r.id for r in _Store.shared.records.values() if r.uri.endswith("/n2.txt"))
    (corpus / "n2.txt").unlink()
    deleted = await _cli("delete", str(removed), "--yes")
    assert deleted.exit_code is ExitCode.SUCCESS
    return await _cli("index", str(corpus), "--layers", _LAYER)


@pytest.mark.parametrize(
    ("route", "covers"),
    [
        pytest.param("reparse-same-run", _EVERY, id="reparsed-in-the-layer-run"),
        pytest.param("reparse-next-run", _EVERY, id="reparsed-then-layer-run"),
        pytest.param("reparse-reprocess", _EVERY, id="reparsed-under-reprocess"),
        pytest.param("deleted", _REMAINING, id="deleted-then-layer-run"),
    ],
)
async def test_a_released_source_ends_in_a_rebuilt_tree_not_a_join_into_the_hole(
    corpus: Path, route: str, covers: set[str]
) -> None:
    """R43.41: a released source ends in a rebuilt tree, not a join into the hole.

    R43.41 — releasing a covered source removes its summaries, so the next layer run owes the
    whole tree, as a deletion already does (task 43.23's `stale-by-deletion-rebuilds`).
    """
    # Arrange
    built = await _built(corpus)

    # Act
    if route == "reparse-same-run":
        rendered = await _reparse(corpus, "--layers", _LAYER)
    elif route == "reparse-next-run":
        rendered = await _reparse_then_layers(corpus)
    elif route == "reparse-reprocess":
        rendered = await _reparse(corpus, "--layers", _LAYER, "--reprocess")
    else:
        rendered = await _delete_then_layers(corpus)

    # Assert
    assert _Handed.calls == [("raptor", len(covers))]
    assert _covered() == covers
    assert _layer_statuses() == dict.fromkeys(covers, LayerStatus.ACTIVE)
    (served,) = _published()
    assert served.id != built.id
    assert rendered.exit_code is ExitCode.SUCCESS
    assert rendered.stdout is not None
    assert "is stale" not in rendered.stdout
    assert f"layer '{_LAYER}': joined" not in rendered.stdout


async def test_the_rebuilt_tree_summarises_the_reparsed_text(corpus: Path) -> None:
    """R43.41 — the tree the layer run publishes is over the new parse, not the released one."""
    # Arrange
    await _built(corpus)

    # Act
    await _reparse_then_layers(corpus)

    # Assert
    texts = _summarised_leaf_texts()
    assert any("n2 points NORTHWARD anew" in text for text in texts)
    assert not any("n2 points NORTHWARD." in text for text in texts)


async def test_a_successful_reparse_marks_every_other_source_stale_and_says_so(
    corpus: Path,
) -> None:
    """R43.41: a successful reparse marks every other source stale and says so.

    R43.41 — the run that re-parses a covered source reports the tree it holed, and the
    re-parsed source itself carries no layer record, as R43.33 excludes the deleted one.
    """
    # Arrange
    await _built(corpus)

    # Act
    rendered = await _reparse(corpus)

    # Assert
    assert _layer_statuses() == dict.fromkeys(_REMAINING, LayerStatus.STALE)
    assert rendered.stdout is not None
    lines = rendered.stdout.splitlines()
    assert _stale_line() in lines
    assert [line for line in lines if f"'{_LAYER}'" in line] == [_stale_line()]
    assert rendered.exit_code is ExitCode.SUCCESS


async def test_the_layer_is_marked_stale_before_the_reparsed_source_is_released(
    corpus: Path,
) -> None:
    """R43.41: the layer is marked stale before the reparsed source is released.

    R43.41, on R43.33's ordering — a tree is marked before it is holed, so an interruption
    between the two never leaves it read as whole.
    """
    # Arrange
    await _built(corpus)

    # Act
    await _reparse(corpus)

    # Assert
    (at_release,) = [others for released, others in _Store.released if _names({released}) == {"n2"}]
    assert _names(set(at_release)) == _REMAINING
    assert set(at_release.values()) == {LayerStatus.STALE}


_FAILURES = [
    pytest.param("failed", id="stage-returns-failed"),
    pytest.param("raises", id="stage-raises"),
    pytest.param("cancelled", id="run-interrupted"),
]


async def _reparse_unreadably(corpus: Path, mode: str) -> render.Rendered | None:
    _Chunker.mode = mode
    _write(corpus, "n2", says=f" but is {_UNREADABLE}")
    try:
        return await _cli("index", str(corpus))
    except asyncio.CancelledError:
        return None


@pytest.mark.parametrize("mode", _FAILURES)
async def test_a_reparse_that_does_not_finish_leaves_the_layer_stale_and_not_ready(
    corpus: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """R43.41: a reparse that does not finish leaves the layer stale and not ready.

    R43.41 — the source's earlier parse was released, so the tree it was in is missing a
    cluster, and the router must not be offered it as ready.
    """
    # Arrange
    await _built(corpus)
    ready_before = await _ready_for_routing(monkeypatch)

    # Act
    await _reparse_unreadably(corpus, mode)

    # Assert
    assert ready_before is not None
    assert _LAYER in ready_before
    ready_after = await _ready_for_routing(monkeypatch)
    assert ready_after is not None
    assert _LAYER not in ready_after
    assert _layer_statuses() == dict.fromkeys(_REMAINING, LayerStatus.STALE)


async def test_a_reparse_that_fails_says_in_the_same_run_that_the_layer_is_stale(
    corpus: Path,
) -> None:
    """R43.41 — the run that holed the tree is the one that reports it, beside the failure."""
    # Arrange
    await _built(corpus)

    # Act
    rendered = await _reparse_unreadably(corpus, "failed")

    # Assert
    assert rendered is not None
    assert rendered.stdout is not None
    lines = rendered.stdout.splitlines()
    assert _stale_line() in lines
    assert [line for line in lines if f"'{_LAYER}'" in line] == [_stale_line()]
    assert rendered.exit_code is ExitCode.OPERATION_FAILED


@pytest.mark.parametrize("mode", _FAILURES)
async def test_the_printed_remedy_after_an_unfinished_reparse_rebuilds_the_tree(
    corpus: Path, mode: str
) -> None:
    """R43.41: the printed remedy after an unfinished reparse rebuilds the tree.

    R43.41 — `weft index --layers <name>`, the remedy the stale line prints, rebuilds the tree
    over the sources that remain rather than finding every eligible record `ACTIVE`.
    """
    # Arrange
    built = await _built(corpus)
    await _reparse_unreadably(corpus, mode)
    _Chunker.mode = "failed"
    _Handed.calls = []

    # Act
    rendered = await _cli("index", str(corpus), "--layers", _LAYER)

    # Assert
    assert _Handed.calls == [("raptor", len(_REMAINING))]
    assert _covered() == _REMAINING
    assert _layer_statuses() == dict.fromkeys(_REMAINING, LayerStatus.ACTIVE)
    (served,) = _published()
    assert served.id != built.id
    assert rendered.stdout is not None
    assert "is stale" not in rendered.stdout


async def test_an_added_source_still_joins_the_published_tree(corpus: Path) -> None:
    """R43.41's guard — a pure addition releases nothing, so task 43.23's join still runs."""
    # Arrange
    await _built(corpus)
    _write(corpus, "n4")

    # Act
    rendered = await _cli("index", str(corpus), "--layers", _LAYER)

    # Assert
    assert _Handed.calls == [("adrap", 1)]
    assert _covered() == {*_EVERY, "n4"}
    assert _layer_statuses() == dict.fromkeys({*_EVERY, "n4"}, LayerStatus.ACTIVE)
    assert rendered.stdout is not None
    assert f"layer '{_LAYER}': joined 1 leaves, 0 unassigned" in rendered.stdout.splitlines()
    assert "is stale" not in rendered.stdout


async def test_an_unchanged_reindex_releases_nothing_and_keeps_the_tree(corpus: Path) -> None:
    """R43.41's guard — an unchanged source is not released, so nothing is marked or rebuilt."""
    # Arrange
    built = await _built(corpus)

    # Act
    rendered = await _cli("index", str(corpus), "--layers", _LAYER)

    # Assert
    assert _Handed.calls == []
    assert _Store.released == []
    assert _published() == [built]
    assert _layer_statuses() == dict.fromkeys(_EVERY, LayerStatus.ACTIVE)
    assert rendered.stdout is not None
    assert "is stale" not in rendered.stdout
