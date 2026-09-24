"""Carried repair **R43.27** — `weft index --layers <name> --layers-only --reprocess` rebuilds a
layer whose identity moved, as the message reporting it says.

`R43.7` settled the owner's Q6: a moved layer is never rebuilt unasked, and `--reprocess` is how it
is asked. Under `--layers-only` that request never reached `run_layers`, so the command printed
"changed since it last ran and was not rebuilt — weft index --layers <name> --reprocess rebuilds
it" and rebuilt nothing: the remedy named was the command just run. Without `--layers-only` the
layer was rebuilt only after every document was re-embedded.

Both scopes: a corpus-scoped `raptor` tree (`cluster_size` 2 → 3, the measured case) and a
per-source expander swapped for another. A corpus layer rebuilds into a new generation and the base
does not run, so no leaf reaches the embedder. A per-source layer's earlier output can only be
released with its source, since no store removes single nodes, so the sources whose layer moved
are released and indexed again, as `--reprocess` alone does (owner's decision, 2026-09-24), and
only those. Without `reprocess` the moved layer is still reported and left alone.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    LAYER,
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
from weft_cli.ingest import IndexResult, run_index
from weft_embed.hash_embedder import HashEmbedder
from weft_index import Expander
from weft_index.payload import Representation
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry
from weft_store.contract import LayerStatus

_PER_SOURCE = "enrich-with-echo"


class _Echo:
    """A per-source `Expander`: every leaf back, plus one question derived from each."""

    technique: ClassVar[str] = "echo"
    calls: ClassVar[list[int]] = []

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        type(self).calls.append(len(payload))
        if not payload:
            return NothingToProduce(reason="no leaves")
        derived = tuple(
            node.derive(
                content=f"{self.technique}: {node.content[:12]!r}?", media_type=MediaType.TEXT
            ).with_ext(Representation(technique=self.technique))
            for node in payload
        )
        return Produced(value=(*payload, *derived))


class _Rephrase(_Echo):
    technique: ClassVar[str] = "rephrase"
    calls: ClassVar[list[int]] = []


def _with_echo(registry: Registry) -> None:
    registry.add(Expander, "echo", _Echo, distribution="weft-index")
    registry.add(Expander, "rephrase", _Rephrase, distribution="weft-index")


def _write_per_source_layer(project: Path, *, use: str) -> None:
    (project / "pipelines" / f"{_PER_SOURCE}.yaml").write_text(
        f"name: {_PER_SOURCE}\nstages:\n  - {{id: ask, use: {use}}}\n"
    )


def _move_cluster_size(project: Path) -> None:
    layer = project / "pipelines" / f"{LAYER}.yaml"
    layer.write_text(layer.read_text().replace("cluster_size: 2", "cluster_size: 3"))


def _is_leaf(node: Node) -> bool:
    return not any(namespace.startswith("weft-index") for namespace in node.ext)


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    write_layer(tmp_path)
    _write_per_source_layer(tmp_path, use="echo")
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    _Echo.calls = []
    _Rephrase.calls = []
    return write_corpus(tmp_path)


@pytest.fixture
def leaves_embedded(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """How many leaves each embedder call was handed, from the moment it is requested."""
    counted: list[int] = []
    original = HashEmbedder.run

    async def run(
        self: HashEmbedder, payload: Sequence[Node], ctx: Context
    ) -> Outcome[Sequence[Node]]:
        counted.append(sum(1 for node in payload if _is_leaf(node)))
        return await original(self, payload, ctx)

    monkeypatch.setattr(HashEmbedder, "run", run)
    return counted


async def _index(
    store: GenerationStore,
    corpus: Path,
    *,
    layer: str,
    layers_only: bool = False,
    reprocess: bool = False,
) -> IndexResult:
    return await run_index(
        corpus,
        registry=registry_for(store, extra=_with_echo),
        ctx=make_ctx(),
        llm=llm_section("m1"),
        layers=(layer,),
        layers_only=layers_only,
        reprocess=reprocess,
    )


def _identities(store: GenerationStore, layer: str) -> set[tuple[str, LayerStatus]]:
    return {
        (entry.pipeline_identity, entry.status)
        for record in store.state.records.values()
        for entry in record.layers
        if entry.name == layer
    }


def _techniques(store: GenerationStore) -> set[str]:
    return {
        marker.technique
        for node in store.state.nodes.values()
        if isinstance(marker := node.ext.get(Representation.__namespace__), Representation)
    }


async def test_layers_only_reprocess_rebuilds_a_corpus_layer_whose_config_moved(
    corpus: Path, tmp_path: Path, leaves_embedded: list[int]
) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layer=LAYER)
    ((before, _),) = _identities(store, LAYER)
    _move_cluster_size(tmp_path)
    ScriptedModel.calls = []
    ScriptedModel.label = "second"
    leaves_embedded.clear()

    # Act
    result = await _index(store, corpus, layer=LAYER, layers_only=True, reprocess=True)

    # Assert
    assert result.layers_changed == ()
    assert ScriptedModel.calls, "the moved layer's stage was never called"
    ((after, status),) = _identities(store, LAYER)
    assert (after != before, status) == (True, LayerStatus.ACTIVE)
    assert len(published(store)) == 1
    summaries = visible_summaries(store)
    assert summaries
    assert all("in the second run" in node.content for node in summaries)
    assert sum(leaves_embedded) == 0, "--layers-only re-embedded the leaves"


async def test_layers_only_reprocess_rebuilds_a_per_source_layer_whose_identity_moved(
    corpus: Path, tmp_path: Path, leaves_embedded: list[int]
) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layer=_PER_SOURCE)
    ((before, _),) = _identities(store, _PER_SOURCE)
    _write_per_source_layer(tmp_path, use="rephrase")
    first_build = sum(leaves_embedded)
    leaves_embedded.clear()

    # Act
    result = await _index(store, corpus, layer=_PER_SOURCE, layers_only=True, reprocess=True)

    # Assert — every source's layer moved, so every source is indexed again, once.
    assert result.layers_changed == ()
    assert sum(_Rephrase.calls) == len(store.state.records)
    ((after, status),) = _identities(store, _PER_SOURCE)
    assert (after != before, status) == (True, LayerStatus.ACTIVE)
    assert sum(leaves_embedded) == first_build


async def test_layers_only_reprocess_leaves_none_of_the_moved_layers_earlier_output(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layer=_PER_SOURCE)
    _write_per_source_layer(tmp_path, use="rephrase")

    # Act
    await _index(store, corpus, layer=_PER_SOURCE, layers_only=True, reprocess=True)

    # Assert
    assert _techniques(store) == {"rephrase"}


async def test_reprocess_without_layers_only_rebuilds_a_corpus_layer_whose_config_moved(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layer=LAYER)
    ((before, _),) = _identities(store, LAYER)
    _move_cluster_size(tmp_path)
    ScriptedModel.calls = []
    ScriptedModel.label = "second"

    # Act
    result = await _index(store, corpus, layer=LAYER, reprocess=True)

    # Assert
    assert result.layers_changed == ()
    assert ScriptedModel.calls
    ((after, status),) = _identities(store, LAYER)
    assert (after != before, status) == (True, LayerStatus.ACTIVE)
    assert len(published(store)) == 1
    summaries = visible_summaries(store)
    assert summaries
    assert all("in the second run" in node.content for node in summaries)


async def test_reprocess_without_layers_only_rebuilds_a_per_source_layer_whose_identity_moved(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layer=_PER_SOURCE)
    ((before, _),) = _identities(store, _PER_SOURCE)
    _write_per_source_layer(tmp_path, use="rephrase")

    # Act
    result = await _index(store, corpus, layer=_PER_SOURCE, reprocess=True)

    # Assert
    assert result.layers_changed == ()
    assert sum(_Rephrase.calls) == len(store.state.records)
    ((after, status),) = _identities(store, _PER_SOURCE)
    assert (after != before, status) == (True, LayerStatus.ACTIVE)
    assert _techniques(store) == {"rephrase"}


@pytest.mark.parametrize("scope", ["corpus", "per-source"])
async def test_layers_only_without_reprocess_still_reports_a_moved_layer_and_leaves_it(
    corpus: Path, tmp_path: Path, scope: str
) -> None:
    # Arrange
    store = GenerationStore()
    layer = LAYER if scope == "corpus" else _PER_SOURCE
    await _index(store, corpus, layer=layer)
    before = _identities(store, layer)
    if scope == "corpus":
        _move_cluster_size(tmp_path)
    else:
        _write_per_source_layer(tmp_path, use="rephrase")
    ScriptedModel.calls = []

    # Act
    result = await _index(store, corpus, layer=layer, layers_only=True)

    # Assert
    assert result.layers_changed == (layer,)
    assert (ScriptedModel.calls, _Rephrase.calls) == ([], [])
    assert _identities(store, layer) == before
