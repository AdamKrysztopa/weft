"""`hybrid` — one query, two arms of the same store, fused downstream. Ledger task **8.6**.

**The name was promised before the plugin existed, and this is that promise kept.**
`weft_retrieve.vector_top_k`'s own config validator has been telling operators *"Use 'hybrid'
for a retriever that [searches more than one arm]"* since task 2.14, and `10` §1.5's
`multi-arm` row has been saying *"Not `hybrid`, which additionally needs `TextSearch`"* since
2.33 — a name printed at users in a refusal, documented in the catalogue, and installable by
nobody. Meanwhile `weft_store.pgvector_store.search_text` was implemented and had **no caller
in the tree**. Two halves, each correct, meeting nowhere.

**What it does, in one line, because if it needs two it is a pipeline** (`10`'s own
diagnostic): searches the vector arm and the text arm of the configured store for each query
and returns both rankings, labelled apart.

**What it deliberately does not do: score fusion.** Most implementations carrying this name
combine dense and lexical results by normalising the two score distributions and taking a
weighted sum — an alpha. This one does not, and the reason is a boundary rather than a
preference: fusing ranked lists is `Fuser`'s position in the pipeline, and
`reciprocal-rank-fusion` already does it *by rank*, which needs no calibration between two
score scales that have no common unit. A cosine similarity and a lexical relevance score are
not comparable numbers, and an alpha over them is a tuning constant nobody can defend —
exactly what `10` §1.1 records against the reference, whose RRF existed twice and *"only the
second copy grew weighted-alpha behaviour"*. Two copies of one technique is what a missing
plugin boundary looks like; this plugin is on the right side of that boundary and stops there.

So the composition is a **document**: `hybrid` produces two `RankedList`s per query,
`reciprocal-rank-fusion` merges them, and an operator who wants the arms weighted apart writes
`weights: {"hybrid:vector": 1.0, "hybrid:text": 0.7}` — the same mapping key
`weft_retrieve.fusion.contributor_label` builds for every other retriever, with no branch
anywhere asking which kind of multiplicity it was handed.

**Why a plugin at all, rather than two stages.** The identical exception `multi-arm` already
carries and `10` §1.5 already documents: a composition is normally a pipeline, but two
retrievers cannot sit in sequence because they do not compose by type — `Retriever` is
`Stage[QuerySet, Candidates]`, so the second would be handed the first's output rather than
the query. The arity has to live inside one plugin. And it is not a `channels` value on
`vector-top-k`, because that plugin's name is a claim about its cost — *"one embedding call,
one vector search, nothing else"* — and a second search behind it would make the name lie.

**No citation, and that is the honest answer rather than a gap.** "Hybrid retrieval" is a
practitioner and framework term for a store satisfying both search protocols, which is exactly
how `02` §1 and `weft_retrieve.payload.Channel`'s own docstring already define it in this tree
(*"Hybrid is not a third method — it is a store satisfying both search protocols"*). The
technique it composes — combining evidence from several rankings — is `reciprocal-rank-fusion`,
which carries the citation. A row in `10` §1.5 beside `multi-arm` is where a name with nothing
of its own to cite belongs; inventing a paper for it would be the false provenance §2.1 rule 4
forbids, and `10` §5 records what this catalogue has not searched.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from weft_embed.contract import Embedder
from weft_kernel.context import Context
from weft_kernel.payload import Failed, Node, Outcome, Produced
from weft_retrieve.payload import Candidates, Channel, Passage, Query, QuerySet, RankedList
from weft_retrieve.vector_top_k import combined_filter, embed_query
from weft_store.contract import Filter, NodeStore, Scored, TextSearch, VectorSearch

NAME: Final[str] = "hybrid"


class HybridConfig(BaseModel):
    """`hybrid`'s `with:` config. Every field has a default, per this pack's own rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many hits to ask each arm for. **One number, not one per arm**, deliberately: the
    #: arms are two views of one corpus, and a document that wanted them asked at different
    #: depths is expressing a weighting, which belongs on the `Fuser` where it can be stated
    #: as a weight rather than smuggled in as a depth.
    top_k: int = Field(default=20, ge=1)
    per_query_top_k: int | None = Field(default=None, ge=1)
    #: Which arms to search. Both by default — that is what the name means — and narrowing to
    #: one is legal so a document can A/B a single arm against the pair without swapping the
    #: plugin out. `needs_store` is still both, on purpose: see `Hybrid`'s own docstring.
    channels: tuple[Channel, ...] = (Channel.VECTOR, Channel.TEXT)
    #: What each arm calls itself when a `Fuser` combines them — `hybrid:vector` and
    #: `hybrid:text` in a `reciprocal-rank-fusion` `weights` mapping. Two fields rather than
    #: one prefix, so a document naming this retriever twice over two narrowings can tell all
    #: four lists apart.
    vector_arm: str = Field(default=Channel.VECTOR.value, min_length=1)
    text_arm: str = Field(default=Channel.TEXT.value, min_length=1)
    #: Narrows **both** arms to part of the index, combined with the query's own filter
    #: exactly as `vector-top-k` combines it. One filter rather than one per arm: an arm-shaped
    #: narrowing is what `multi-arm` is for, and two plugins offering the same knob in
    #: different shapes is how a configuration surface stops being learnable.
    filter: Filter | None = None

    @field_validator("channels", mode="after")
    @classmethod
    def _at_least_one_arm(cls, value: tuple[Channel, ...]) -> tuple[Channel, ...]:
        """An empty `channels` would retrieve nothing and report success.

        `Channel` has exactly two members, so there is no unknown-arm case to refuse here —
        pydantic has already rejected anything that is not one of the two, at the field, where
        the typo was made. What it cannot catch is the empty tuple, which is valid as a tuple
        and meaningless as a retrieval: every query would produce no list, the `Fuser` would
        combine nothing, and the answer would be *"no evidence"* from a run that never looked.
        That is the silent-plausible-answer failure `CLAUDE.md` singles out, so it is refused.
        """
        if not value:
            raise ValueError(
                f"'{NAME}' was configured with no channels at all, so it would search "
                f"nothing and return an empty ranking indistinguishable from a corpus with "
                f"no match. Name at least one of: "
                f"{', '.join(channel.value for channel in Channel)}."
            )
        return value


class Hybrid:
    """Searches the vector and text arms of one store per query. Satisfies `Retriever`.

    `needs_store = (VectorSearch, TextSearch)` — **both, regardless of `channels`**, and that
    is a choice rather than an oversight. `weft_cli.run_services.check_store_capabilities`
    reads this declaration before any stage runs, so a document naming `hybrid` against a store
    that cannot do lexical search is refused at assembly, by name, with the capability and the
    stores that provide it. Deriving the requirement from `channels` instead would let
    `channels: [vector]` resolve happily against `qdrant` — which deliberately advertises no
    `TextSearch` (ledger 2.6) — and then the day somebody restored the text arm they would meet
    the refusal, having changed one word in a `with:` block. **What a plugin declares it needs
    is what it will call under its own configuration surface, not under the one configuration
    it happens to be holding.**
    """

    config_model: ClassVar[type[HybridConfig]] = HybridConfig
    needs_store: ClassVar[tuple[type, ...]] = (VectorSearch, TextSearch)

    def __init__(self, config: HybridConfig | None = None) -> None:
        self._config = config if config is not None else HybridConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        store = ctx.require(NodeStore)
        # Written out rather than looped over `needs_store`, for two reasons that point the
        # same way: `isinstance` against a loop variable narrows nothing, so the calls below
        # would need a suppression each; and the two capabilities are not interchangeable to
        # the operator reading the refusal — the remedy for a missing `TextSearch` is
        # `vector-top-k`, and there is no equivalent for a missing `VectorSearch`.
        if not isinstance(store, VectorSearch):
            return Failed(reason=_missing(store, "VectorSearch"))
        if not isinstance(store, TextSearch):
            return Failed(reason=_missing(store, "TextSearch"))
        offered = frozenset(channel.value for channel in self._config.channels)
        top_k = (
            self._config.per_query_top_k
            if self._config.per_query_top_k is not None
            else self._config.top_k
        )

        lists: list[RankedList] = []
        for query in payload.queries:
            # `Query.channels` is what this query asks for; `channels` above is what this
            # stage offers. The intersection runs — the identical rule `vector-top-k` applies
            # to its single arm, so a `QueryTransform` that labels its output for one arm
            # narrows this retriever the same way it narrows that one.
            asked = frozenset(query.channels) if query.channels else offered
            arms = asked & offered
            if not arms:
                continue
            narrowing = combined_filter(query.filter, self._config.filter)
            if Channel.VECTOR.value in arms:
                vector = await embed_query(query.text, embedder=ctx.require(Embedder), ctx=ctx)
                if isinstance(vector, Failed):
                    return vector
                lists.append(
                    _ranked(
                        query,
                        await store.search_vector(vector, top_k, filter=narrowing),
                        arm=self._config.vector_arm,
                    )
                )
            if Channel.TEXT.value in arms:
                # The query's own text, never an embedding of it: a lexical index is asked for
                # words. This is the call `weft_store.pgvector_store.search_text` has been
                # waiting for since it was written.
                lists.append(
                    _ranked(
                        query,
                        await store.search_text(query.text, top_k, filter=narrowing),
                        arm=self._config.text_arm,
                    )
                )

        return Produced(
            value=Candidates(origin=payload.origin, lists=tuple(lists), ext=payload.ext)
        )


def _missing(store: object, capability: str) -> str:
    """The refusal, naming what was wanted, why it is unavailable, and what to do — `01`
    requirement 5's three clauses. The `vector-top-k` remedy is offered only because it is
    real: a store with vector search and no text search can still run that plugin."""
    return (
        f"'{NAME}' needs {capability} from the configured store, and "
        f"{type(store).__name__} does not provide it. Configure a store that satisfies both "
        f"VectorSearch and TextSearch, or use 'vector-top-k' for the vector arm alone."
    )


def _ranked(query: Query, scored: Sequence[Scored[Node]], *, arm: str) -> RankedList:
    """One arm's answer as a `RankedList`, ranked by the order the store returned it in.

    Rank comes from position, never from the score, and that is the same boundary the module
    docstring draws: the two arms' scores are on scales with no common unit, and the reason
    this plugin hands both lists downstream instead of merging them is that
    `reciprocal-rank-fusion` combines by *rank* and therefore needs no calibration. Re-sorting
    here by score would quietly reintroduce the comparison this plugin refuses to make.
    """
    return RankedList(
        query=query,
        retriever=NAME,
        channel=arm,
        hits=tuple(
            Passage(scored=item, rank=rank, retrieved_by=NAME) for rank, item in enumerate(scored)
        ),
    )
