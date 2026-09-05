"""`multi-arm` — one query, several bases, one `Candidates`.

**Why this is a plugin and not a pipeline, which is the opposite of this project's usual
answer.** `docs/01-high-level-plan.md` requirement 3 makes pipelines data, and
`10-technique-catalogue.md` §2.1 rule 5 says a composition is a pipeline and never a plugin. So
the first attempt at "search the leaf chunks and the RAPTOR summaries at once" was a document
naming `vector-top-k` twice. **It does not resolve, and the binary is what said why:** *stage
'retrieve-raptor' expects `QuerySet`, but the previous stage 'retrieve-leaves' produces
`Candidates`. Consecutive stages must compose by type.*

A pipeline is an **ordered list** — G2 settled that, adding derivation, slots and declared
constraints on top of it rather than branching. Two retrievers therefore cannot sit side by
side, because the second would have to consume what the first produced. Everything Weft calls
"fan-out" today fans out over **queries**: `multi-query` turns one question into several and one
retriever returns one `RankedList` per query (ledger 2.18). Nothing fanned out over **arms**,
and `.phase2-design.md`'s row for `hybrid` — the plugin that was to search more than one arm —
carries `—` in its task-id column and was never built.

That leaves one place the arity can grow without reopening a settled gate: **inside a single
`Retriever`**, whose contract already returns a `Candidates` holding *many* `RankedList`s. This
plugin is that. It is a composition and it is a plugin, because the pipeline model cannot hold
it — recorded here rather than left for a reader to trip over, since it is a deliberate
exception to a documented rule and the reason is structural rather than a preference.

**An arm is a slice of the index that names itself.** Not a backend and not a store: the same
`VectorSearch`, narrowed by a `Filter` and labelled so a `Fuser` can address it.
`weft_retrieve.fusion.contributor_label` is `retriever:channel`, so an arm named `raptor`
becomes the key `multi-arm:raptor`, and `reciprocal-rank-fusion`'s `weights` mapping is written
against those keys. `RankedList.channel` is a `str` rather than the `Channel` enum for precisely
this reason — `weft_retrieve.payload.Channel`'s own docstring calls itself *a vocabulary,
deliberately not a field type*, because `02` names graph traversal among the ways backends
genuinely differ. A new base needs no core edit and no new enum member anywhere.

**One embedding per query, not one per arm.** Arms differ by filter, never by vector. Embedding
once and searching N times is not an optimisation but the only correct reading: two arms
searching the same question from two separately-computed vectors would be two different
questions the moment an embedder were non-deterministic, and it would cost N times the calls to
say so.

**What this does not do.** It does not search a *lexical* arm — every arm here goes through
`VectorSearch`, which is what `needs_store` declares and what the refusal below names. A true
vector-plus-lexical hybrid needs `TextSearch` as well and is still the unbuilt `hybrid` row;
taking that name here would be exactly the overclaim `10` §2.1 rule 4 forbids. It also does not
fuse: arity reduction is a `Fuser`'s position, and a retriever that quietly merged its own arms
would be one plugin doing two jobs, with the fusion policy unreachable from a pipeline
document.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_embed.contract import Embedder
from weft_kernel.context import Context
from weft_kernel.payload import Failed, Outcome, Produced, Vector
from weft_retrieve.payload import Candidates, Passage, Query, QuerySet, RankedList
from weft_retrieve.vector_top_k import combined_filter, embed_query
from weft_store.contract import Filter, NodeStore, VectorSearch

#: The name this plugin is registered and selectable under — see `weft_retrieve.register`.
NAME = "multi-arm"


class Arm(BaseModel):
    """One base: what to call it, how deep to go, and which slice of the index it covers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: What this arm contributes under. Becomes `RankedList.channel`, and therefore the
    #: `retriever:channel` key a `Fuser`'s `weights` mapping is written against. Two arms
    #: sharing a name would be two lists an operator has no way to weight apart, which is why
    #: the config below refuses duplicates rather than leaving the label ambiguous.
    name: str = Field(min_length=1)
    top_k: int = Field(default=20, ge=1)
    #: Narrows this arm. `None` means the whole index. The honest spelling of an
    #: "everything else" arm is a `not` over the other arms' filters, written in the document
    #: where a reader can see it, rather than a mode this plugin infers from the others.
    filter: Filter | None = None


class MultiArmConfig(BaseModel):
    """`multi-arm`'s `with:` config."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: At least two, because one arm is `vector-top-k` and should be spelled that way. A plugin
    #: whose whole purpose is arity, handed arity one, is a document mistake — and `02` §2's
    #: rule is that those are refused by name rather than quietly tolerated.
    arms: tuple[Arm, ...] = Field(min_length=2)

    def model_post_init(self, context: object, /) -> None:
        del context
        names = [arm.name for arm in self.arms]
        if len(set(names)) != len(names):
            raise ValueError(
                f"'{NAME}' arms must have distinct names — a Fuser addresses an arm by its "
                f"'{NAME}:<name>' label, so duplicates leave an operator no key to weight "
                f"them apart. Got: {names}"
            )


class MultiArm:
    """Satisfies `contract.Retriever` structurally — see the module docstring."""

    config_model: ClassVar[type[MultiArmConfig]] = MultiArmConfig
    needs_store: ClassVar[tuple[type, ...]] = (VectorSearch,)

    def __init__(self, config: MultiArmConfig) -> None:
        self._config = config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        store = ctx.require(NodeStore)
        if not isinstance(store, VectorSearch):
            return Failed(
                reason=(
                    f"'{NAME}' needs vector search from the configured store, and "
                    f"{type(store).__name__} does not provide it. Configure a store that "
                    f"satisfies VectorSearch."
                )
            )
        embedder = ctx.require(Embedder)

        lists: list[RankedList] = []
        for query in payload.queries:
            vector = await embed_query(query.text, embedder=embedder, ctx=ctx)
            if isinstance(vector, Failed):
                return vector
            for arm in self._config.arms:
                lists.append(await self._search(store, query, arm, vector))

        return Produced(
            value=Candidates(origin=payload.origin, lists=tuple(lists), ext=payload.ext)
        )

    async def _search(
        self, store: VectorSearch, query: Query, arm: Arm, vector: Vector
    ) -> RankedList:
        """One arm's ranked list for one query, labelled with the arm's own name."""
        scored = await store.search_vector(
            vector, arm.top_k, filter=combined_filter(query.filter, arm.filter)
        )
        hits = tuple(
            Passage(scored=item, rank=rank, retrieved_by=NAME) for rank, item in enumerate(scored)
        )
        return RankedList(query=query, retriever=NAME, channel=arm.name, hits=hits)
