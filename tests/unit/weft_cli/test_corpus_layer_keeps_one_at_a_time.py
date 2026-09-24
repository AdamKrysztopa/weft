"""Carried repair **R43.40** — a corpus build's checkpoints never overlap two calls on one store.

`02` §1: a `Lifetime.RUN` plugin carries "no thread-safety obligation on the author", which is why
`01` keeps one batch in flight per run. `LayerCheckpoints.keep` runs the layer's store stage on one
bound handle, and `raptor` gathers its summaries, so every `keep` and `recall` of one build arrived
on that handle at once — on pgvector, two `add` transactions on one connection. The service a stage
gathers over is what owes the serialisation, for `raptor` and for a stranger's layer alike.

The store is `corpus_build_doubles.GenerationStore`, yielding inside every call and refusing a
second call while one is in flight on the same handle, as a connection-holding store does.
"""

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    CLUSTERS,
    LAYER,
    LEAVES,
    GenerationStore,
    ScriptedModel,
    State,
    llm_section,
    make_ctx,
    published,
    registry_for,
    visible_summaries,
    write_corpus,
)
from weft_cli import commands, render
from weft_cli.exit_codes import ExitCode
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_index import Expander
from weft_index.contract import LayerCheckpoints
from weft_index.payload import Representation
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Node, Outcome, Produced, Vector
from weft_kernel.registry import Registry
from weft_store.contract import Cursor, Filter, GenerationId, Page

_STRANGER_LAYER = "enrich-with-glosses"


class _InterleavedCallError(Exception):
    """What a store holding one connection does when a second call arrives mid-call."""


class _OneCallAtATimeStore(GenerationStore):
    """Makes concurrent use of one store handle an observable failure instead of a silent race.

    A `Lifetime.RUN` store with no thread-safety of its own: a call entered while another is
    in flight on the same handle is recorded and refused.
    """

    interleaved: ClassVar[list[str]] = []

    def __init__(self, state: State | None = None, generation: GenerationId | None = None) -> None:
        super().__init__(state, generation)
        self._in_flight: str | None = None

    async def _enter(self, call: str) -> None:
        if self._in_flight is not None:
            _OneCallAtATimeStore.interleaved.append(f"{call} during {self._in_flight}")
            raise _InterleavedCallError(f"{call} arrived while {self._in_flight} was in flight")
        self._in_flight = call
        await asyncio.sleep(0)

    async def add(self, nodes: Sequence[Node]) -> None:
        await self._enter("add")
        try:
            await super().add(nodes)
        finally:
            self._in_flight = None

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        await self._enter("matching")
        try:
            return await super().matching(filter, cursor)
        finally:
            self._in_flight = None


class _ConcurrentGloss:
    """A third party's corpus-layer `Expander` that recalls and keeps every leaf's gloss at once."""

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        checkpoints = ctx.require(LayerCheckpoints)

        async def _gloss(leaf: Node) -> Node:
            key = f"concurrent-gloss:{leaf.id}"
            kept = await checkpoints.recall(key)
            if kept is not None:
                return kept
            gloss = (
                leaf.derive(content=f"a gloss on: {leaf.content}")
                .with_ext(Representation(technique="concurrent-gloss"))
                .with_embedding(Vector(values=tuple(0.25 for _ in range(64))))
            )
            await checkpoints.keep(key, gloss)
            return gloss

        glosses = await asyncio.gather(*(_gloss(leaf) for leaf in payload))
        return Produced(value=(*payload, *glosses))


def _register_stranger(registry: Registry) -> None:
    registry.add(Expander, "concurrent-gloss", _ConcurrentGloss, distribution="weft-example")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / f"{LAYER}.yaml").write_text(
        f"name: {LAYER}\n"
        "vars:\n  layer.scope: corpus\n"
        "stages:\n"
        "  - id: raptor\n"
        "    use: raptor\n"
        "    with:\n"
        "      cluster_size: 2\n"
        "      similarity_threshold: -1.0\n"
    )
    (tmp_path / "pipelines" / f"{_STRANGER_LAYER}.yaml").write_text(
        f"name: {_STRANGER_LAYER}\n"
        "vars:\n  layer.scope: corpus\n"
        "stages:\n  - {id: gloss, use: concurrent-gloss}\n"
    )
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    _OneCallAtATimeStore.interleaved = []
    return write_corpus(tmp_path)


async def _index_command(store: GenerationStore, corpus: Path, *, layers: str) -> render.Rendered:
    deps = Dependencies(
        registry=registry_for(store, extra=_register_stranger),
        reports=tuple(
            PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
            for p in ("extract", "chunk", "embed", "store", "index", "llm")
        ),
        services=ServiceSelection(store="pgvector"),
        llm=llm_section("m1"),
    )
    ctx = make_ctx()
    ctx.services.add(Dependencies, deps)
    outcome = await commands.IndexCommand().run(
        commands.IndexArgs.model_validate({"path": str(corpus), "layers": layers}), ctx
    )
    return render.render_outcome(outcome)


def _glosses(store: GenerationStore) -> list[Node]:
    shown = {g.id for g in store.state.generations.values() if g.layer == _STRANGER_LAYER}
    return [
        node
        for node in store.state.nodes.values()
        if (marker := node.ext_as(Representation)) is not None
        and marker.technique == "concurrent-gloss"
        and store.state.members.get(node.id, set()) & shown
    ]


async def test_raptor_keeping_every_summary_at_once_publishes_through_a_one_call_store(
    corpus: Path,
) -> None:
    # Arrange
    store = _OneCallAtATimeStore()

    # Act
    rendered = await _index_command(store, corpus, layers=LAYER)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert _OneCallAtATimeStore.interleaved == []
    assert len(published(store)) == 1
    assert len(visible_summaries(store)) == CLUSTERS


async def test_a_stranger_layer_recalling_and_keeping_at_once_is_served_one_call_at_a_time(
    corpus: Path,
) -> None:
    # Arrange
    store = _OneCallAtATimeStore()

    # Act
    rendered = await _index_command(store, corpus, layers=_STRANGER_LAYER)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS, rendered.stderr
    assert _OneCallAtATimeStore.interleaved == []
    assert len(_glosses(store)) == LEAVES
