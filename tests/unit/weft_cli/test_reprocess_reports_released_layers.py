"""Carried repair R43.28: no per-source layer disappears in a `--reprocess` run unreported.

Carried repair **R43.28** — `--reprocess` says which per-source layers it released and did not
rebuild.

No store removes single nodes, so re-indexing a source releases everything derived from it,
every per-source layer included. `weft index --reprocess --layers A` (and, after `R43.27`,
`--layers-only --reprocess --layers A` once A's identity moved) rebuilt A and left B's nodes
and record entries gone, reporting nothing. Now each such layer is carried on `IndexResult`
with how many sources it was released with, and `weft index` prints it with the command that
rebuilds it. A run naming every built layer, or a run without `--reprocess`, releases none.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    GenerationStore,
    llm_section,
    make_ctx,
    registry_for,
    write_corpus,
)
from weft_cli import commands, render
from weft_cli.ingest import IndexResult, run_index
from weft_cli.layers import LayerRelease
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_index import Expander
from weft_index.payload import Representation
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry

_A = "enrich-with-echo"
_B = "enrich-with-rephrase"
_SOURCES = 3


class _Echo:
    """A per-source `Expander`: every leaf back, plus one question derived from each."""

    technique: ClassVar[str] = "echo"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
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


def _with_echo(registry: Registry) -> None:
    registry.add(Expander, "echo", _Echo, distribution="weft-index")
    registry.add(Expander, "rephrase", _Rephrase, distribution="weft-index")


def _write_layer(project: Path, name: str, *, use: str) -> None:
    (project / "pipelines").mkdir(exist_ok=True)
    (project / "pipelines" / f"{name}.yaml").write_text(
        f"name: {name}\nstages:\n  - {{id: ask, use: {use}}}\n"
    )


def _released_line(layer: str, sources: int) -> str:
    return (
        f"layer '{layer}' was released with {sources} source(s) and not rebuilt — "
        f"weft index --layers {layer} rebuilds it"
    )


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _write_layer(tmp_path, _A, use="echo")
    _write_layer(tmp_path, _B, use="rephrase")
    monkeypatch.chdir(tmp_path)
    return write_corpus(tmp_path, documents=_SOURCES)


async def _index(
    store: GenerationStore,
    corpus: Path,
    *,
    layers: tuple[str, ...],
    layers_only: bool = False,
    reprocess: bool = False,
) -> IndexResult:
    return await run_index(
        corpus,
        registry=registry_for(store, extra=_with_echo),
        ctx=make_ctx(),
        llm=llm_section("m1"),
        layers=layers,
        layers_only=layers_only,
        reprocess=reprocess,
    )


async def _index_command(store: GenerationStore, corpus: Path, **flags: object) -> render.Rendered:
    deps = Dependencies(
        registry=registry_for(store, extra=_with_echo),
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index")
        ),
        services=ServiceSelection(store="pgvector"),
    )
    ctx = make_ctx()
    ctx.services.add(Dependencies, deps)
    outcome = await commands.IndexCommand().run(
        commands.IndexArgs.model_validate({"path": str(corpus), **flags}), ctx
    )
    return render.render_outcome(outcome)


def _carrying(store: GenerationStore, layer: str) -> int:
    return sum(
        1
        for record in store.state.records.values()
        if any(entry.name == layer for entry in record.layers)
    )


async def test_reprocess_naming_one_layer_reports_the_other_as_released(corpus: Path) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layers=(_A, _B))

    # Act
    result = await _index(store, corpus, layers=(_A,), reprocess=True)

    # Assert
    assert _carrying(store, _B) == 0
    assert result.layers_released == (LayerRelease(layer=_B, sources=_SOURCES),)


async def test_layers_only_reprocess_after_a_layer_moved_reports_the_other_as_released(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layers=(_A, _B))
    _write_layer(tmp_path, _A, use="rephrase")

    # Act
    result = await _index(store, corpus, layers=(_A,), layers_only=True, reprocess=True)

    # Assert
    assert _carrying(store, _B) == 0
    assert result.layers_released == (LayerRelease(layer=_B, sources=_SOURCES),)


async def test_the_release_counts_only_the_sources_that_carried_the_layer(
    corpus: Path,
) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layers=(_A, _B))
    (corpus / "late.txt").write_text("a document that arrived after the second layer ran.")
    await _index(store, corpus, layers=(_A,))

    # Act
    result = await _index(store, corpus, layers=(_A,), reprocess=True)

    # Assert
    assert result.layers_released == (LayerRelease(layer=_B, sources=_SOURCES),)


async def test_weft_index_prints_the_released_layer_and_how_to_rebuild_it(corpus: Path) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layers=(_A, _B))

    # Act
    rendered = await _index_command(store, corpus, layers=_A, reprocess=True)

    # Assert
    assert rendered.stdout is not None
    assert _released_line(_B, _SOURCES) in rendered.stdout


async def test_reprocess_naming_every_built_layer_releases_none(corpus: Path) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layers=(_A, _B))

    # Act
    result = await _index(store, corpus, layers=(_A, _B), reprocess=True)
    rendered = await _index_command(store, corpus, layers=f"{_A},{_B}", reprocess=True)

    # Assert
    assert result.layers_released == ()
    assert rendered.stdout is not None
    assert "was released" not in rendered.stdout


async def test_a_run_without_reprocess_releases_none(corpus: Path) -> None:
    # Arrange
    store = GenerationStore()
    await _index(store, corpus, layers=(_A, _B))

    # Act
    result = await _index(store, corpus, layers=(_A,))
    rendered = await _index_command(store, corpus, layers=_A)

    # Assert
    assert _carrying(store, _B) == _SOURCES
    assert result.layers_released == ()
    assert rendered.stdout is not None
    assert "was released" not in rendered.stdout
