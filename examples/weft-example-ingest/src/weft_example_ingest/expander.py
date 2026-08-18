"""`ExampleFirstSentenceExpander` — a stranger's `Expander`: a node's first sentence as a gist.

Every node handed in continues, unchanged, into the output — `weft_index.contract.Expander`'s
own distinction from `Chunker` and `Enhancer` at the same input/output shape — and a gist is
*added* beside it, `parent.derive(...)`-built so its `Lineage` names the parent it stands in
for. Marked with `weft_index.payload.Representation`, the shared marker task 2.31's own
docstring says a summariser or a rephraser is meant to reuse rather than inventing its own.
A node whose first sentence *is* its whole content has nothing to gist and is left alone —
the same "degrade, never fail" posture the contract states for a representation that could
not be produced.
"""

import re
from collections.abc import Sequence

from weft_index.payload import Representation
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced

#: The name this expander is registered and selectable under — see `weft_example_ingest.register`.
NAME = "example-first-sentence"

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


class ExampleFirstSentenceExpander:
    """Derives one gist node per input node — its first sentence, when it has more than one.

    Satisfies `weft_index.contract.Expander` structurally — this class never imports it.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no node to expand")
        out: list[Node] = list(payload)
        for node in payload:
            gist = _gist(node)
            if gist is not None:
                out.append(gist)
        return Produced(value=out)


def _gist(node: Node) -> Node | None:
    """`node`'s first sentence as a derived, marked child — `None` when there is only one."""
    parts = _SENTENCE_BREAK.split(node.content.strip(), maxsplit=1)
    if len(parts) < 2:  # no sentence break found — nothing to gist  # noqa: PLR2004
        return None
    first, rest = parts
    first = first.strip()
    if not first or not rest.strip():
        return None
    return node.derive(content=first).with_ext(Representation(technique=NAME))
