"""`whole-corpus` — hands the generator every leaf of the corpus. Ledger task **43.49**.

**The setting.** Zhuowan Li, Cheng Li, Mingyang Zhang, Qiaozhu Mei, Michael Bendersky,
*Retrieval Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid
Approach*, arXiv:2407.16833 (2024), measure a long-context (**LC**) arm that reads the whole
corpus rather than retrieving from it — their own paper's baseline for the hybrid method
(Self-Route) it argues for, which this plugin does not build. Brian J. Chan, Chao-Ting Chen,
Jui-Hung Cheng, Hen-Hsen Huang, *Don't Do RAG: When Cache-Augmented Generation is All You
Need for Knowledge Tasks*, WWW Companion 2025, arXiv:2412.15605, name a related shape
**CAG**: the corpus in context plus a precomputed KV cache reloaded per query. **This plugin
diverges from CAG** and does not take its name: it sends the corpus as prompt text on every
call and controls no cache — every leaf is read and counted afresh, and nothing here is
reused between questions.

**Never reads the question.** Every leaf `weft_index.leaves.leaf_filter()` selects is
offered, in source order then chunk ordinal, whatever was asked — the corpus, not the
retrieval, is the strategy. A leaf total over `max_tokens`, counted by the generating role's
own tokenizer as it is read, is refused by name rather than silently cut: a cut corpus would
answer from whichever part happened to be read first, which is worse than a refusal that
says how to fix it.
"""

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_chunk.payload import ChunkPosition
from weft_index.leaves import leaf_filter
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, Node, Outcome, Produced
from weft_llm.contract import LLM, LLMRole, TokenCounter
from weft_retrieve.payload import Candidates, Passage, QuerySet, RankedList
from weft_store.contract import Cursor, MetadataFilter, NodeStore, Scored

#: The name this retriever is registered and selectable under — see `weft_retrieve.register`.
NAME = "whole-corpus"

_SCORE_SEMANTICS = (
    "every leaf is offered at score 1.0: no leaf was scored against the question, so this "
    "list's order carries the meaning, never its score column"
)


class WholeCorpusConfig(BaseModel):
    """`WholeCorpus`'s `with:` config. Every field has a default, per this pack's own rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Counted on the leaves alone; the prompt adds a label per passage and the question.
    max_tokens: int = Field(default=100_000, ge=1)
    #: Whose tokenizer counts: the role the generator asks, `cited-answer`'s default.
    role: Annotated[str, LLMRole()] = Field(default="generate", min_length=1)


class CorpusOverTokenBoundError(WeftError):
    """The corpus's leaves count more tokens than `max_tokens` allows. A raise, not a `Failed`.

    The fault is the corpus and its configuration, not the question this run happened to
    ask. `counted` is *at least* the true total: reading stops at the first leaf past `bound`.
    """

    def __init__(self, *, counted: int, bound: int) -> None:
        super().__init__(
            f"'{NAME}': the corpus's leaves count at least {counted:,} tokens against a "
            f"bound of {bound:,} tokens — raise max_tokens if the model's context holds "
            "the corpus, or ask a pipeline that retrieves, such as retrieve-then-generate"
        )
        self.counted = counted
        self.bound = bound


class WholeCorpus:
    """Every leaf of the bound target, as one ranked list, in source order then chunk ordinal.

    Satisfies `weft_retrieve.contract.Retriever` structurally. `needs_store =
    (MetadataFilter,)`: leaves are read through `weft_index.leaves.leaf_filter()`, evaluated
    by `weft_store.contract.MetadataFilter.matching`, the same capability
    `weft_retrieve.adjacent_chunks.AdjacentChunks` declares for the identical reason.

    See the module docstring for the citations this name is earned against and the one
    respect in which it diverges from CAG.
    """

    config_model: ClassVar[type[WholeCorpusConfig]] = WholeCorpusConfig
    needs_store: ClassVar[tuple[type, ...]] = (MetadataFilter,)
    score_semantics: ClassVar[str] = _SCORE_SEMANTICS

    def __init__(self, config: WholeCorpusConfig | None = None) -> None:
        self._config = config if config is not None else WholeCorpusConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        """Read and count every leaf of the bound store, then rank them by position.

        Never reads `payload.queries` or any query's own `filter` — the corpus offered is
        the same whatever was asked. Raises `CorpusOverTokenBoundError` the moment the
        running token count exceeds `self._config.max_tokens`; propagates
        `weft_llm.errors.TokenCountUnavailableError` untouched.
        """
        store = ctx.require(NodeStore)
        if not isinstance(store, MetadataFilter):
            return Failed(
                reason=(
                    f"'{NAME}' needs a store that can evaluate a metadata filter to read "
                    f"every leaf, and {type(store).__name__} does not provide it. Configure "
                    "a store that satisfies MetadataFilter."
                )
            )
        llm = ctx.require(LLM)
        if not isinstance(llm, TokenCounter):
            return Failed(
                reason=(
                    f"'{NAME}' counts every leaf against a token bound, but the resolved "
                    f"LLM service does not satisfy {TokenCounter.__name__} and cannot "
                    "count tokens."
                )
            )

        leaves = await _read_bounded(
            store, llm, role=self._config.role, bound=self._config.max_tokens
        )
        ordered = sorted(leaves, key=_sort_key)
        hits = tuple(
            Passage(scored=Scored(value=node, score=1.0), rank=rank, retrieved_by=NAME)
            for rank, node in enumerate(ordered)
        )
        return Produced(
            value=Candidates(
                origin=payload.origin,
                lists=(RankedList(query=payload.origin, retriever=NAME, hits=hits),),
            )
        )


async def _read_bounded(
    store: MetadataFilter, llm: TokenCounter, *, role: str, bound: int
) -> list[Node]:
    """Every leaf of `store`, counted as it is read; raises the moment the count exceeds `bound`.

    Pages until `next_cursor` is exhausted, counting one leaf at a time so the refusal fires
    having read at most one leaf past the bound — never a whole page counted before the
    first check.
    """
    leaves: list[Node] = []
    total = 0
    cursor: Cursor | None = None
    filter_ = leaf_filter()
    while True:
        page = await store.matching(filter_, cursor)
        for node in page.items:
            total += await llm.count_tokens(role, node.content)
            if total > bound:
                raise CorpusOverTokenBoundError(counted=total, bound=bound)
            leaves.append(node)
        if page.next_cursor is None:
            return leaves
        cursor = page.next_cursor


def _sort_key(node: Node) -> tuple[tuple[int, str], tuple[int, int], str]:
    """Source (smallest string, absent last), then numeric ordinal (absent last), then node id."""
    sources = node.lineage.sources
    source_key = (0, min(sources)) if sources else (1, "")
    position = node.ext_as(ChunkPosition)
    position_key = (0, position.ordinal) if position is not None else (1, 0)
    return (source_key, position_key, node.id)


__all__ = ["NAME", "CorpusOverTokenBoundError", "WholeCorpus", "WholeCorpusConfig"]
