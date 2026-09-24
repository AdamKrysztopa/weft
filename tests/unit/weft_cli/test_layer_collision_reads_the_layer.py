"""Carried repair **R43.34** — a layer collision is decided by the layer that wrote the node.

`_layer_collision` compared the techniques two nodes carried in `Representation`. A graph layer's
fact and mention nodes, and a stranger's derived node, carry none, so both sides read `"?"` and
a second layer overwrote the first's node unrefused; two layers running one `Expander` carry the
same technique and passed the same way. Since R43.23 every node a layer creates is stored
carrying `LayerMember(layer=<name>)`, and that is what the check now compares.

Each collision here is two layers running the same plugin over the same leaves, so the stored
node and the new one differ in nothing but the layer. The doubles are `corpus_build_doubles`'s
store and helpers, and `test_reprocess_reports_released_layers`'s `Dependencies` for the command.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    GenerationStore,
    make_ctx,
    registry_for,
    write_corpus,
)
from weft_cli import cli
from weft_cli.commands import IndexCommand
from weft_cli.exit_codes import ExitCode
from weft_cli.ingest import IndexResult, run_index
from weft_cli.layers import LayerNodeCollisionError
from weft_command.contract import Command
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_index import Expander
from weft_index.payload import LayerMember, Representation
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import (
    ExtModel,
    MediaType,
    Node,
    NodeId,
    NothingToProduce,
    Outcome,
    Produced,
)
from weft_kernel.registry import Registry
from weft_kg.payload import MentionedEntity
from weft_store.contract import LayerStatus
from weft_store.rehydrate import ext_models, register_ext_model

_FIRST = "enrich-with-first"
_SECOND = "enrich-with-second"
_BASE = "index-with-derive"
_SOURCES = 3


class _StrangerNote(ExtModel):
    __namespace__ = "test-r4334-note"
    __schema_version__ = "1"
    not_a_leaf: ClassVar[bool] = True
    note: str


def _ensure_registered(*models: type[ExtModel]) -> None:
    held = ext_models.names_for(ExtModel)
    for model in models:
        if model.__namespace__ not in held:
            register_ext_model(model)


class _Derive:
    """A per-source `Expander` returning every leaf plus one node derived from each.

    A per-source `Expander`: every leaf back, plus one node derived from each, marked by
    `_mark` — which is the dimension these tests vary.
    """

    def __init__(self, config: object = None) -> None:
        del config

    @staticmethod
    def _mark(node: Node) -> Node:
        return node.with_ext(_StrangerNote(note="derived"))

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no leaves")
        derived = tuple(
            self._mark(
                node.derive(content=f"about {node.content[:12]!r}", media_type=MediaType.TEXT)
            )
            for node in payload
        )
        return Produced(value=(*payload, *derived))


class _DeriveMention(_Derive):
    @staticmethod
    def _mark(node: Node) -> Node:
        return node.with_ext(MentionedEntity(name="Marie Curie", entity_type="Person"))


class _DeriveQuestion(_Derive):
    @staticmethod
    def _mark(node: Node) -> Node:
        return node.with_ext(Representation(technique="echo-question"))


class _DeriveOtherQuestion(_Derive):
    @staticmethod
    def _mark(node: Node) -> Node:
        return node.with_ext(Representation(technique="other-question"))


class _Digest:
    """A corpus-scope `Expander`: every leaf back, plus one node combining all of them."""

    def __init__(self, config: object = None) -> None:
        del config

    @staticmethod
    def _mark(node: Node) -> Node:
        return node.with_ext(_StrangerNote(note="digest"))

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no leaves")
        digest = Node.combine(payload, content="a digest of everything", media_type=MediaType.TEXT)
        return Produced(value=(*payload, self._mark(digest)))


class _DigestQuestion(_Digest):
    @staticmethod
    def _mark(node: Node) -> Node:
        return node.with_ext(Representation(technique="echo-digest"))


_PLUGINS: dict[str, type[_Derive] | type[_Digest]] = {
    "derive-note": _Derive,
    "derive-mention": _DeriveMention,
    "derive-question": _DeriveQuestion,
    "derive-other-question": _DeriveOtherQuestion,
    "digest-note": _Digest,
    "digest-question": _DigestQuestion,
}


def _with_plugins(registry: Registry) -> None:
    for name, plugin in _PLUGINS.items():
        registry.add(Expander, name, plugin, distribution="weft-index")


def _write_layer(project: Path, name: str, *, use: str, corpus_scope: bool = False) -> None:
    (project / "pipelines").mkdir(exist_ok=True)
    scope = "vars:\n  layer.scope: corpus\n" if corpus_scope else ""
    (project / "pipelines" / f"{name}.yaml").write_text(
        f"name: {name}\n{scope}stages:\n  - {{id: derive, use: {use}}}\n"
    )


def _write_base(project: Path, *, use: str) -> None:
    """Write a base pipeline that derives before `embed`, as `index-with-questions` does.

    A base pipeline deriving before `embed`, as `index-with-questions` does: its derived
    nodes are stored carrying no `LayerMember`.
    """
    (project / "pipelines").mkdir(exist_ok=True)
    (project / "pipelines" / f"{_BASE}.yaml").write_text(
        f"name: {_BASE}\n"
        "stages:\n"
        "  - {id: extract, use: text}\n"
        "  - {id: chunk, use: fixed-size}\n"
        f"  - {{id: derive, use: {use}}}\n"
        "  - {id: embed, use: hash}\n"
        "  - {id: store, use: pgvector}\n"
    )


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _ensure_registered(_StrangerNote, MentionedEntity)
    monkeypatch.chdir(tmp_path)
    return write_corpus(tmp_path, documents=_SOURCES)


async def _index(
    store: GenerationStore,
    corpus: Path,
    *,
    layers: tuple[str, ...],
    pipeline: str | None = None,
) -> IndexResult:
    return await run_index(
        corpus,
        registry=registry_for(store, extra=_with_plugins),
        ctx=make_ctx(),
        pipeline=pipeline,
        layers=layers,
    )


def _unstamped_derived(store: GenerationStore) -> dict[NodeId, Node]:
    return {
        node.id: node
        for node in store.state.nodes.values()
        if node.ext_as(LayerMember) is None
        and (node.ext_as(Representation) is not None or node.ext_as(_StrangerNote) is not None)
    }


def _created_by(store: GenerationStore, layer: str) -> dict[NodeId, Node]:
    return {
        node.id: node
        for node in store.state.nodes.values()
        if (member := node.ext_as(LayerMember)) is not None and member.layer == layer
    }


def _left_indexing(store: GenerationStore, layer: str) -> None:
    """Put each source's `layer` entry back to `INDEXING`, with its nodes stored.

    Each source's `layer` entry put back to `INDEXING` with its nodes stored — the state an
    interrupt between the layer's tail and its `ACTIVE` flip leaves.
    """
    for source_id, record in store.state.records.items():
        store.state.records[source_id] = record.model_copy(
            update={
                "layers": tuple(
                    entry.model_copy(update={"status": LayerStatus.INDEXING})
                    if entry.name == layer
                    else entry
                    for entry in record.layers
                )
            }
        )


def _assert_names_both_layers(message: str) -> None:
    assert f"layer '{_SECOND}' derived node" in message
    assert f"which the '{_FIRST}' layer already wrote" in message


@pytest.mark.parametrize("use", ["derive-note", "derive-mention", "derive-question"])
async def test_a_second_per_source_layer_deriving_the_firsts_nodes_is_refused_naming_both(
    corpus: Path, tmp_path: Path, use: str
) -> None:
    """A second per-source layer deriving the first's nodes is refused, naming both.

    A stranger's note, a graph mention, and one technique shared by two layers: none tells
    the two layers apart through `Representation`.
    """
    # Arrange
    _write_layer(tmp_path, _FIRST, use=use)
    _write_layer(tmp_path, _SECOND, use=use)
    store = GenerationStore()
    await _index(store, corpus, layers=(_FIRST,))
    first = _created_by(store, _FIRST)

    # Act
    with pytest.raises(LayerNodeCollisionError) as refused:
        await _index(store, corpus, layers=(_SECOND,))

    # Assert
    assert len(first) == _SOURCES
    _assert_names_both_layers(str(refused.value))
    assert _created_by(store, _FIRST) == first
    assert _created_by(store, _SECOND) == {}


@pytest.mark.parametrize("use", ["digest-note", "digest-question"])
async def test_a_second_corpus_layer_deriving_the_firsts_node_is_refused_naming_both(
    corpus: Path, tmp_path: Path, use: str
) -> None:
    """The corpus scope's own caller of the check, `_write_corpus_created`."""
    # Arrange
    _write_layer(tmp_path, _FIRST, use=use, corpus_scope=True)
    _write_layer(tmp_path, _SECOND, use=use, corpus_scope=True)
    store = GenerationStore()
    await _index(store, corpus, layers=(_FIRST,))
    first = _created_by(store, _FIRST)

    # Act
    with pytest.raises(LayerNodeCollisionError) as refused:
        await _index(store, corpus, layers=(_SECOND,))

    # Assert
    assert len(first) == 1
    _assert_names_both_layers(str(refused.value))
    assert _created_by(store, _FIRST) == first
    assert _created_by(store, _SECOND) == {}


@pytest.mark.parametrize("use", ["derive-note", "derive-mention", "derive-question"])
async def test_a_layer_deriving_again_the_nodes_it_already_stored_is_not_a_collision(
    corpus: Path, tmp_path: Path, use: str
) -> None:
    """A layer deriving again the nodes it already stored is not a collision.

    An interrupted run's layer is run again over the same leaves: its own nodes are not
    another layer's.
    """
    # Arrange
    _write_layer(tmp_path, _FIRST, use=use)
    store = GenerationStore()
    await _index(store, corpus, layers=(_FIRST,))
    first = set(_created_by(store, _FIRST))
    _left_indexing(store, _FIRST)

    # Act
    result = await _index(store, corpus, layers=(_FIRST,))

    # Assert
    assert len(first) == _SOURCES
    assert result.layers_failed == ()
    assert set(_created_by(store, _FIRST)) == first
    statuses = {
        entry.status
        for record in store.state.records.values()
        for entry in record.layers
        if entry.name == _FIRST
    }
    assert statuses == {LayerStatus.ACTIVE}


async def test_an_unstamped_stored_node_under_another_technique_is_still_refused_naming_it(
    corpus: Path, tmp_path: Path
) -> None:
    """R43.34: an unstamped stored node under another technique is still refused, naming it.

    The owner's ruling on R43.34: a stored node with no `LayerMember` keeps the
    `Representation` comparison, and the message names its technique as before.
    """
    # Arrange
    _write_base(tmp_path, use="derive-question")
    _write_layer(tmp_path, _SECOND, use="derive-other-question")
    store = GenerationStore()
    await _index(store, corpus, layers=(), pipeline=_BASE)
    base = _unstamped_derived(store)

    # Act
    with pytest.raises(LayerNodeCollisionError) as refused:
        await _index(store, corpus, layers=(_SECOND,), pipeline=_BASE)

    # Assert
    assert len(base) == _SOURCES
    message = str(refused.value)
    assert f"layer '{_SECOND}' derived node" in message
    assert "which the 'echo-question' layer already wrote" in message
    assert _unstamped_derived(store) == base
    assert _created_by(store, _SECOND) == {}


@pytest.mark.parametrize("use", ["derive-question", "derive-note"])
async def test_an_unstamped_stored_node_under_the_same_technique_or_none_is_not_a_collision(
    corpus: Path, tmp_path: Path, use: str
) -> None:
    """R43.34: an unstamped node under the same technique, or none, is not a collision.

    The owner's ruling on R43.34, its other half: an unstamped node whose technique matches,
    or which carries no `Representation`, passes as it did before.
    """
    # Arrange
    _write_base(tmp_path, use=use)
    _write_layer(tmp_path, _SECOND, use=use)
    store = GenerationStore()
    await _index(store, corpus, layers=(), pipeline=_BASE)
    base = set(_unstamped_derived(store))

    # Act
    result = await _index(store, corpus, layers=(_SECOND,), pipeline=_BASE)

    # Assert
    assert len(base) == _SOURCES
    assert result.layers_failed == ()
    statuses = {
        entry.status
        for record in store.state.records.values()
        for entry in record.layers
        if entry.name == _SECOND
    }
    assert statuses == {LayerStatus.ACTIVE}


async def test_weft_index_prints_the_collision_naming_both_layers_and_exits_1(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    _write_layer(tmp_path, _FIRST, use="derive-note")
    _write_layer(tmp_path, _SECOND, use="derive-note")
    store = GenerationStore()
    await _index(store, corpus, layers=(_FIRST,))
    registry = registry_for(store, extra=_with_plugins)
    registry.add(Command, "index", IndexCommand, distribution="weft-rag")
    deps = Dependencies(
        registry=registry,
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index")
        ),
        services=ServiceSelection(store="pgvector"),
    )
    args = cli.build_parser(registry).parse_args(["index", str(corpus), "--layers", _SECOND])

    # Act
    rendered = await cli.run_command("index", args, deps)

    # Assert
    assert rendered.exit_code is ExitCode.OPERATION_FAILED
    _assert_names_both_layers(rendered.stderr or "")
