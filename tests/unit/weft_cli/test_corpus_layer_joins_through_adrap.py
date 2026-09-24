"""Ledger task **43.23** — a corpus layer stale by addition is joined through adRAP, not rebuilt.

A corpus-scoped layer document declares its incremental stage by id, `layer.incremental: join`,
beside the stage that builds the tree. A full build runs every stage but that one; a run over a
layer that is stale **only by addition** runs that one alone, over the leaves of the sources the
tree does not cover, into a generation that carries every summary it does not replace. Stale by
deletion is rebuilt in full, since a join cannot remove a member. Each join prints
`layer '<name>': joined n leaves, m unassigned`.

Leaves are embedded by direction, so which cluster a leaf joins is set by its text: `NORTHWARD`
and `EASTWARD` leaves form one cluster each, and an `UPWARD` leaf is orthogonal to both.
"""

from collections.abc import Iterator, Sequence
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import ClassVar

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    GenerationStore,
    ScriptedModel,
    State,
    llm_section,
    make_ctx,
)
from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli import render
from weft_cli.commands import IndexCommandResult
from weft_cli.ingest import IndexResult, run_index
from weft_cli.layers import LayerJoin, compose_layer
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine import registry_bootstrap
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_index import Expander, Revisable
from weft_index.adrap import AdrapJoiner
from weft_index.payload import RaptorFacts
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import RaptorSummarizer
from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_kernel.registry import Registry
from weft_llm.contract import LLMProvider
from weft_prompts.contract import Prompt
from weft_store import NodeStore
from weft_store.contract import (
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    LayerStatus,
)

LAYER = "enrich-with-tree"
_FIRST = ("n1", "n2", "n3", "e1", "e2", "e3")
_WIDTH = 8
_DIRECTIONS = {"NORTHWARD": 0, "EASTWARD": 1, "UPWARD": 2}
_ELSEWHERE = 3


def _direction(content: str) -> Vector:
    axis = next((i for word, i in _DIRECTIONS.items() if word in content), _ELSEWHERE)
    return Vector(values=tuple(1.0 if i == axis else 0.0 for i in range(_WIDTH)))


class _DirectionEmbedder(HashEmbedder):
    """A leaf's vector is the axis its text names; a summary names none and gets its own."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=tuple(n.with_embedding(_direction(n.content)) for n in payload))


class _Handed:
    """Which layer stage was handed which leaves: `(stage, leaf count, sources)` per call."""

    calls: ClassVar[list[tuple[str, int, frozenset[SourceId]]]] = []

    @classmethod
    def note(cls, stage: str, payload: Sequence[Node]) -> None:
        sources = frozenset(source for node in payload for source in node.lineage.sources)
        cls.calls.append((stage, len(payload), sources))


class _Raptor(RaptorSummarizer):
    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        _Handed.note("raptor", payload)
        return await super().run(payload, ctx)


class _Adrap(AdrapJoiner):
    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        _Handed.note("adrap", payload)
        return await super().run(payload, ctx)


class _JoinStore(GenerationStore):
    """`GenerationStore` plus `GenerationCarrying.carry_forward` (task 43.22), a reader that sees
    only each layer's newest published generation (R43.25), and a `supersede` that deletes from
    whatever holds the node, as the shipped stores' does.

    `reader` is a handle opened before the join; `at_publish` records, as each generation is
    published, what `reader` sees and what the generation holds.
    """

    reader: ClassVar["_JoinStore | None"] = None
    at_publish: ClassVar[list[tuple[frozenset[NodeId], frozenset[NodeId]]]] = []
    superseded: ClassVar[list[NodeId]] = []
    published: ClassVar[int] = 0

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

    def snapshot(self) -> None:
        self._touch()

    def summaries_seen(self) -> frozenset[NodeId]:
        return frozenset(
            node.id
            for node in self._state.nodes.values()
            if node.ext_as(RaptorFacts) is not None and self._visible(node)
        )

    def summaries_in(self, generation: GenerationId) -> frozenset[NodeId]:
        return frozenset(
            node.id
            for node in self._state.nodes.values()
            if node.ext_as(RaptorFacts) is not None
            and generation in self._state.members.get(node.id, set())
        )

    async def publish_generation(self, generation: GenerationId) -> GenerationRecord:
        if _JoinStore.reader is not None:
            seen = _JoinStore.reader.summaries_seen()
            _JoinStore.at_publish.append((seen, self.summaries_in(generation)))
        _JoinStore.published += 1
        base = await super().publish_generation(generation)
        record = base.model_copy(
            update={"published_at": base.opened_at + timedelta(hours=_JoinStore.published)}
        )
        self._state.generations[generation] = record
        return record

    async def carry_forward(self, into: GenerationId, node_ids: Sequence[NodeId]) -> int:
        self._known(into)
        published = {
            g for g, r in self._state.generations.items() if r.status is GenerationStatus.PUBLISHED
        }
        distinct = list(dict.fromkeys(node_ids))
        refused = [i for i in distinct if not self._state.members.get(i, set()) & published]
        if refused:
            raise AssertionError(f"carried nodes no published generation holds: {refused}")
        for node_id in distinct:
            self._state.members[node_id].add(into)
        return len(distinct)

    async def supersede(self, old: NodeId, new: Node) -> None:
        _JoinStore.superseded.append(old)
        await self.add([new])
        self._state.nodes.pop(old, None)
        self._state.members.pop(old, None)


def _published_at(record: GenerationRecord) -> float:
    return record.published_at.timestamp() if record.published_at is not None else 0.0


def _factory(store: _JoinStore, config: object) -> _JoinStore:
    del config
    return store


def _registry(store: _JoinStore) -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", _DirectionEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_factory, store), distribution="weft-store")
    registry.add(Expander, "raptor", _Raptor, distribution="weft-index")
    registry.add(Revisable, "adrap", _Adrap, distribution="weft-index")
    registry.add(Prompt, SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt, distribution="weft-index")
    registry.add(LLMProvider, "scripted", ScriptedModel, distribution="weft-llm")
    return registry


def _write_layer(project: Path, *, max_leaves: int = 5_000) -> None:
    shared = (
        "      cluster_size: 8\n"
        "      similarity_threshold: 0.5\n"
        "      max_concurrent_summaries: 1\n"
    )
    (project / "pipelines").mkdir(exist_ok=True)
    (project / "pipelines" / f"{LAYER}.yaml").write_text(
        f"name: {LAYER}\n"
        "vars:\n  layer.scope: corpus\n  layer.incremental: join\n"
        "stages:\n"
        f"  - id: raptor\n    use: raptor\n    with:\n{shared}      max_leaves: {max_leaves}\n"
        f"  - id: join\n    use: adrap\n    with:\n{shared}"
    )


def _write(corpus: Path, *names: str) -> None:
    words = {"n": "NORTHWARD", "e": "EASTWARD", "u": "UPWARD"}
    for name in names:
        (corpus / f"{name}.txt").write_text(f"document {name} points {words[name[0]]}.")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    docs = tmp_path / "docs"
    docs.mkdir()
    _write(docs, *_FIRST)
    _write_layer(tmp_path)
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    monkeypatch.setattr(_Handed, "calls", [])
    monkeypatch.setattr(_JoinStore, "reader", None)
    monkeypatch.setattr(_JoinStore, "at_publish", [])
    monkeypatch.setattr(_JoinStore, "superseded", [])
    monkeypatch.setattr(_JoinStore, "published", 0)
    yield docs
    ScriptedModel.reset()


async def _index(store: _JoinStore, corpus: Path) -> IndexResult:
    return await run_index(
        corpus,
        registry=_registry(store),
        ctx=make_ctx(),
        llm=llm_section("m1"),
        layers=(LAYER,),
    )


async def _built(corpus: Path) -> tuple[_JoinStore, frozenset[NodeId]]:
    """A published tree over `_FIRST`, the model's call log and the stage log cleared after it;
    the next run's summaries are labelled apart, so a rebuilt summary never keeps an old id.
    """
    store = _JoinStore(State())
    await _index(store, corpus)
    old = _fresh(store).summaries_seen()
    assert len(old) == 2, "the arrangement should build one NORTHWARD and one EASTWARD cluster"
    ScriptedModel.calls = []
    ScriptedModel.label = "second"
    _Handed.calls = []
    return store, old


def _fresh(store: _JoinStore) -> _JoinStore:
    reader = _JoinStore(store.state)
    reader.snapshot()
    return reader


def _source(store: _JoinStore, name: str) -> SourceId:
    (found,) = (i for i, r in store.state.records.items() if r.uri.endswith(f"/{name}.txt"))
    return found


def _summary_over(store: _JoinStore, ids: frozenset[NodeId], *names: str) -> Node:
    """The one summary among `ids` whose sources are exactly `names`."""
    wanted = {_source(store, name) for name in names}
    (found,) = (
        store.state.nodes[i] for i in ids if set(store.state.nodes[i].lineage.sources) == wanted
    )
    return found


async def _delete(store: _JoinStore, corpus: Path, name: str) -> None:
    """What `weft delete` leaves (task 43.21): the file and its nodes gone, and the corpus layer
    `STALE` on every remaining source.
    """
    source = _source(store, name)
    (corpus / f"{name}.txt").unlink()
    await store.delete_source(source)
    for record in await store.list_sources():
        layers = tuple(
            entry.model_copy(update={"status": LayerStatus.STALE}) if entry.name == LAYER else entry
            for entry in record.layers
        )
        await store.put_source(record.model_copy(update={"layers": layers}))


def _layer_statuses(store: _JoinStore) -> list[LayerStatus | None]:
    return [
        next((entry.status for entry in record.layers if entry.name == LAYER), None)
        for record in store.state.records.values()
    ]


async def test_only_the_added_sources_leaves_are_offered_and_every_source_is_then_active(
    corpus: Path,
) -> None:
    # Arrange
    store, _ = await _built(corpus)
    _write(corpus, "n4", "n5")

    # Act
    result = await _index(store, corpus)

    # Assert — the join alone ran, over the two new sources' leaves; the tree now covers all.
    added = frozenset({_source(store, "n4"), _source(store, "n5")})
    assert _Handed.calls == [("adrap", 2, added)]
    assert result.layers_failed == ()
    assert result.layers_stale == ()
    assert _layer_statuses(store) == [LayerStatus.ACTIVE] * 8


async def test_the_untouched_summary_keeps_its_id_and_the_joined_one_is_replaced(
    corpus: Path,
) -> None:
    # Arrange
    store, old = await _built(corpus)
    untouched = _summary_over(store, old, "e1", "e2", "e3")
    joined = _summary_over(store, old, "n1", "n2", "n3")
    _write(corpus, "n4", "n5")

    # Act
    await _index(store, corpus)

    # Assert
    after = _fresh(store).summaries_seen()
    assert untouched.id in after
    assert joined.id not in after
    (rebuilt,) = after - {untouched.id}
    assert set(store.state.nodes[rebuilt].lineage.sources) == {
        _source(store, name) for name in ("n1", "n2", "n3", "n4", "n5")
    }


async def test_a_reader_opened_before_the_join_sees_only_the_old_tree_at_its_publish(
    corpus: Path,
) -> None:
    # Arrange
    store, old = await _built(corpus)
    untouched = _summary_over(store, old, "e1", "e2", "e3")
    _write(corpus, "n4", "n5")
    _JoinStore.reader = _fresh(store)

    # Act
    await _index(store, corpus)

    # Assert — the published tree was never edited in place; the new generation carries the
    # untouched summary beside the one rebuilt summary, and nothing else.
    ((seen, held),) = _JoinStore.at_publish
    assert seen == old
    assert untouched.id in held
    assert len(held) == 2
    assert _JoinStore.superseded == []


async def test_the_join_is_reported_with_both_counts_where_the_operator_reads_it(
    corpus: Path,
) -> None:
    # Arrange
    store, _ = await _built(corpus)
    _write(corpus, "n4", "n5")

    # Act
    result = await _index(store, corpus)
    rendered = render.render_outcome(
        Produced(
            value=IndexCommandResult(
                summary=result.summary,
                stored_count=result.stored_count,
                layers_joined=result.layers_joined,
            )
        )
    )

    # Assert
    assert result.layers_joined == (LayerJoin(layer=LAYER, joined=2, unassigned=0),)
    assert rendered.stdout is not None
    assert f"layer '{LAYER}': joined 2 leaves, 0 unassigned" in rendered.stdout.splitlines()


async def test_a_leaf_orthogonal_to_every_centroid_is_counted_unassigned(corpus: Path) -> None:
    # Arrange
    store, _ = await _built(corpus)
    _write(corpus, "n4", "u1")

    # Act
    result = await _index(store, corpus)

    # Assert — its source is still covered: the join considered it and placed it nowhere.
    assert result.layers_joined == (LayerJoin(layer=LAYER, joined=1, unassigned=1),)
    assert _layer_statuses(store) == [LayerStatus.ACTIVE] * 8
    assert result.layers_stale == ()


@pytest.mark.parametrize(
    ("added", "deleted", "handed", "calls"),
    [
        pytest.param(("n4", "n5"), (), ("adrap", 2), 1, id="stale-by-addition-joins"),
        pytest.param((), ("n3",), ("raptor", 5), 2, id="stale-by-deletion-rebuilds"),
        pytest.param(("n4", "n5"), ("n3",), ("raptor", 7), 2, id="deletion-wins-over-addition"),
    ],
)
async def test_a_join_pays_for_the_clusters_it_touches_and_a_deletion_for_every_cluster(
    corpus: Path,
    added: tuple[str, ...],
    deleted: tuple[str, ...],
    handed: tuple[str, int],
    calls: int,
) -> None:
    # Arrange
    store, _ = await _built(corpus)
    for name in deleted:
        await _delete(store, corpus, name)
    _write(corpus, *added)

    # Act
    result = await _index(store, corpus)

    # Assert
    assert [(stage, count) for stage, count, _ in _Handed.calls] == [handed]
    assert len(ScriptedModel.calls) == calls
    assert len(_fresh(store).summaries_seen()) == 2
    assert result.layers_failed == ()
    assert set(_layer_statuses(store)) == {LayerStatus.ACTIVE}


async def test_a_join_above_max_leaves_still_runs(corpus: Path, tmp_path: Path) -> None:
    # Arrange — six leaves built the tree at the bound; eight would be refused a full rebuild.
    _write_layer(tmp_path, max_leaves=6)
    store, _ = await _built(corpus)
    _write(corpus, "n4", "n5")

    # Act
    result = await _index(store, corpus)

    # Assert
    assert result.layers_failed == ()
    assert result.layers_joined == (LayerJoin(layer=LAYER, joined=2, unassigned=0),)


def test_enrich_with_raptor_declares_adrap_as_its_incremental_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')
    monkeypatch.chdir(tmp_path)
    deps = registry_bootstrap.build_dependencies(config_path=config)

    # Act
    composed = compose_layer(
        "enrich-with-raptor", base="index-text", registry=deps.registry, reports=deps.reports
    )

    # Assert — a build, per source or over the corpus, never runs the join stage.
    assert [spec.name for spec in composed.layer_specs] == ["raptor"]
    assert [spec.name for spec in composed.incremental_specs] == ["adrap"]
