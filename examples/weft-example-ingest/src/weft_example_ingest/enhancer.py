"""`ExampleWordCountEnhancer` — a stranger's `Enhancer`: attaches a word count, never rewrites text.

`weft_enhance.contract.Enhancer`'s own distinction from `Cleaner` at the same input/output
shape: a fact is *added* via `Node.with_ext`, `content` is untouched, and node identity
(`node.id`) does not move.
"""

from collections.abc import Sequence

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Node, NothingToProduce, Outcome, Produced


class WordCount(ExtModel):
    """This pack's own namespaced fact: how many whitespace-separated words `content` has."""

    __namespace__ = "weft-example-ingest"

    count: int


class ExampleWordCountEnhancer:
    """Attaches a `WordCount` to every node it is handed. Satisfies `weft_enhance.contract.
    Enhancer` structurally — this class never imports it.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no node to enhance")
        enhanced = [node.with_ext(WordCount(count=len(node.content.split()))) for node in payload]
        return Produced(value=enhanced)
