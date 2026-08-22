"""`GraphEntityEnhancer` — attaches `GraphData` to every node it is handed. Never rewrites
`content`, so node identity is unaffected — `weft_enhance.contract.Enhancer`'s own contrast
with `Cleaner`.

Satisfies `weft_enhance.contract.Enhancer` structurally — this class never imports it, the
same path `docs/02-extension-model.md` describes for a third-party plugin.
"""

from collections.abc import Sequence

from weft_example_graph.extraction import extract_graph_data
from weft_example_graph.payload import GraphData
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced


class GraphEntityEnhancer:
    """Crude, deterministic entity/relation extraction as an ordinary `Enhancer` stage.

    Every node in a non-empty batch gets a `GraphData`, even an empty one (no entities
    found) — the same convention `weft_example_ingest.enhancer.ExampleWordCountEnhancer`
    follows: an empty *result* per node is a real, attachable fact, and only an empty
    *batch* answers `NothingToProduce`.
    """

    def __init__(self, config: object = None) -> None:
        # No `with:` configuration this enhancer takes — the runner's factory call always
        # passes a `spec.config` (`None` when a `StageSpec` names none), so the parameter
        # exists to accept that, not to be used.
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no node to extract graph data from")
        enhanced: list[Node] = []
        for node in payload:
            entities, relations = extract_graph_data(node.content)
            enhanced.append(node.with_ext(GraphData(entities=entities, relations=relations)))
        return Produced(value=enhanced)


__all__ = ["GraphEntityEnhancer"]
