"""`WordChunker` — a stranger's chunker: one child node per whitespace-separated word.

Deliberately not `weft_chunk.fixed_size.FixedSizeChunker` with different
numbers — a third party has no reason to reimplement the built-in, so this
one picks a genuinely different strategy to make the point that any
implementation satisfying `weft_chunk.contract.Chunker` structurally is
usable, not only the shape the built-in happens to take. Every child is
built through `Node.derive`, so lineage is carried automatically — the same
guarantee `docs/02-extension-model.md` gives every chunker, first-party or
not.

`destroys: tuple[type[Property], ...] = ()` is not decoration. `Chunker`
publishes a property vocabulary (`docs/02-extension-model.md` §3 →
*Ordering constraints*), so `weft_kernel.registry` refuses to register any
`Chunker` implementation — a stranger's own no less than a built-in — that
never states `destroys` at all. This one states the truth: splitting
strictly on whitespace never breaks a word the way a fixed-size window can,
so the tuple is empty rather than borrowed from `FixedSizeChunker`.
"""

from collections.abc import Sequence

from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Property


class WordChunker:
    """Splits each node's content on whitespace into one child node per word.

    Satisfies `weft_chunk.contract.Chunker` structurally — this class never
    imports it, the same path `docs/02-extension-model.md` describes for a
    third-party plugin. A node with no words contributes no children; a
    batch that contributes none at all answers `NothingToProduce`, never an
    empty `Produced([])`, the same convention `FixedSizeChunker` follows.
    """

    destroys: tuple[type[Property], ...] = ()

    def __init__(self, config: object = None) -> None:
        # No `with:` configuration this chunker takes — the runner's factory
        # call always passes a `spec.config` (`None` when a `StageSpec`
        # names none), so the parameter exists to accept that, not to be
        # used.
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        words: list[Node] = []
        for node in payload:
            words.extend(_words(node))
        if not words:
            return NothingToProduce(reason="no node had any word to carry")
        return Produced(value=words)


def _words(node: Node) -> list[Node]:
    """Every whitespace-separated word of `node.content`, each a child of `node`."""
    return [
        node.derive(content=word, ordinal=ordinal)
        for ordinal, word in enumerate(node.content.split())
    ]
