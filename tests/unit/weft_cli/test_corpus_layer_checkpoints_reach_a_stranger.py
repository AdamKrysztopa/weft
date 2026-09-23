"""Ledger task **43.20** — the resume path is a published service, not `raptor`'s private one.

A corpus-scoped build hands its layer stages `weft_index.contract.LayerCheckpoints`: `recall` a
node kept under a key in the open generation, `keep` one there as it completes. `weft_cli` names
no plugin to offer it, so a third party's own corpus layer resumes exactly as `raptor` does.
The stranger here derives one gloss per leaf and pays for each gloss it has to write.
"""

import asyncio
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
from weft_cli.ingest import IndexResult, run_index
from weft_index import Expander
from weft_index.contract import LayerCheckpoints
from weft_index.payload import Representation
from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, Vector
from weft_kernel.registry import Registry
from weft_store.contract import GenerationStatus

_LAYER = "enrich-with-glosses"
_LEAVES = 6


class _StrangerGloss:
    """A third party's corpus-layer `Expander`: one gloss per leaf, each kept as it is written."""

    paid: ClassVar[list[NodeId]] = []
    trip: ClassVar[int | None] = None
    victim: ClassVar[asyncio.Task[IndexResult] | None] = None

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        checkpoints = ctx.require(LayerCheckpoints)
        glosses: list[Node] = []
        for leaf in sorted(payload, key=lambda node: node.id):
            key = f"stranger-gloss:{leaf.id}"
            gloss = await checkpoints.recall(key)
            if gloss is None:
                _StrangerGloss.paid.append(leaf.id)
                if len(_StrangerGloss.paid) == _StrangerGloss.trip:
                    assert _StrangerGloss.victim is not None
                    _StrangerGloss.victim.cancel()
                    await asyncio.Event().wait()
                gloss = (
                    leaf.derive(content=f"a gloss on: {leaf.content}")
                    .with_ext(Representation(technique="stranger-gloss"))
                    .with_embedding(Vector(values=tuple(0.25 for _ in range(64))))
                )
                await checkpoints.keep(key, gloss)
            glosses.append(gloss)
        return Produced(value=(*payload, *glosses))


def _register_stranger(registry: Registry) -> None:
    registry.add(Expander, "stranger-gloss", _StrangerGloss, distribution="weft-example-stranger")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / f"{_LAYER}.yaml").write_text(
        f"name: {_LAYER}\n"
        "vars:\n  layer.scope: corpus\n"
        "stages:\n  - {id: gloss, use: stranger-gloss}\n"
    )
    monkeypatch.chdir(tmp_path)
    _StrangerGloss.paid = []
    _StrangerGloss.trip = None
    _StrangerGloss.victim = None
    return write_corpus(tmp_path, documents=_LEAVES)


async def _index(store: GenerationStore, corpus: Path) -> IndexResult:
    return await run_index(
        corpus,
        registry=registry_for(store, extra=_register_stranger),
        ctx=make_ctx(),
        layers=(_LAYER,),
    )


def _glosses(store: GenerationStore) -> list[Node]:
    shown = {
        g.id for g in store.state.generations.values() if g.status is GenerationStatus.PUBLISHED
    }
    return [
        node
        for node in store.state.nodes.values()
        if (marker := node.ext_as(Representation)) is not None
        and marker.technique == "stranger-gloss"
        and store.state.members.get(node.id, {""}) & (shown | {""})
    ]


async def test_a_third_party_corpus_layer_resumes_through_the_checkpoints_it_was_handed(
    corpus: Path,
) -> None:
    # Arrange — interrupted while writing the fourth of six glosses.
    store = GenerationStore()
    _StrangerGloss.trip = 4
    task = asyncio.create_task(_index(store, corpus))
    _StrangerGloss.victim = task
    with pytest.raises(asyncio.CancelledError):
        await task
    first_run = list(_StrangerGloss.paid[:3])
    _StrangerGloss.paid = []
    _StrangerGloss.trip = None

    # Act
    await _index(store, corpus)

    # Assert — the three it kept are recalled, not paid for again.
    assert len(_StrangerGloss.paid) == _LEAVES - 3
    assert not set(first_run) & set(_StrangerGloss.paid)
    assert len(_glosses(store)) == _LEAVES
    assert [(g.layer, g.status) for g in store.state.generations.values()] == [
        (_LAYER, GenerationStatus.PUBLISHED)
    ]
