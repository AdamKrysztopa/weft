"""Carried repair **R43.23** — `adrap` joins new leaves only into the base pipeline's own tree.

`adrap` found "the tree" by asking the store for every node carrying `RaptorFacts.level`, and
superseded what it found with no further condition. A store that also holds an
`enrich-with-raptor` layer's tree answers that question with the layer's summaries too, so
`index-with-adrap` edited a layer's tree in place, and could join one document into another
document's per-source tree.

`weft_cli.layers` now stamps every node a layer creates with `LayerMember`, and `adrap`'s read
leaves out every summary carrying it. The fact varied below is that stamp alone, on two trees of
otherwise identical shape; the layer's tree is the one nearer the new leaves, so a read that
ignored the stamp would join them there.

The store double is `tests/unit/weft_index/test_adrap.py`'s `_RecordingStore`, except that
`matching` evaluates the filter it is handed, with the semantics
`examples/weft-example-ingest`'s in-memory store gives it — a double that answered "every
summary" regardless of the filter could not tell the two reads apart.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from weft_embed.contract import Embedder
from weft_index.adrap import AdrapJoiner
from weft_index.payload import LayerMember, RaptorFacts, Representation
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import NAME as RAPTOR_NAME
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_prompts.contract import Prompts
from weft_store import NodeStore
from weft_store.contract import Filter, FilterOp, Page
from weft_store.fields import FieldKind, FieldPath, field_for

_BASE_SOURCE = SourceId("doc-base")
_LAYER_SOURCE = SourceId("doc-layered")
_LAYER = "enrich-with-raptor"

_TREE_THRESHOLD = 0.75
_TREE_CLUSTER_SIZE = 8

# Base centroid (0.95, 0.05) and layer centroid (0.75, 0.65). Both new leaves clear the 0.75
# threshold against either — cosine 0.81 and 0.78 to the base, 0.999 to the layer.
_BASE_VECTORS = (Vector(values=(1.0, 0.0)), Vector(values=(0.9, 0.1)))
_LAYER_VECTORS = (Vector(values=(0.8, 0.6)), Vector(values=(0.7, 0.7)))
_NEW_VECTORS = (Vector(values=(0.78, 0.62)), Vector(values=(0.74, 0.66)))


def _leaf(content: str, vector: Vector, source: SourceId) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="test fixture",
        sources=frozenset({source}),
    ).with_embedding(vector)


def _summary(members: Sequence[Node], *, content: str) -> Node:
    """A level-1 summary of `members`, shaped exactly as `raptor` writes one."""
    return (
        Node.combine(members, content=content, media_type=MediaType.TEXT)
        .with_ext(Representation(technique=RAPTOR_NAME))
        .with_ext(
            RaptorFacts(
                members=len(members),
                members_truncated=0,
                characters_held=sum(len(member.content) for member in members),
                characters_shown=sum(len(member.content) for member in members),
                level=1,
                resolved_similarity_threshold=_TREE_THRESHOLD,
                resolved_cluster_size=_TREE_CLUSTER_SIZE,
            )
        )
    )


def _matches(node: Node, filter: Filter) -> bool:
    if filter.op is FilterOp.AND:
        return all(_matches(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.OR:
        return any(_matches(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.NOT:
        return not _matches(node, filter.clauses[0])
    path = field_for(filter.op, filter.field or "")
    value = _value_at(node, path)
    if filter.op is FilterOp.EXISTS:
        return value is not None
    raise AssertionError(f"adrap's read used an operator this double lacks: {filter}")


def _value_at(node: Node, path: FieldPath) -> object:
    if path.kind is FieldKind.EXTENSION:
        model = node.ext.get(path.namespace)
        for key in path.keys:
            if model is None:
                return None
            model = getattr(model, key, None)
        return model
    raise AssertionError(f"adrap's read named a core field this double lacks: {path}")


class _RecordingStore:
    """A `NodeStore` + `MetadataFilter` + `NodeSupersedable` holding nodes in a dict, with
    `supersede` implemented write-new-then-delete-old, as the contract orders it."""

    def __init__(self, nodes: Sequence[Node]) -> None:
        self.nodes: dict[NodeId, Node] = {node.id: node for node in nodes}
        self.superseded: list[tuple[NodeId, NodeId]] = []

    async def put(self, nodes: Sequence[Node]) -> None:
        for node in nodes:
            self.nodes[node.id] = node

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self.nodes[node_id] for node_id in ids if node_id in self.nodes)

    async def scan(self, cursor: object | None = None) -> Page[Node]:
        del cursor
        return Page(items=tuple(self.nodes.values()), next_cursor=None)

    async def count(self) -> int:
        return len(self.nodes)

    async def matching(self, filter: Filter, cursor: object | None = None) -> Page[Node]:
        del cursor
        return Page(
            items=tuple(node for node in self.nodes.values() if _matches(node, filter)),
            next_cursor=None,
        )

    async def supersede(self, old: NodeId, new: Node) -> None:
        self.nodes[new.id] = new
        if old != new.id:
            self.nodes.pop(old, None)
        self.superseded.append((old, new.id))


class _StubPrompts:
    def __init__(self) -> None:
        self._prompt = SummarizeClusterPrompt()

    async def render(self, name: str, values: BaseModel, ctx: Context) -> Outcome[Rendered]:
        if name != SUMMARIZE_CLUSTER_NAME:
            raise KeyError(name)
        return await self._prompt.render(values, ctx)


class _ScriptedLLM:
    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, role, ctx
        return Produced(value=Completion(text="A rebuilt summary.", model="stub-model"))


class _StubEmbedder:
    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=[node.with_embedding(Vector(values=(0.6, 0.8))) for node in payload])


def _ctx(store: _RecordingStore) -> Context:
    services = ServiceRegistry()
    services.add(NodeStore, store)
    services.add(Embedder, _StubEmbedder())
    services.add(LLM, _ScriptedLLM())
    services.add(Prompts, _StubPrompts())
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _base_tree() -> tuple[Node, Node, Node]:
    a = _leaf("base passage a", _BASE_VECTORS[0], _BASE_SOURCE)
    b = _leaf("base passage b", _BASE_VECTORS[1], _BASE_SOURCE)
    return a, b, _summary((a, b), content="A summary of the base passages.")


def _layer_tree() -> tuple[Node, Node, Node]:
    a = _leaf("layered passage a", _LAYER_VECTORS[0], _LAYER_SOURCE)
    b = _leaf("layered passage b", _LAYER_VECTORS[1], _LAYER_SOURCE)
    summary = _summary((a, b), content="A summary of the layered passages.")
    return a, b, summary.with_ext(LayerMember(layer=_LAYER))


def _new_leaves() -> tuple[Node, Node]:
    return (
        _leaf("new passage one", _NEW_VECTORS[0], SourceId("doc-new")),
        _leaf("new passage two", _NEW_VECTORS[1], SourceId("doc-new")),
    )


async def test_new_leaves_join_the_base_tree_and_never_touch_a_layers_nearer_tree() -> None:
    # Arrange
    base_a, base_b, base_summary = _base_tree()
    layer_a, layer_b, layer_summary = _layer_tree()
    store = _RecordingStore((base_a, base_b, base_summary, layer_a, layer_b, layer_summary))
    new_leaves = _new_leaves()

    # Act
    outcome = await AdrapJoiner().run(new_leaves, _ctx(store))

    # Assert
    assert isinstance(outcome, Produced)
    assert await store.get([base_summary.id]) == ()
    assert await store.get([layer_summary.id]) == (layer_summary,)
    ((old_id, new_id),) = store.superseded
    assert old_id == base_summary.id
    (rebuilt,) = await store.get([new_id])
    assert set(rebuilt.lineage.parents) == {base_a.id, base_b.id, *(n.id for n in new_leaves)}


async def test_a_store_holding_only_a_layers_tree_gives_adrap_nothing_to_join() -> None:
    # Arrange
    layer_a, layer_b, layer_summary = _layer_tree()
    store = _RecordingStore((layer_a, layer_b, layer_summary))
    new_leaves = _new_leaves()

    # Act
    outcome = await AdrapJoiner().run(new_leaves, _ctx(store))

    # Assert
    assert isinstance(outcome, Produced)
    assert tuple(outcome.value) == new_leaves
    assert store.superseded == []
    assert await store.get([layer_summary.id]) == (layer_summary,)
