"""`vector-top-k` — the single-pass baseline. `Retriever`, one search per query, no model call.

Task **2.14**, `docs/build-ledger.md`: "the single-pass baseline is a plugin whose name
states its cost, so an operator choosing what to run in a loop is not misled by the
registry." `docs/10-technique-catalogue.md` §1.1's own row on this technique names the
reference's mistake directly: `rag_simple` cost a floor of roughly three LLM calls with an
unbounded ceiling — a query-rewrite call, all-modes hybrid retrieval, cross-encoder
reranking and up to *N* regenerations — behind a name that promised none of it. "A plugin
an operator will run in a loop must not be called `simple`." `vector-top-k` is that
plugin's honest replacement: one embedding call, one vector search, nothing else. Its name
says exactly that, and `cost_bound` (below) restates the claim as a class attribute a
consumer can read with no instance. `.phase2-design.md` §10's own mechanism for making a
`cost_bound` mechanically checked — a unit test counting calls against the deterministic
`scripted` provider — needs a call to count: it applies to a technique that resolves the
`LLM` service and could plausibly call it a variable number of times. `vector-top-k` never
resolves an LLM-shaped service at all (`run`, below, imports nothing from `weft_llm` and
calls `ctx.require` only for `NodeStore` and `Embedder`), so there is no call for a counter
to watch. `(0, 0)` is checked here by what a `scripted`-backed counter would have checked
indirectly anyway — the absence of the resolve — read directly instead: this module's own
import list, `run`'s two `ctx.require` calls, and the class attribute below. A repair
against three reviewer findings on this exact claim replaced the counting-double test
`tests/unit/weft_retrieve/test_vector_top_k.py` used to carry with a direct assertion,
once it was clear the double was never wired into `run`'s `ServiceRegistry` and no `LLM`
service exists yet for it to be wired into — see that test module's own docstring.

**Read against `10` §2.1 rule 5 — this plugin, not a `retrieve-then-generate` plugin.**
Rule 5 reads "a composition is a pipeline, never a plugin", and gives the reference's
`rag_complex` (HyDE plus repacking on the baseline skeleton) as the worked example of a
composition that becomes a *pipeline*. `retrieve-then-generate` is `vector-top-k` then a
`Fuser` then a `ContextPacker` then a `Generator` — a composition by the same rule, not an
atomic technique. `.phase2-design.md` decision 12 reads ledger 2.14 this way rather than
literally, and this module is what makes that reading's own stated purpose true: every
name in the registry — this one included — carries a measured `cost_bound`, which is
strictly more than "a plugin named `retrieve-then-generate` exists" would have given an
operator deciding what to run in a loop. `.phase2-design.md` §13 item 2 leaves the literal
reading open for the project owner to overrule; this build takes decision 12's reading and
records that choice here rather than defaulting it silently.

**`retrieve-then-generate.yaml` is not shipped in this commit, for task 2.13's own
reason.** A resolvable pipeline needs every stage it names to be registered, and `single-
list` (task 2.7), `repack` (task 2.19) and `cited-answer` (task 2.9) are not yet — shipping
the document now would fail fitness function 11(b)'s resolve-every-shipped-pipeline check
the moment `weft-retrieve/pipelines/` stops being empty, which is exactly what
`weft_retrieve.no_retrieval`'s own module docstring recorded for `no-retrieval.yaml` one
task earlier. The pipeline lands with whichever of those three tasks closes last.

**A retriever never builds its own index** (ledger 2.5): the vector it searches with is
resolved through the `Embedder` service (`ctx.require(Embedder)`), and the index it
searches is resolved through the `NodeStore` service (`ctx.require(NodeStore)`), never
constructed here. `needs_store = (VectorSearch,)` is what `weft_cli.run_services`'s check
reads before any stage runs — see that module's own docstring — so a store that cannot
rank by vector similarity is refused by name before this class's `run` is ever called, not
discovered here as an `AttributeError` mid-batch.

**Embedding a query reuses the ingest-side `Embedder` contract rather than inventing a
second one.** `Embedder` is `Stage[Sequence[Node], Sequence[Node]]` — it attaches a vector
to a `Node`, never to a bare string — so a query's text is wrapped in a one-off
`Node.synthetic` (media type `TEXT`, a stated reason) before it is handed to the same
`run()` an ingest pipeline's embed stage calls. No second embedding contract, no second
vector representation for a query to drift from the one a corpus was indexed with.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from weft_embed.contract import Embedder
from weft_kernel.context import Context
from weft_kernel.payload import Failed, MediaType, Node, NothingToProduce, Outcome, Produced, Vector
from weft_retrieve.payload import Candidates, Channel, Passage, QuerySet, RankedList
from weft_store.contract import NodeStore, VectorSearch

#: The name this retriever is registered and selectable under — see `weft_retrieve.register`.
NAME = "vector-top-k"


class VectorTopKConfig(BaseModel):
    """`VectorTopK`'s `with:` config. Every field has a default, per the project's rule that
    every Phase 2 pack's settings must be constructible with none supplied.

    `per_query_top_k`, when set, is what is actually asked of the store for every query in
    the set — `top_k` alone otherwise. The two names exist so a document can say "twenty
    results for the question as asked" (`top_k`) while making the *per-query* meaning
    explicit at the point a fan-out transform ahead of this stage turns one query into
    several, rather than reading as a total this retriever might divide across them. This
    reading was not settled by `.phase2-design.md`'s own table, which names both fields
    with no further text; it is this build's smallest defensible choice, recorded here
    rather than left silent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    top_k: int = 20
    per_query_top_k: int | None = None
    channels: tuple[Channel, ...] = (Channel.VECTOR,)

    @field_validator("channels", mode="after")
    @classmethod
    def _only_vector(cls, value: tuple[Channel, ...]) -> tuple[Channel, ...]:
        """This plugin declares `needs_store = (VectorSearch,)` alone — no `TextSearch`.

        A `channels` value naming an arm this class has no store capability to search would
        otherwise be accepted and fail later, at the first `search_text` call this class
        never makes, as an `AttributeError` with nothing in it naming the real mistake. The
        project's own rule is that a silent fallback is worse than a failure; this is that
        rule applied to a config field rather than to a code path. `hybrid` is named in the
        message because it is the plugin built to search more than one arm.
        """
        unsupported = tuple(channel for channel in value if channel is not Channel.VECTOR)
        if unsupported:
            names = ", ".join(sorted(channel.value for channel in unsupported))
            raise ValueError(
                f"'{NAME}' can only search the vector arm — it declares needs_store = "
                f"(VectorSearch,) and calls no other search method. channels named here "
                f"that it cannot search: {names}. Use 'hybrid' for a retriever that "
                f"searches more than one arm."
            )
        return value


class VectorTopK:
    """One vector search per query. Satisfies `weft_retrieve.contract.Retriever` structurally.

    `cost_bound = (0, 0)` is this plugin's own claim: an operator reading the name and the
    bound together learns the whole cost before running anything. It is checked here by
    what `run` (below) actually resolves — `NodeStore` and `Embedder`, never an `LLM`
    service — and by `tests/unit/weft_retrieve/test_vector_top_k.py`'s direct assertion on
    this class attribute, the same honest shape task 2.13's `NoRetrieval.cost_bound` test
    already used. See the module docstring for why a call-counting test — the mechanism
    `.phase2-design.md` §10 names for a technique that resolves `LLM` a variable number of
    times — does not apply to a plugin that never resolves it at all.
    """

    config_model: ClassVar[type[VectorTopKConfig]] = VectorTopKConfig
    needs_store: ClassVar[tuple[type, ...]] = (VectorSearch,)
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: VectorTopKConfig | None = None) -> None:
        self._config = config if config is not None else VectorTopKConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        """One `RankedList` per query this retriever's own arm matches, never fused.

        A query whose own `channels` names arms none of which this retriever offers is
        skipped — it gets no `RankedList` at all, the same "never asked" fact
        `weft_retrieve.payload.Candidates`'s own docstring draws a line around, applied per
        query rather than to the whole batch. A query the store *did* search but that
        matched nothing still gets a `RankedList` with `hits=()` — the emptiness rule
        stated on every contract in this module's sibling `contract.py`.

        The configured store is resolved as `NodeStore` (`weft_cli`'s future run assembler
        adds it under that contract, per `.phase2-design.md` §3) and narrowed to
        `VectorSearch` here with `isinstance`, not assumed. `needs_store` is what makes a
        store lacking that capability *refused before this method is ever reached* once
        something calls `weft_cli.run_services.check_store_capabilities` — nothing does yet
        (that module's own docstring: "the assembler that will call it lands with"
        tasks 2.8 and 2.10). Until it does, this is the one line standing between a
        misconfigured store and the `AttributeError` mid-batch task 2.5's own repair closed
        for the fallback chain — closed here too, as a named `Failed` rather than a crash.

        `payload.ext` is carried onto `Candidates.ext` unchanged — the fix, added by ledger
        2.23, for a gap that plugin's own worked example exposed: `QuerySet.ext` is where a
        `QueryTransform` attaches something a later stage needs (`weft_retrieve.payload`'s own
        module docstring), but neither this nor `no-retrieval` used to carry it across the
        retrieve position at all, so anything attached upstream was silently dropped the
        moment a retriever ran. `weft_retrieve.boolean.BooleanRetrieval` is the first plugin
        that actually needs what crosses this line to survive: `BooleanPlan`, read back by
        `weft_retrieve.fusion.BooleanCombine` two stages later.
        """
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
        offered = frozenset(channel.value for channel in self._config.channels)
        top_k = (
            self._config.per_query_top_k
            if self._config.per_query_top_k is not None
            else self._config.top_k
        )

        lists: list[RankedList] = []
        for query in payload.queries:
            wanted = frozenset(query.channels) if query.channels else offered
            if not wanted & offered:
                continue
            vector = await _embed(query.text, embedder=embedder, ctx=ctx)
            if isinstance(vector, Failed):
                return vector
            scored = await store.search_vector(vector, top_k, filter=query.filter)
            hits = tuple(
                Passage(scored=item, rank=rank, retrieved_by=NAME)
                for rank, item in enumerate(scored)
            )
            lists.append(
                RankedList(query=query, retriever=NAME, channel=Channel.VECTOR.value, hits=hits)
            )

        return Produced(
            value=Candidates(origin=payload.origin, lists=tuple(lists), ext=payload.ext)
        )


async def _embed(text: str, *, embedder: Embedder, ctx: Context) -> Vector | Failed:
    """`text`, embedded through the ingest-side `Embedder` contract — see the module docstring.

    Wraps the one query in a one-node batch rather than a bespoke single-string method,
    reusing exactly the code path a corpus was indexed through. `Failed` reports an
    embedder that ran but produced nothing usable for a batch of exactly one node — a
    result the contract permits only for an *empty* batch (`weft_embed.contract.Embedder`'s
    own docstring), so seeing it here names the embedder as having broken its own contract
    rather than silently searching with no vector.
    """
    node = Node.synthetic(
        content=text, media_type=MediaType.TEXT, reason="query text embedded for vector-top-k"
    )
    outcome = await embedder.run([node], ctx)
    if isinstance(outcome, Failed):
        return outcome
    if isinstance(outcome, NothingToProduce):
        return Failed(
            reason=(
                f"the configured embedder produced nothing for a one-node query batch: "
                f"{outcome.reason}"
            )
        )
    embedded = outcome.value[0]
    if embedded.embedding is None:
        return Failed(
            reason="the configured embedder ran and returned a node carrying no embedding"
        )
    return embedded.embedding
