"""`postqfrap` — the second `ContextPacker`. Ledger task **10.15**.

`docs/internal/build-ledger.md`'s own line for this task, and `10` §4's own row: Chucri, Azouz &
Ott, *Recursive Abstractive Processing for Retrieval in Dynamic Datasets*, 2024,
arXiv:2410.01736 §5, Algorithm 3, read at source: retrieve `k0` chunks — upstream of this
stage, arriving as `Ranking.hits` — build a **query-focused** recursive-abstractive tree
over them with **one-step clustering**, then generate one final query-focused summary from
the tree's top layer *instead of* returning a top-k list.

**Why a `ContextPacker` and not an `Expander`, which is what grilling session G15 first
proposed.** `weft_index.contract.Expander.run` takes `(payload, ctx)` and no query — a
query-time summariser is not that shape. `Ranking` carries `origin: Query`, and
`ContextPacker` is already `Stage[Ranking, Passages]`, so the question this technique needs
is already in hand at exactly the position it occupies. No contract change, no ambient
query, and nothing stored — the retrieval path has no `store` stage at all.

**Reuses `weft_index.raptor`'s clustering shape, not its code.** `_cluster_by_similarity`
there is a private helper of another pack, so this module writes its own — greedy,
single-pass, cosine similarity against a running centroid, id-sorted first so the result is
a function of the node *set* this stage was handed, never of `Ranking.hits`' own arrival
order. `similarity_threshold` here is a plain typed float, never `raptor`'s `Auto`
machinery: this stage sees only the `k0` chunks a retriever already selected, which §5.2
treats as one global cluster already filtered from the whole corpus, so a percentile
computed over just those `k0` vectors describes nothing an operator's own number would not.

**Divergence from the paper, first: order-based clustering above the leaf level.** A cluster
summary carries no embedding of its own — nothing in this pipeline position re-embeds it,
and inventing an `Embedder` requirement on the query path would make this stage unusable in
every pipeline that has none, which is most of them (`weft_index.raptor`'s own module
docstring makes the identical argument on the ingest side, for the identical reason).
So level 2 and beyond group the previous level's summaries by *order* — id-sorted, then
chunked into `cluster_size`-sized groups — never by similarity. §5.2's own argument that the
retrieved set is already one global cluster applies here a second time: a second similarity
pass over an already-filtered set has little left to separate.

**Divergence from the paper, second: `max_levels`, which Algorithm 3 does not have.** Its
own stop rule is width- and depth-conditioned together ("while the top layer contains more
than 10 nodes and there are fewer than 5 layers"), with both constants asserted and no
ablation behind either. Weft keeps only the depth half, as an explicit ceiling an operator
sets, because every level here costs model calls at *query* time — a cost `raptor`'s own
ingest-time tree does not carry the same way.

**The final step, read literally.** Algorithm 3 step 5 asks for one summary over whatever
the tree's top layer holds, *instead of* a top-k list — not a fixed extra call on top of
however many levels the recursion already built. So `run` recurses level by level until
either exactly one summary remains or `max_levels` is reached, and only performs a further,
genuinely final summarising call when more than one summary is still standing at that point;
when the recursion has already reduced the tree to one node, that node already *is* "the one
summary the top layer holds" and no redundant call is made over it. Reading Algorithm 3 as
"always call once more" would spend a model call proving what construction already
guarantees — a summary over a single member is that member, not a shorter version of it.

**A hit with no embedding is refused by name, never silently dropped.** §5.2: "we modify the
clustering to rely solely on local embeddings, as retrieving k0 documents already serves as
a global filtering step." A store hands its vectors back with its nodes, so a hit without
one means this stage was placed after something that stripped them —
`weft_index.raptor`'s own unembedded-node refusal is the precedent this module follows for
wording and shape.
"""

import asyncio
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Failed, MediaType, Node, Outcome, Produced, Vector
from weft_llm.contract import LLM
from weft_prompts.contract import Prompts
from weft_retrieve.payload import Passage, Passages, Ranking
from weft_retrieve.prompts import SUMMARIZE_FOR_QUERY_NAME, SummarizeForQueryRequest
from weft_store.contract import Scored

#: The name this packer is registered and selectable under — `10` §4's own reservation, and
#: `10` §2.1 rule 3: use the literature's own name for its own technique.
NAME = "postqfrap"


class PostQfrapConfig(BaseModel):
    """`postqfrap`'s `with:` config. Every field has a default, per this pack's own rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The greedy cluster cap — the most members one cluster (or, above the leaf level, one
    #: order-based group) may hold. `weft_index.raptor.RaptorConfig.cluster_size`'s own
    #: comment applies verbatim: not "how many clusters", which falls out of the corpus.
    cluster_size: int = Field(default=4, ge=2)
    #: The cosine-similarity floor a node must clear against a cluster's running centroid to
    #: join it, at the leaf level only. A typed default, never `raptor`'s `Auto`: this stage
    #: sees only the `k0` chunks a retriever already selected, which the paper's own §5.2
    #: already treats as one global cluster, so a percentile computed over just those `k0`
    #: vectors would describe nothing an operator's own number does not already say.
    similarity_threshold: float = Field(default=0.5, ge=-1.0, le=1.0)
    #: A ceiling on the recursion, because each level costs model calls at *query* time —
    #: unlike `raptor`'s ingest-time tree, this cost is paid on every question asked. Not in
    #: Algorithm 3, which stops on a width condition alone — see the module docstring.
    max_levels: int = Field(default=3, ge=1)
    #: The most cluster text one summary request may carry, shared evenly across a cluster's
    #: members — `weft_index.raptor.RaptorConfig.max_cluster_chars`'s own reasoning, one
    #: pipeline position over: without a cap, a single oversized cluster could exceed a
    #: model's context and take its summary with it.
    max_cluster_chars: int = Field(default=12_000, ge=100)
    #: How many summarising calls may be in flight at once, at any one level. Unbounded
    #: `asyncio.gather` over every cluster would fire as many concurrent completions as
    #: `k0` happened to cluster into, against whatever provider is configured — an
    #: operator's own fact, not this plugin's, which is why it is a field rather than a
    #: constant (`raptor`'s own `max_concurrent_summaries` states the identical reasoning).
    max_concurrent_summaries: int = Field(default=8, ge=1)
    prompt: str = Field(default=SUMMARIZE_FOR_QUERY_NAME, min_length=1)
    #: **`index`, not `generate`, and the reason was found by running the binary.** This does
    #: run on the query path, so `generate` reads like the obvious default — and it produced
    #: garbage on a real `weft ask`: `weft_cli.sinks.DEFAULT_DISPLAY_ROLES` is exactly
    #: `{"generate"}`, so every one of these concurrent intermediate summaries streamed to the
    #: terminal at once and interleaved word by word, above an answer that was itself correct.
    #: A role names a *model mapping*, not a pipeline path, and these are summarisation calls —
    #: the same class of work `weft_index.raptor` does under `index`, with the same shape of
    #: prompt. Running them there keeps the answer channel to the answer.
    #:
    #: *The cost, stated:* a deployment that maps `generate` and not `index` — a query-only
    #: installation — gets a loud refusal naming the role and every role that *is* mapped
    #: (`weft_llm.client`'s `UnmappedLLMRoleError`), rather than a garbled answer. Set
    #: `role: generate` in a derived document if that is the trade you want; the interleaving
    #: is what you are buying.
    #:
    #: The deeper fact is not this plugin's to fix: **any concurrent stage on a displayed role
    #: interleaves**, because a `TokenChunk` carries a role and nothing finer, so a sink cannot
    #: tell the generator's tokens from an intermediate stage's on the same role. Filed as a
    #: carried repair rather than widened into this task.
    role: str = Field(default="index", min_length=1)


class PostQfrapPacker:
    """Clusters `Ranking.hits` into a query-focused recursive-abstractive tree and returns
    one synthesised `Passage` instead of a top-k list. Satisfies `weft_retrieve.contract.
    ContextPacker` structurally — never imported here, per this tree's own rule that a
    plugin never imports the contract it satisfies.
    """

    config_model = PostQfrapConfig

    def __init__(self, config: PostQfrapConfig | None = None) -> None:
        self._config = config if config is not None else PostQfrapConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Passages]:
        """Cluster, summarise, recurse, and pack the result into one labelled `Passage`.

        **The emptiness rule** — no hits at all packs to empty `Passages`, with no
        clustering and no model call, the identical case `weft_retrieve.repack.Repack.run`
        handles and for the identical reason (`weft_retrieve.contract`'s own emptiness rule;
        `09` §4's V2 requires the engine to be able to answer "not in this corpus").
        """
        if not payload.hits:
            return Produced(value=Passages(origin=payload.origin, ext=payload.ext))

        unembedded = sum(1 for hit in payload.hits if hit.node.embedding is None)
        if unembedded:
            return Failed(
                reason=(
                    f"'{NAME}' received {unembedded} hit(s) with no embedding out of "
                    f"{len(payload.hits)}. This stage clusters on the vectors it is handed "
                    f"and computes none itself, so a store or an upstream stage stripped "
                    f"them before it ran — check that this packer sits after the retriever "
                    f"that produced 'Ranking.hits', not after something that discarded "
                    f"their vectors"
                )
            )

        prompts = ctx.require(Prompts)
        llm = ctx.require(LLM)
        limit = asyncio.Semaphore(self._config.max_concurrent_summaries)
        query = payload.origin.text

        # Every hit was just confirmed embedded above, so this is a narrowing, not a guess.
        embedded = tuple(
            (hit.node, hit.node.embedding) for hit in payload.hits if hit.node.embedding is not None
        )
        clusters = _cluster_by_similarity(
            embedded,
            cluster_size=self._config.cluster_size,
            similarity_threshold=self._config.similarity_threshold,
        )
        current = await self._summarize_all(
            clusters, query=query, prompts=prompts, llm=llm, ctx=ctx, limit=limit
        )
        if isinstance(current, Failed):
            return current

        levels_built = 1
        while len(current) > 1 and levels_built < self._config.max_levels:
            groups = _group_by_order(current, size=self._config.cluster_size)
            summarized = await self._summarize_all(
                groups, query=query, prompts=prompts, llm=llm, ctx=ctx, limit=limit
            )
            if isinstance(summarized, Failed):
                return summarized
            current = summarized
            levels_built += 1

        if len(current) == 1:
            # The recursion already reduced the tree to one node — that node already *is*
            # "the one summary the top layer holds" (see the module docstring's closing
            # section), so no redundant call is made over a single member.
            final = current[0]
        else:
            # Algorithm 3 step 5, read literally: one summary over whatever the top layer
            # holds — every remaining node treated as a single group, never chunked further
            # by `cluster_size`, because this call's whole job is to end the recursion at
            # exactly one node regardless of how many levels `max_levels` left standing.
            final_result = await self._summarize_all(
                (current,), query=query, prompts=prompts, llm=llm, ctx=ctx, limit=limit
            )
            if isinstance(final_result, Failed):
                return final_result
            final = final_result[0]

        best_score = max(hit.score for hit in payload.hits)
        passage = Passage(
            scored=Scored(value=final, score=best_score),
            rank=0,
            retrieved_by=NAME,
            label="1",
        )
        return Produced(value=Passages(origin=payload.origin, passages=(passage,), ext=payload.ext))

    async def _summarize_all(
        self,
        groups: Sequence[Sequence[Node]],
        *,
        query: str,
        prompts: Prompts,
        llm: LLM,
        ctx: Context,
        limit: asyncio.Semaphore,
    ) -> tuple[Node, ...] | Failed:
        """Every group in `groups`, summarised concurrently and bounded by `limit`.

        A group that degrades (the prompt or the model declined) contributes nothing rather
        than raising — `weft_index.raptor.RaptorSummarizer._summarize`'s own "degrade,
        never fail the run" posture for a single cluster. But every group in `groups`
        degrading is a different fact — the ambient model service being unusable for this
        whole call — and that is worth saying rather than silently returning an empty tree,
        which `run` could never recurse or finish from.
        """

        async def _bounded(group: Sequence[Node]) -> Node | None:
            async with limit:
                return await self._summarize(group, query=query, prompts=prompts, llm=llm, ctx=ctx)

        summaries = await asyncio.gather(*(_bounded(group) for group in groups))
        derived = tuple(summary for summary in summaries if summary is not None)
        if not derived:
            return Failed(
                reason=(
                    f"'{NAME}' summarised none of its {len(groups)} cluster(s) at this "
                    f"level: every summary request degraded, so the tree could not build "
                    f"another level"
                )
            )
        return derived

    async def _summarize(
        self, members: Sequence[Node], *, query: str, prompts: Prompts, llm: LLM, ctx: Context
    ) -> Node | None:
        """One cluster's query-focused summary node, or `None` when generation degrades —
        never raised. A misconfigured `prompt:` name or an unmapped `role:` still raises:
        that is an operator's own document being wrong, the same split
        `weft_index.hypothetical_questions`'s own docstring draws.
        """
        passages = _format_cluster(members, budget=self._config.max_cluster_chars)
        values = SummarizeForQueryRequest(query=query, passages=passages)
        rendered = await prompts.render(self._config.prompt, values, ctx)
        if not isinstance(rendered, Produced):
            return None
        completion = await llm.complete(rendered.value, role=self._config.role, ctx=ctx)
        if not isinstance(completion, Produced):
            return None
        summary = completion.value.text.strip()
        if not summary:
            return None
        return Node.combine(members, content=summary, media_type=MediaType.TEXT)


def _group_by_order(nodes: Sequence[Node], *, size: int) -> list[list[Node]]:
    """`nodes`, id-sorted for determinism and then chunked into groups of at most `size`.

    Summaries carry no embedding of their own (see the module docstring's first divergence),
    so above the leaf level there is nothing to cluster *by* — grouping by order is what
    "cluster by order" means here, and id-sorting first keeps the grouping a function of the
    node set a level actually holds, never of whichever order `asyncio.gather` happened to
    return its results in.
    """
    ordered = sorted(nodes, key=lambda node: node.id)
    return [list(ordered[start : start + size]) for start in range(0, len(ordered), size)]


class _Cluster:
    """One open cluster while `_cluster_by_similarity` is assigning nodes — the identical
    shape `weft_index.raptor._Cluster` keeps, rewritten here rather than imported because
    that class is private to another pack.
    """

    __slots__ = ("members", "_sum")

    def __init__(self, first: Node, vector: Sequence[float]) -> None:
        self.members: list[Node] = [first]
        self._sum: list[float] = list(vector)

    def centroid(self) -> Sequence[float]:
        return tuple(total / len(self.members) for total in self._sum)

    def add(self, node: Node, vector: Sequence[float]) -> None:
        self.members.append(node)
        self._sum = [total + component for total, component in zip(self._sum, vector, strict=True)]


def _cluster_by_similarity(
    embedded: Sequence[tuple[Node, Vector]], *, cluster_size: int, similarity_threshold: float
) -> list[list[Node]]:
    """Greedy single-pass grouping by cosine similarity to each open cluster's running
    centroid — `weft_index.raptor._cluster_by_similarity`'s own algorithm, rewritten here
    because that function is private to another pack (see the module docstring). Every
    node in `embedded` is guaranteed a vector by its own type: `run` refuses an unembedded
    hit and narrows to this shape before this is ever called.

    `embedded` is consumed in ascending `Node.id` order rather than in whatever order
    `Ranking.hits` happened to arrive in, so the result is a function of the node *set* a
    retriever handed this stage, never of the retriever's own internal ordering —
    `weft_index.raptor`'s own module docstring makes the identical argument for the
    identical reason.
    """
    ordered = sorted(embedded, key=lambda pair: pair[0].id)
    clusters: list[_Cluster] = []
    for node, vector in ordered:
        best_cluster: _Cluster | None = None
        best_similarity = float("-inf")
        for cluster in clusters:
            if len(cluster.members) >= cluster_size:
                continue
            similarity = _cosine(cluster.centroid(), vector.values)
            if similarity > best_similarity:
                best_cluster, best_similarity = cluster, similarity
        if best_cluster is not None and best_similarity >= similarity_threshold:
            best_cluster.add(node, vector.values)
        else:
            clusters.append(_Cluster(node, vector.values))
    return [cluster.members for cluster in clusters]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two same-length embeddings —
    `weft_index.raptor._cosine`'s own twin, one pack over; every pack in this tree writes
    its own rather than sharing one through the kernel, which names no capability to hang a
    shared helper off of.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _format_cluster(members: Sequence[Node], *, budget: int) -> str:
    """One cluster's members, numbered and joined into one string.

    `weft_index.raptor._format_cluster`'s own budget-sharing rule, one pipeline position
    over: `budget` is split evenly across members rather than spent first-come, so a single
    long member cannot crowd its siblings out of the summary entirely.
    """
    share = max(1, budget // max(1, len(members)))
    passages = [member.content[:share] for member in members]
    return "\n\n".join(f"{index}. {passage}" for index, passage in enumerate(passages, 1))
