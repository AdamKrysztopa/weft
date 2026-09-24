"""Ledger task **43.21** — deleting a source leaves every corpus-scoped layer that covered it stale.

A corpus-scoped layer (`layer.scope: corpus`, `43.15`) is one tree over every source, and a node
it made is produced by that whole source set, so `weft delete` removes it outright. Before this
task the other sources' records still read `ACTIVE`, the generation stayed published, and routing
served a tree with a hole in it. Now the delete demotes that layer's record on every remaining
source to `LayerStatus.STALE` and prints one line per layer it demoted; `weft index` says so;
`weft sources list` shows it; the router withholds a rung requiring it; and `weft index --layers`
rebuilds it to `ACTIVE`. A source-scoped layer is untouched: its nodes left with their source.

The delete learns which layers are corpus-scoped the way `weft index`'s own stale report does
(`weft_cli.layers._corpus_scoped_layer_names`, over the installed layer documents), and demotes
only a layer the deleted source itself carried `ACTIVE`: a tree that never covered it has no hole.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Self

import pytest

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli import cli, commands, render
from weft_cli.exit_codes import ExitCode
from weft_cli.ingest import IndexResult, run_index
from weft_command.contract import Command
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_generate.payload import Answer, AnswerStance
from weft_index import Expander
from weft_index.payload import Representation
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import (
    MediaType,
    Node,
    NodeId,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
    Vector,
)
from weft_kernel.registry import Registry
from weft_retrieve.payload import Query
from weft_store import NodeStore
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    LayerStatus,
    Page,
    Removed,
    SourceRecord,
    UnknownGenerationError,
)

_PAGE = 2
_WHEN_OPENED = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
_CORPUS = "enrich-with-summary"
_PER_SOURCE = "enrich-with-questions"
_RUNG = "needs-summary"
_STALE_LINE = (
    f"layer '{_CORPUS}' is stale: a source it covered was deleted — "
    f"weft index --layers {_CORPUS} rebuilds it."
)


def _holds(node: Node, filter: Filter) -> bool:
    if filter.op is FilterOp.AND:
        return all(_holds(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.NOT:
        return not _holds(node, filter.clauses[0])
    if filter.op is FilterOp.IN and filter.field == "lineage.sources":
        wanted = filter.value if isinstance(filter.value, tuple) else (filter.value,)
        return bool(set(node.lineage.sources) & {SourceId(str(value)) for value in wanted})
    if filter.op is FilterOp.EXISTS and filter.field is not None:
        _, namespace, *_ = filter.field.split(".")
        return namespace in node.ext
    raise AssertionError(f"the layer selection used an operator this double lacks: {filter}")


class _State:
    """What every handle onto the one store shares: nodes, records, generations, members."""

    def __init__(self) -> None:
        self.nodes: dict[NodeId, Node] = {}
        self.members: dict[NodeId, set[str]] = {}
        self.records: dict[SourceId, SourceRecord] = {}
        self.generations: dict[GenerationId, GenerationRecord] = {}


class _Store:
    """`test_corpus_layers`' `_GenerationStore`, registered as a class so `weft delete`'s fan-out
    (which asks `issubclass` of what was registered) counts it as a participant. Every instance
    reads the one class-held `state`, as every connection to one database would."""

    state: ClassVar[_State] = _State()

    def __init__(self, config: object = None, generation: GenerationId | None = None) -> None:
        del config
        self._generation = generation
        self._published: frozenset[str] | None = None

    def _touch(self) -> frozenset[str]:
        if self._published is None:
            self._published = frozenset(
                g
                for g, r in self.state.generations.items()
                if r.status is GenerationStatus.PUBLISHED
            )
        return self._published

    def _visible(self, node: Node) -> bool:
        own: set[str] = {self._generation} if self._generation else set()
        seen: frozenset[str] = self._touch() | {""} | own
        return bool(self.state.members.get(node.id, {""}) & seen)

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        self._touch()
        marker = self._generation or ""
        for node in nodes:
            self.state.nodes[node.id] = node
            self.state.members.setdefault(node.id, set()).add(marker)

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return len(self.state.nodes)

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self.state.nodes[i] for i in ids if i in self.state.nodes)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        return Page(items=tuple(self.state.nodes.values()))

    async def delete_source(self, source_id: SourceId) -> Removed:
        doomed = [i for i, n in self.state.nodes.items() if source_id in n.lineage.sources]
        for i in doomed:
            del self.state.nodes[i]
            self.state.members.pop(i, None)
        self.state.records.pop(source_id, None)
        return Removed(source_id=source_id, node_count=len(doomed))

    async def put_source(self, record: SourceRecord) -> None:
        self.state.records[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return self.state.records.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self.state.records.values())

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        selected = sorted(
            (n for n in self.state.nodes.values() if self._visible(n) and _holds(n, filter)),
            key=lambda n: n.id,
        )
        start = int(cursor) if cursor is not None else 0
        end = start + _PAGE
        return Page(
            items=tuple(selected[start:end]),
            next_cursor=Cursor(str(end)) if end < len(selected) else None,
        )

    async def open_generation(self, layer: str) -> GenerationRecord:
        record = GenerationRecord(
            id=GenerationId(f"g-{len(self.state.generations) + 1}"),
            layer=layer,
            status=GenerationStatus.BUILDING,
            opened_at=_WHEN_OPENED,
        )
        self.state.generations[record.id] = record
        return record

    def _known(self, generation: GenerationId) -> GenerationRecord:
        if generation not in self.state.generations:
            raise UnknownGenerationError(generation, valid_options=tuple(self.state.generations))
        return self.state.generations[generation]

    async def bind_generation(self, generation: GenerationId) -> Self:
        self._known(generation)
        return type(self)(None, generation)

    async def publish_generation(self, generation: GenerationId) -> GenerationRecord:
        record = self._known(generation).model_copy(
            update={"status": GenerationStatus.PUBLISHED, "published_at": _WHEN_OPENED}
        )
        self.state.generations[generation] = record
        return record

    async def retract_generation(self, generation: GenerationId) -> Removed:
        self._known(generation)
        doomed = [i for i, m in self.state.members.items() if m == {generation}]
        for i in doomed:
            self.state.nodes.pop(i, None)
            del self.state.members[i]
        for m in self.state.members.values():
            m.discard(generation)
        del self.state.generations[generation]
        return Removed(source_id=SourceId(generation), node_count=len(doomed))

    async def generations(self) -> tuple[GenerationRecord, ...]:
        return tuple(self.state.generations.values())


class _Summary:
    """A corpus-scope `Expander`: every leaf back, plus one summary over all of them, embedded
    by this stage itself, as `raptor` embeds its own summaries."""

    calls: ClassVar[list[int]] = []

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        _Summary.calls.append(len(payload))
        if not payload:
            return NothingToProduce(reason="no leaves")
        summary = (
            Node.combine(payload, content="a summary of everything", media_type=MediaType.TEXT)
            .with_ext(Representation(technique="echo-summary"))
            .with_embedding(Vector(values=tuple(0.5 for _ in range(64))))
        )
        return Produced(value=(*payload, summary))


class _Question:
    """A source-scope `Expander`: every leaf back, plus one question derived from each."""

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no leaves")
        derived = tuple(
            node.derive(
                content=f"what does {node.content[:12]!r} say?", media_type=MediaType.TEXT
            ).with_ext(Representation(technique="echo-question"))
            for node in payload
        )
        return Produced(value=(*payload, *derived))


def _registry() -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _Store, distribution="weft-store")
    registry.add(Expander, "echo-summary", _Summary, distribution="weft-index")
    registry.add(Expander, "echo-question", _Question, distribution="weft-index")
    return registry


def _run_ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _command_ctx() -> Context:
    deps = Dependencies(
        registry=_registry(),
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index")
        ),
        services=ServiceSelection(store="pgvector"),
    )
    ctx = _run_ctx()
    ctx.services.add(Dependencies, deps)
    return ctx


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Three sources, one corpus-scoped layer and one source-scoped layer, on one store."""
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in ("a", "b", "c"):
        (docs / f"{name}.txt").write_text(f"document {name} says something of its own.")
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    (pipelines / f"{_CORPUS}.yaml").write_text(
        f"name: {_CORPUS}\n"
        "vars:\n  layer.scope: corpus\n"
        "stages:\n  - {id: summary, use: echo-summary}\n"
    )
    (pipelines / f"{_PER_SOURCE}.yaml").write_text(
        f"name: {_PER_SOURCE}\nstages:\n  - {{id: questions, use: echo-question}}\n"
    )
    (pipelines / f"{_RUNG}.yaml").write_text(
        f"name: {_RUNG}\n"
        "vars:\n"
        "  route.summary: answers from the summary of the whole corpus\n"
        f"  route.requires: {_CORPUS}\n"
        "stages:\n"
        "  - {id: retrieve, use: vector-top-k}\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_Store, "state", _State())
    monkeypatch.setattr(_Summary, "calls", [])
    return docs


async def _index(corpus: Path, *, layers: tuple[str, ...] = ()) -> IndexResult:
    return await run_index(
        corpus, registry=_registry(), ctx=_run_ctx(), batch_size=4, layers=layers
    )


async def _index_both(corpus: Path) -> None:
    await _index(corpus, layers=(_CORPUS, _PER_SOURCE))


def _id_of(name: str) -> SourceId:
    (found,) = (i for i, r in _Store.state.records.items() if r.uri.endswith(f"/{name}"))
    return found


def _layer_statuses(layer: str) -> dict[str, LayerStatus]:
    return {
        record.uri.rsplit("/", 1)[-1]: entry.status
        for record in _Store.state.records.values()
        for entry in record.layers
        if entry.name == layer
    }


async def _delete(source_id: str) -> render.Rendered:
    outcome = await commands.DeleteCommand().run(
        commands.DeleteArgs(source_id=source_id), _command_ctx()
    )
    assert isinstance(outcome, Produced)
    return render.render_outcome(outcome)


async def _delete_file(corpus: Path, name: str) -> render.Rendered:
    """What an operator does: remove the file, then `weft delete` the source it was."""
    source = _id_of(name)
    (corpus / name).unlink()
    return await _delete(str(source))


async def test_deleting_a_source_stales_the_corpus_layer_and_leaves_the_source_layer_active(
    corpus: Path,
) -> None:
    # Arrange
    await _index_both(corpus)
    assert _layer_statuses(_CORPUS) == dict.fromkeys(
        ("a.txt", "b.txt", "c.txt"), LayerStatus.ACTIVE
    )

    # Act
    await _delete_file(corpus, "b.txt")

    # Assert — scope is the one fact varied between the two layers.
    assert _layer_statuses(_CORPUS) == {"a.txt": LayerStatus.STALE, "c.txt": LayerStatus.STALE}
    assert _layer_statuses(_PER_SOURCE) == {
        "a.txt": LayerStatus.ACTIVE,
        "c.txt": LayerStatus.ACTIVE,
    }


async def test_the_delete_names_the_layer_it_staled_and_not_the_source_scoped_one(
    corpus: Path,
) -> None:
    # Arrange
    await _index_both(corpus)

    # Act
    rendered = await _delete_file(corpus, "b.txt")

    # Assert
    assert rendered.stdout is not None
    lines = rendered.stdout.splitlines()
    assert _STALE_LINE in lines
    assert [line for line in lines if "is stale" in line] == [_STALE_LINE]
    assert _PER_SOURCE not in rendered.stdout
    assert rendered.exit_code is ExitCode.SUCCESS


async def test_deleting_a_source_the_corpus_layer_never_covered_leaves_it_active(
    corpus: Path,
) -> None:
    # Arrange — `d.txt` arrives after the tree was built, so no summary node names it.
    await _index_both(corpus)
    (corpus / "d.txt").write_text("document d arrives after the tree was built.")
    await _index(corpus)

    # Act
    rendered = await _delete_file(corpus, "d.txt")

    # Assert — the tree has no hole: the three it covered are all still indexed.
    assert _layer_statuses(_CORPUS) == dict.fromkeys(
        ("a.txt", "b.txt", "c.txt"), LayerStatus.ACTIVE
    )
    assert rendered.stdout is not None
    assert "is stale" not in rendered.stdout


async def test_deleting_an_id_nothing_holds_stales_nothing(corpus: Path) -> None:
    # Arrange
    await _index_both(corpus)

    # Act
    rendered = await _delete("/corpus/typo.txt")

    # Assert
    assert _layer_statuses(_CORPUS) == dict.fromkeys(
        ("a.txt", "b.txt", "c.txt"), LayerStatus.ACTIVE
    )
    assert rendered.stdout is not None
    assert "is stale" not in rendered.stdout


async def _index_command(corpus: Path, **flags: object) -> render.Rendered:
    outcome = await commands.IndexCommand().run(
        commands.IndexArgs.model_validate({"path": str(corpus), **flags}), _command_ctx()
    )
    return render.render_outcome(outcome)


async def test_weft_index_says_a_layer_is_stale_after_a_source_it_covered_was_deleted(
    corpus: Path,
) -> None:
    # Arrange
    await _index_both(corpus)
    await _delete_file(corpus, "b.txt")

    # Act
    rendered = await _index_command(corpus, layers="none")

    # Assert
    assert rendered.stdout is not None
    assert _STALE_LINE in rendered.stdout.splitlines()
    assert "built over" not in rendered.stdout
    assert rendered.exit_code is ExitCode.SUCCESS


async def test_a_layer_stale_by_a_deletion_and_behind_an_added_source_is_one_line(
    corpus: Path,
) -> None:
    # Arrange — `d.txt` carries no summary record, and `a`/`c` carry a stale one.
    await _index_both(corpus)
    await _delete_file(corpus, "b.txt")
    (corpus / "d.txt").write_text("document d arrives after the delete.")

    # Act
    rendered = await _index_command(corpus, layers="none")

    # Assert
    assert rendered.stdout is not None
    assert [line for line in rendered.stdout.splitlines() if f"'{_CORPUS}'" in line] == [
        _STALE_LINE
    ]


async def test_weft_index_naming_the_stale_layer_rebuilds_it_active_over_what_remains(
    corpus: Path,
) -> None:
    # Arrange
    await _index_both(corpus)
    await _delete_file(corpus, "b.txt")
    _Summary.calls = []

    # Act
    rendered = await _index_command(corpus, layers=_CORPUS)

    # Assert
    assert _Summary.calls == [2]
    assert _layer_statuses(_CORPUS) == {"a.txt": LayerStatus.ACTIVE, "c.txt": LayerStatus.ACTIVE}
    (generation,) = await _Store().generations()
    assert generation.status is GenerationStatus.PUBLISHED
    assert rendered.stdout is not None
    assert "is stale" not in rendered.stdout


async def test_sources_list_shows_the_stale_layer_beside_the_active_one(corpus: Path) -> None:
    # Arrange
    await _index_both(corpus)
    await _delete_file(corpus, "b.txt")

    # Act
    outcome = await commands.SourcesListCommand().run(commands.SourcesListArgs(), _command_ctx())
    rendered = render.render_outcome(outcome)

    # Assert
    assert rendered.stdout is not None
    lines = rendered.stdout.splitlines()
    assert len(lines) == 2
    for line in lines:
        assert f"{_CORPUS} stale" in line
        assert f"{_PER_SOURCE} active" in line


def _answer() -> Answer:
    return Answer(
        origin=Query(text="what is this corpus about?"),
        text="the answer",
        stance=AnswerStance.ANSWERED,
        citations=(),
        used=(),
        answered_by="scripted",
    )


class _Named:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, *_args: object, **_kwargs: object) -> Answer:
        self.called = True
        return _answer()


class _Routed:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def __call__(self, *_args: object, **kwargs: object) -> tuple[str, Answer]:
        self.kwargs = kwargs
        return "retrieve-then-generate", _answer()


async def test_the_router_stops_offering_the_rung_once_its_layer_is_stale(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    routed = _Routed()
    monkeypatch.setattr(commands, "run_routed_ask", routed)
    await _index_both(corpus)
    await commands.AskCommand().run(
        commands.AskArgs(question="what is this corpus about?"), _command_ctx()
    )
    ready_before = routed.kwargs.get("ready_layers")
    await _delete_file(corpus, "b.txt")

    # Act
    await commands.AskCommand().run(
        commands.AskArgs(question="what is this corpus about?"), _command_ctx()
    )

    # Assert
    assert isinstance(ready_before, frozenset)
    assert _CORPUS in ready_before
    ready_after = routed.kwargs.get("ready_layers")
    assert isinstance(ready_after, frozenset)
    assert _CORPUS not in ready_after
    assert _PER_SOURCE in ready_after


async def test_naming_the_rung_over_a_stale_layer_is_refused_naming_the_layer(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    named = _Named()
    monkeypatch.setattr(commands, "run_named_ask", named)
    await _index_both(corpus)
    await _delete_file(corpus, "b.txt")

    # Act
    with pytest.raises(commands.PendingLayerError) as refused:
        await commands.AskCommand().run(
            commands.AskArgs(question="what is this corpus about?", pipeline=_RUNG),
            _command_ctx(),
        )

    # Assert
    message = str(refused.value)
    assert f"'{_RUNG}'" in message
    assert f"'{_CORPUS}'" in message
    assert f"--layers {_CORPUS}" in message
    assert not named.called


def _cli_deps() -> Dependencies:
    deps = _command_ctx().require(Dependencies)
    deps.registry.add(Command, "delete", commands.DeleteCommand, distribution="weft-rag")
    deps.registry.add(Command, "index", commands.IndexCommand, distribution="weft-rag")
    return deps


async def _cli(*argv: str) -> render.Rendered:
    """What an operator types, through the shipped parser and `cli.run_command`."""
    deps = _cli_deps()
    args = cli.build_parser(deps.registry).parse_args(list(argv))
    return await cli.run_command(argv[0], args, deps)


async def _refuse(self: _Store, record: SourceRecord) -> None:
    del self, record
    raise RuntimeError("the records table is read-only")


async def test_a_demotion_that_fails_stops_the_delete_before_anything_is_removed(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R43.33 — a tree is marked before it is holed: a mark that cannot be written leaves the
    source, its nodes and every tree whole, and the refusal says so and names the retry."""
    # Arrange
    await _index_both(corpus)
    monkeypatch.setattr(_Store, "put_source", _refuse)
    deleted = _id_of("b.txt")
    nodes_before = set(_Store.state.nodes)
    (corpus / "b.txt").unlink()

    # Act
    rendered = await _cli("delete", str(deleted), "--yes")

    # Assert
    assert rendered.exit_code is ExitCode.OPERATION_FAILED
    assert rendered.stderr is not None
    assert f"'{deleted}' was not deleted" in rendered.stderr
    assert f"marking corpus layer(s) {_CORPUS} stale failed" in rendered.stderr
    assert f"weft delete {deleted} again" in rendered.stderr
    assert deleted in _Store.state.records
    assert set(_Store.state.nodes) == nodes_before
    assert _layer_statuses(_CORPUS) == dict.fromkeys(
        ("a.txt", "b.txt", "c.txt"), LayerStatus.ACTIVE
    )


async def test_the_remedy_a_failed_demotion_prints_ends_with_the_layer_rebuilt(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R43.33 — the retry the refusal prints, then the rebuild the retry prints, run the stage
    again over what remains and publish a new tree in place of the one that lost a source."""
    # Arrange
    await _index_both(corpus)
    (built,) = await _Store().generations()
    healthy = _Store.put_source
    monkeypatch.setattr(_Store, "put_source", _refuse)
    deleted = _id_of("b.txt")
    (corpus / "b.txt").unlink()
    refused = await _cli("delete", str(deleted), "--yes")
    assert f"weft delete {deleted} again" in (refused.stderr or "")
    monkeypatch.setattr(_Store, "put_source", healthy)
    _Summary.calls = []

    # Act
    retried = await _cli("delete", str(deleted), "--yes")
    rebuilt = await _cli("index", str(corpus), "--layers", _CORPUS)

    # Assert
    assert retried.exit_code is ExitCode.SUCCESS
    assert retried.stdout is not None
    assert _STALE_LINE in retried.stdout.splitlines()
    assert _Summary.calls == [2]
    assert deleted not in _Store.state.records
    assert _layer_statuses(_CORPUS) == {"a.txt": LayerStatus.ACTIVE, "c.txt": LayerStatus.ACTIVE}
    published = [g for g in await _Store().generations() if g.status is GenerationStatus.PUBLISHED]
    assert len(published) == 1
    assert published[0].id != built.id
    assert rebuilt.exit_code is ExitCode.SUCCESS
    assert rebuilt.stdout is not None
    assert "is stale" not in rebuilt.stdout


async def test_a_corpus_layer_only_the_deleted_source_held_is_not_reported_stale(
    corpus: Path,
) -> None:
    """R43.33 — marking before the fan-out must not count the source being deleted: a tree no
    remaining source carries has no remaining source to be stale on."""
    # Arrange — the tree is built while `a.txt` is the only document.
    texts = {name: (corpus / name).read_text() for name in ("b.txt", "c.txt")}
    for name in texts:
        (corpus / name).unlink()
    await _index(corpus, layers=(_CORPUS,))
    for name, text in texts.items():
        (corpus / name).write_text(text)
    await _index(corpus)

    # Act
    rendered = await _delete_file(corpus, "a.txt")

    # Assert
    assert rendered.stdout is not None
    assert "is stale" not in rendered.stdout
    assert _layer_statuses(_CORPUS) == {}
