"""Resolving a citation past a derived representation, to the one node it stands in for.

`.phase2-findings.md` §11 (BINDING): "a hit on any of them resolves through lineage to the
one parent chunk and the one source document... which is what makes task 2.9's citations
able to follow back to a passage rather than to a paraphrase of one." `weft_generate`
depends on `weft-kernel`, `weft-store`, `weft-retrieve`, `weft-llm` and `weft-prompts` only
(`weft_generate.contract`'s own module docstring), and adding `weft-index` — or any future
pack that ships a summariser or a rephraser over the same mechanism — here would mean every
deployment that generates an answer, whether or not it ever expands a chunk into questions,
installs whatever generates them. `weft_generate.page.page_for` already sets this precedent
for a chunk's offset; this module sets it for a node's own citable identity.

So this module never imports `weft_index` or `Representation`. It asks a node's `ext`
values, structurally, for one shape — a `runtime_checkable` `Protocol` the project's own
rule prefers over `hasattr` — that `weft_index.payload.Representation` already satisfies
without either class changing, and any future pack's own derived-representation marker
satisfies it the same way, for free, the moment it carries a `technique: str` attribute.

**Only a single-parent node is resolved.** `.phase2-findings.md` §11's own mechanism,
`chunk.derive(...)`, always produces exactly one parent. A node `Node.combine` built from
several members (a cluster summary) has no single "the" parent to stand in for — citing
one of several sources it was built from would misattribute a claim the same way naming one
of a summary's several `Lineage.sources` already does (`_source_id`'s own docstring, in
`weft_generate.cited_answer`) — so a node with more than one parent is cited as itself, on
purpose, even when it happens to carry this marker.
"""

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from weft_kernel.payload import Node, NodeId
from weft_store.contract import NodeStore


@runtime_checkable
class _RepresentationMarker(Protocol):
    """Structurally, `weft_index.payload.Representation`: a derived node's own technique name."""

    technique: str


async def citable_nodes(nodes: Iterable[Node], *, store: NodeStore) -> dict[NodeId, Node]:
    """Every node in `nodes`, mapped to itself — or, for a single-parent representation, to
    the one parent it stands in for, fetched from `store` once per distinct parent.

    Mirrors `weft_generate.cited_answer._uris_for`'s own batching: one `store.get` call
    for every distinct id this citation actually needs, never one call per passage. A
    parent `store.get` could not find (deleted between retrieval and generation, in
    principle) leaves that one representation cited as itself rather than raising — the
    citation still resolves to *a* node, which is what `Citation.node_id`'s own contract
    promises; only the identity substitution is skipped.
    """
    by_id = {node.id: node for node in nodes}
    parents = {
        node.id: parent for node in by_id.values() if (parent := _parent_of(node)) is not None
    }
    fetched = (
        {found.id: found for found in await store.get(tuple(parents.values()))} if parents else {}
    )
    return {
        node_id: fetched.get(parents[node_id], node) if node_id in parents else node
        for node_id, node in by_id.items()
    }


def _parent_of(node: Node) -> NodeId | None:
    """`node`'s one parent, when it is a single-parent representation of it — `None` otherwise."""
    if len(node.lineage.parents) != 1:
        return None
    if not any(isinstance(value, _RepresentationMarker) for value in node.ext.values()):
        return None
    return node.lineage.parents[0]
