"""`ExampleBlankLineCollapser` — a stranger's `Cleaner`: three-or-more blank lines become one.

`destroys` is not decoration — `weft_clean.contract.Cleaner.publishes_property_vocabulary`
is `True`, so `weft_kernel.registry` refuses to register any `Cleaner` implementation that
never states it, a stranger's own no less than a built-in. Collapsing *runs of blank
lines* never touches a word or a sentence, so the empty tuple is the truthful answer, the
same posture `weft_example_chunker.word_chunker.WordChunker.destroys` documents for
splitting strictly on whitespace.
"""

import re
from collections.abc import Sequence

from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Property

_BLANK_RUN = re.compile(r"\n{3,}")


class ExampleBlankLineCollapser:
    """Collapses three-or-more consecutive newlines to exactly two. Satisfies
    `weft_clean.contract.Cleaner` structurally — this class never imports it.
    """

    destroys: tuple[type[Property], ...] = ()

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no node to clean")
        cleaned = [node.derive(content=_BLANK_RUN.sub("\n\n", node.content)) for node in payload]
        return Produced(value=cleaned)
