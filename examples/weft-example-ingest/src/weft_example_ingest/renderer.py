"""`ExamplePlainRenderer` — a stranger's `Renderer`: nodes joined into `text/plain`.

Honest about what plain text cannot carry, on `weft_extract.payload.Rendition`'s own rule
("a renderer returning a partial document with an empty `dropped` is a defect the reviewer
must catch"): an embedding is recorded as a dropped `Node`, and so is every namespaced
`ext` fact — plain text has no place to put either.
"""

from collections.abc import Sequence

from weft_extract.payload import DroppedContent, DroppedKind, Rendition
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced

_MEDIA_TYPE = "text/plain"


class ExamplePlainRenderer:
    """Joins every node's `content` with a blank line. Satisfies `weft_extract.contract.Renderer`
    structurally — this class never imports it.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Rendition]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no node to render")
        dropped = tuple(item for node in payload for item in _dropped_for(node))
        return Produced(
            value=Rendition(
                text="\n\n".join(node.content for node in payload),
                media_type=_MEDIA_TYPE,
                nodes_rendered=len(payload),
                dropped=dropped,
            )
        )


def _dropped_for(node: Node) -> tuple[DroppedContent, ...]:
    """Every fact `node` carries that `text/plain` cannot represent."""
    items: list[DroppedContent] = []
    if node.embedding is not None:
        items.append(
            DroppedContent(
                node_id=node.id, kind=DroppedKind.EMBEDDING, detail="plain text carries no vector"
            )
        )
    items.extend(
        DroppedContent(node_id=node.id, kind=DroppedKind.EXTENSION, detail=namespace)
        for namespace in node.ext
    )
    return tuple(items)
