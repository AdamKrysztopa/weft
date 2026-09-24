"""Carried repair **R43.36** — a join stage cannot write the published tree, and a stranger's join
is tested.

A corpus layer's join stage is offered `weft_index.contract.LayerRevision` and a `NodeStore` it may
only read: it returns the nodes it creates and reports what they replace through `replaced`, and
`Revisable`'s own docstring says a stage handed a `LayerRevision` "writes nothing". The stranger
here keeps one roster per layer, a summary over every leaf it placed; a leaf whose text says
`ASIDE` it places nowhere.
"""

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import ClassVar, cast

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    GenerationStore,
    make_ctx,
    registry_for,
    write_corpus,
)
from weft_cli import render
from weft_cli.commands import IndexCommandResult
from weft_cli.exit_codes import ExitCode
from weft_cli.ingest import IndexResult, run_index
from weft_cli.layers import LayerJoin, LayerJoinWritesStoreError
from weft_index import Expander, Revisable
from weft_index.contract import LayerRevision
from weft_index.payload import LayerMember, Representation
from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import MetadataFilter, NodeStore, NodeSupersedable
from weft_store.contract import (
    Filter,
    FilterOp,
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    LayerStatus,
)

_LAYER = "enrich-with-roster"
_FIRST = 4
_ASIDE = "ASIDE"
_ROSTER = "stranger-roster"
_MEMBER_FIELD = f"ext.{LayerMember.__namespace__}.layer"


class _Store(GenerationStore):
    """`GenerationStore` plus what a join needs, copied from `test_corpus_layer_joins_through_adrap.
    _JoinStore`: `carry_forward`, a reader that sees each layer's newest published generation
    only, and a `supersede` that deletes from whatever holds the node, as the shipped stores' does.
    """

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
        await self.add([new])
        self._state.nodes.pop(old, None)
        self._state.members.pop(old, None)


def _published_at(record: GenerationRecord) -> float:
    return record.published_at.timestamp() if record.published_at is not None else 0.0


def _roster(members: Sequence[Node]) -> Node:
    ordered = sorted(members, key=lambda node: node.id)
    return Node.combine(
        ordered, content=f"a roster of {len(ordered)} leaves", media_type=ordered[0].media_type
    ).with_ext(Representation(technique=_ROSTER))


def _satisfies(handed: object, contract: type[object]) -> bool:
    return isinstance(handed, contract)


class _StrangerRoster:
    """A third party's full build: every leaf it is handed, and one roster over all of them."""

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=(*payload, _roster(payload)))


class _StrangerRejoin:
    """A third party's join: reads the published roster through the store it is handed, and
    returns one over its members and every placed new leaf. `write`, when set, names the store
    write it attempts instead of reporting through `LayerRevision`.
    """

    write: ClassVar[str | None] = None
    capabilities: ClassVar[list[tuple[bool, bool]]] = []

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        store = ctx.require(NodeStore)
        revision = ctx.require(LayerRevision)
        _StrangerRejoin.capabilities.append(
            (_satisfies(store, NodeStore), _satisfies(store, MetadataFilter))
        )
        page = await cast(MetadataFilter, store).matching(
            Filter(op=FilterOp.EQ, field=_MEMBER_FIELD, value=revision.layer)
        )
        (old,) = page.items
        members = await store.get(old.lineage.parents)
        placed = [leaf for leaf in payload if _ASIDE not in leaf.content]
        rebuilt = _roster([*members, *placed])
        if _StrangerRejoin.write == "add":
            await store.add([payload[0].derive(content="a note the stranger keeps")])
        elif _StrangerRejoin.write == "supersede":
            await cast(NodeSupersedable, store).supersede(old.id, rebuilt)
        elif _StrangerRejoin.write == "delete_source":
            await store.delete_source(next(iter(members[0].lineage.sources)))
        else:
            await revision.replaced(old.id)
            await revision.unassigned(len(payload) - len(placed))
        return Produced(value=(*payload, rebuilt))


def _register_stranger(registry: Registry) -> None:
    registry.add(Expander, "stranger-roster", _StrangerRoster, distribution="weft-example-stranger")
    registry.add(
        Revisable, "stranger-rejoin", _StrangerRejoin, distribution="weft-example-stranger"
    )


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / f"{_LAYER}.yaml").write_text(
        f"name: {_LAYER}\n"
        "vars:\n  layer.scope: corpus\n  layer.incremental: join\n"
        "stages:\n"
        "  - {id: roster, use: stranger-roster}\n"
        "  - {id: join, use: stranger-rejoin}\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_Store, "published", 0)
    monkeypatch.setattr(_StrangerRejoin, "write", None)
    monkeypatch.setattr(_StrangerRejoin, "capabilities", [])
    return write_corpus(tmp_path, documents=_FIRST)


async def _index(store: _Store, corpus: Path) -> IndexResult:
    return await run_index(
        corpus,
        registry=registry_for(store, extra=_register_stranger),
        ctx=make_ctx(),
        layers=(_LAYER,),
    )


def _add_documents(corpus: Path) -> None:
    """Two leaves the join places, and one it places nowhere."""
    (corpus / "later0.txt").write_text("a later document that joins the roster.")
    (corpus / "later1.txt").write_text("another later document that joins the roster.")
    (corpus / "later2.txt").write_text(f"a later document the stranger sets {_ASIDE}.")


def _fresh(store: _Store) -> _Store:
    reader = _Store(store.state)
    reader.snapshot()
    return reader


async def _rosters_seen(store: _Store) -> dict[NodeId, Node]:
    page = await _fresh(store).matching(Filter(op=FilterOp.EQ, field=_MEMBER_FIELD, value=_LAYER))
    return {node.id: node for node in page.items}


def _later_sources(store: _Store) -> set[SourceId]:
    return {i for i, r in store.state.records.items() if "/later" in r.uri}


def _layer_failure_types(store: _Store) -> dict[SourceId, str | None]:
    return {
        source: entry.failure.error_type if entry.failure is not None else None
        for source, record in store.state.records.items()
        for entry in record.layers
        if entry.name == _LAYER and entry.status is LayerStatus.FAILED
    }


async def _built(corpus: Path) -> tuple[_Store, dict[NodeId, Node]]:
    store = _Store()
    await _index(store, corpus)
    before = await _rosters_seen(store)
    assert len(before) == 1, "the full build should publish one roster over the first leaves"
    _add_documents(corpus)
    return store, before


async def test_a_stranger_join_publishes_its_rebuilt_roster_and_is_reported_where_read(
    corpus: Path,
) -> None:
    # Arrange
    store, before = await _built(corpus)
    (old,) = before.values()

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

    # Assert — the replaced roster is left out of the published tree, the rebuilt one covers
    # every leaf but the one set aside, and the join is counted from what the stranger reported.
    after = await _rosters_seen(store)
    assert old.id not in after
    (rebuilt,) = after.values()
    assert len(rebuilt.lineage.parents) == _FIRST + 2
    assert set(old.lineage.parents) < set(rebuilt.lineage.parents)
    assert result.layers_joined == (LayerJoin(layer=_LAYER, joined=2, unassigned=1),)
    assert rendered.stdout is not None
    assert f"layer '{_LAYER}': joined 2 leaves, 1 unassigned" in rendered.stdout.splitlines()


async def test_the_store_a_join_is_handed_is_a_node_store_that_still_filters(
    corpus: Path,
) -> None:
    # Arrange
    store, _ = await _built(corpus)

    # Act
    await _index(store, corpus)

    # Assert
    assert _StrangerRejoin.capabilities == [(True, True)]


@pytest.mark.parametrize("write", ["add", "supersede", "delete_source"])
async def test_a_join_writing_through_its_store_is_refused_and_the_published_tree_stands(
    corpus: Path, write: str
) -> None:
    # Arrange
    store, before = await _built(corpus)
    published_before = {
        g.id for g in store.state.generations.values() if g.status is GenerationStatus.PUBLISHED
    }
    _StrangerRejoin.write = write

    # Act
    with pytest.raises(LayerJoinWritesStoreError) as refused:
        await _index(store, corpus)
    rendered = render.render_refusal(refused.value)

    # Assert — refused at the call, named where the operator reads it, and nothing published moved.
    assert rendered.exit_code == ExitCode.OPERATION_FAILED
    assert rendered.stderr is not None
    assert f"'{_LAYER}'" in rendered.stderr
    assert f"called {write}" in rendered.stderr
    assert "may only return the nodes it creates" in rendered.stderr
    assert "LayerRevision" in rendered.stderr
    assert refused.value.plugin == "stranger-rejoin"
    assert await _rosters_seen(store) == before
    assert {
        g.id for g in store.state.generations.values() if g.status is GenerationStatus.PUBLISHED
    } == published_before
    assert [
        g for g in store.state.generations.values() if g.status is GenerationStatus.BUILDING
    ] == []
    assert _layer_failure_types(store) == dict.fromkeys(
        _later_sources(store), "LayerJoinWritesStoreError"
    )
