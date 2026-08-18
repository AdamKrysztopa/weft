"""`run_ask` — `weft ask <question>` retrieves and prints matching passages. It does not generate.

`docs/06-phase-0-build.md`'s fourth, smaller trap: "`03` defines `weft ask` as
a query that streams an answer with citations. Generation belongs to Phase 2
and no LLM pack exists in Phase 0. **Phase 0's `weft ask` retrieves and
prints the matching passages, and says so in its help text.**" The help text
living up to that is `weft_cli.cli.COMMANDS`'s job; this module is the
retrieval itself.

**Not a pipeline stage — a direct capability resolution**, exactly as
`weft_store.contract` says a future `Retriever` will do: "`VectorSearch`...
not a `Stage`... a future `Retriever` (Phase 2) resolves this capability
directly against the configured store rather than through the runner's stage
machinery." `weft ask` is that direct resolution one phase early, with no
`Retriever` contract yet to own it. Embedding the question, though, *is* a
`Stage[Sequence[Node], Sequence[Node]]` call — `weft_embed.Embedder.run` —
so it goes through `weft_kernel.seam.wrap` exactly as `Runner._run_one_batch`
would, rather than being called bare: "if you find yourself writing a span by
hand, stop — either the seam should do it."

The question becomes a synthetic `Node` (`Node.synthetic`, `sources=frozenset()`)
purely so it can pass through `Embedder.run`'s `Sequence[Node]` signature — it
is never stored, never given lineage, and its id is discarded the moment
`HashEmbedder` returns its embedding.

**`embedder_entry.factory(None)` is trusted to satisfy `Embedder`, and cast
rather than checked** — the same trust `weft_kernel.runner._run_one_batch`
places in a resolved stage instance (`cast("Stage[object, object]", ...)`):
a pack registers a factory *under* the `Embedder` contract, which is the
declaration, not a claim the kernel separately verifies for this contract
family. `VectorSearch`, by contrast, is a genuinely *derived* capability a
`NodeStore` registration may or may not also satisfy (G4) — so that one is
checked with `isinstance`, not cast, and can legitimately fail.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import cast

from weft_embed import Embedder
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import MediaType, Node, Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.seam import wrap
from weft_store import NodeStore, Scored, VectorSearch


class NotVectorSearchableError(WeftError):
    """The registered `NodeStore` named `"pgvector"` does not also satisfy `VectorSearch`.

    Capability is derived, never declared (G4) — this is what it means for
    that derivation to come back empty: a store plugin registered under the
    same name Phase 0's built-in uses, but implementing a narrower store, is
    not something pipeline resolution alone would catch, since `search_vector`
    is never called through `Stage[In, Out]` composition.
    """


class EmbeddingFailedError(WeftError):
    """`weft-embed`'s `hash` plugin answered `NothingToProduce` or `Failed` for the question.

    `HashEmbedder` never actually returns either for a non-empty batch of one
    — this exists so a differently-configured `Embedder` named `"hash"` still
    fails loudly rather than this module silently searching with no vector.
    """


async def run_ask(
    question: str, *, registry: Registry, ctx: Context, top_k: int
) -> tuple[Scored[Node], ...]:
    """Embed `question` and return its `top_k` nearest stored passages, by vector distance."""
    embedder_entry = registry.entry(Embedder, "hash")
    embedder = cast(Embedder, embedder_entry.factory(None))
    wrapped_embed = wrap(
        embedder.run,
        distribution=embedder_entry.distribution,
        contract="Embedder",
        plugin="hash",
        stage="ask:embed",
    )
    query_node = Node.synthetic(content=question, media_type=MediaType.TEXT, reason="ask query")
    outcome: Outcome[Sequence[Node]] = await wrapped_embed([query_node], ctx)
    if not isinstance(outcome, Produced):
        raise EmbeddingFailedError(f"could not embed the question: {outcome.reason}")
    (embedded,) = outcome.value
    if embedded.embedding is None:
        raise EmbeddingFailedError("the embedder produced a node with no embedding attached")

    store_entry = registry.entry(NodeStore, "pgvector")
    store = store_entry.factory(None)
    if not isinstance(store, VectorSearch):
        raise NotVectorSearchableError(
            "the registered 'pgvector' NodeStore does not satisfy VectorSearch; "
            "weft ask has nothing to search."
        )
    try:
        return tuple(await store.search_vector(embedded.embedding, top_k))
    finally:
        aclose = _aclose_of(store)
        if aclose is not None:
            await aclose()


def render_results(results: Sequence[Scored[Node]]) -> str:
    """Ranked passages for a human reader — never the raw `score`.

    `docs/03-cli.md` -> Output, *Score display*: `Scored.score` is a similarity
    (`weft-store`'s pgvector implementation computes `1 - cosine distance`),
    unbounded and routinely negative with Phase 0's hash embedder, which is
    correct for ranking and reads as broken to a person with no context for it.
    Rank order already carries the relevance signal — `1.` is the closest
    match — so this is what a human sees; a programmatic caller still gets
    the exact float, unrendered, through `Scored[Node].score` itself.
    """
    if not results:
        return "no matching passages found."
    lines = [f"{rank}. {scored.value.content}" for rank, scored in enumerate(results, start=1)]
    return "\n".join(lines)


def _aclose_of(instance: object) -> Callable[[], Awaitable[None]] | None:
    """`instance.aclose`, if it has one and it is callable — the same defensive read
    `weft_kernel.runner`'s own `_flush_of` gives `flush`. Not part of any contract `NodeStore`
    publishes — a store may or may not have a connection worth closing.
    """
    found = getattr(instance, "aclose", None)
    if found is None or not callable(found):
        return None
    return cast(Callable[[], Awaitable[None]], found)
