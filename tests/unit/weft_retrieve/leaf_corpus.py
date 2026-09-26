"""A two-source corpus and a store that reads it back by filter, for `whole-corpus` (43.49).

`LeafStore` is `MemoryStore` with `MetadataFilter.matching` added: the filter is evaluated by
`tests.unit.weft_cli.leaf_selection.selects`, which refuses any operator the leaf filter does not
use, and the selection is served `PAGE` nodes at a time in the order the nodes were added, which
`Corpus.stored_order` scrambles. The contract promises pages and no order, so a reader that stops
at the first page, or trusts the store's order, is caught.

Every leaf's content is `words` words long and opens with a marker naming its source and ordinal,
so a count and a position in a rendered prompt can both be checked by hand.
"""

from dataclasses import dataclass

from tests.unit.weft_cli.leaf_selection import DeclaredNotALeaf, ensure_registered, selects
from weft_chunk.payload import ChunkPosition
from weft_index.payload import Representation
from weft_kernel.payload import MediaType, Node, SourceId
from weft_store.contract import Cursor, Filter, Page
from weft_store.memory import MemoryStore

PAGE = 3
POLONIUM = SourceId("file:///corpus/a-polonium.md")
RADIUM = SourceId("file:///corpus/b-radium.md")


class LeafStore(MemoryStore):
    """`MemoryStore` plus `matching`, paged by `PAGE`, in the order nodes were added."""

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        held = (await self.scan()).items
        selected = [node for node in held if selects(node, filter)]
        start = int(cursor) if cursor is not None else 0
        end = start + PAGE
        return Page(
            items=tuple(selected[start:end]),
            next_cursor=Cursor(str(end)) if end < len(selected) else None,
        )


@dataclass(frozen=True)
class Corpus:
    """`leaves` in source-then-ordinal order; `excluded` derived nodes no leaf read may return."""

    leaves: tuple[Node, ...]
    excluded: tuple[Node, ...]

    def stored_order(self) -> tuple[Node, ...]:
        nodes = (*self.leaves, *self.excluded)
        return (*reversed(nodes[::2]), *nodes[1::2])


def leaf_content(marker: str, words: int) -> str:
    return " ".join((f"[{marker}]", *(["element"] * (words - 1))))


def _document(source: SourceId, tag: str, chunks: int, words: int) -> tuple[Node, ...]:
    parent = Node.synthetic(
        content=f"the whole of {source}",
        media_type=MediaType.TEXT,
        reason="43.49 fixture document",
        sources=frozenset({source}),
    )
    return tuple(
        parent.derive(content=leaf_content(f"{tag}#{ordinal}", words), ordinal=ordinal).with_ext(
            ChunkPosition(ordinal=ordinal, start=ordinal * 100)
        )
        for ordinal in range(chunks)
    )


def corpus(words: int = 4) -> Corpus:
    """Fifteen leaves over two sources, one of them unpositioned, and two derived nodes.

    `b-radium` holds eleven chunks, so ordinal 10 sorts after 2 only when ordinals are compared
    as numbers. The unpositioned leaf of `a-polonium` belongs after that source's positioned ones.
    """
    ensure_registered(DeclaredNotALeaf)
    polonium = _document(POLONIUM, "a", 3, words)
    radium = _document(RADIUM, "b", 11, words)
    unpositioned = Node.synthetic(
        content=leaf_content("a#unpositioned", words),
        media_type=MediaType.TEXT,
        reason="43.49 fixture leaf with no recorded position",
        sources=frozenset({POLONIUM}),
    )
    summary = (
        radium[3]
        .derive(content="a summary of radium", ordinal=0)
        .with_ext(Representation(technique="raptor"))
    )
    declared = (
        polonium[1]
        .derive(content="a stranger's derived node", ordinal=1)
        .with_ext(DeclaredNotALeaf(note="derived"))
    )
    return Corpus(leaves=(*polonium, unpositioned, *radium), excluded=(summary, declared))


async def stored(fixture: Corpus) -> LeafStore:
    store = LeafStore()
    await store.add(fixture.stored_order())
    return store
