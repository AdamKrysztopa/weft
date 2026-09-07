"""`raptor` — the second `Expander`. Task **2.32**.

`docs/build-ledger.md`: "a query too broad for any one chunk is answerable, because
summaries of clustered chunks are themselves retrievable nodes, and a summary that cannot
be produced degrades the tree rather than failing the run." `10` §1.2's own row: Parth
Sarthi, Salman Abdullah, Aditi Tuli, Shubh Khanna, Anna Goldie, Christopher D. Manning,
*RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*, ICLR 2024,
arXiv:2401.18059.

**Reuses 2.31's mechanism, not a second one** (`.phase2-findings.md` §11's binding rule).
`weft_index.contract.Expander`'s own docstring already names the shape a summariser takes:
"a `Chunker` *replaces*... an `Enhancer` never changes... an `Expander` does the third
thing." What differs from `hypothetical-questions` is the *build*, not the contract:
`chunk.derive(...)` gives a question one parent; a cluster summary has several, so this
plugin reaches `Node.combine(members, ...)` instead — the same classmethod
`weft_kernel.payload.node`'s own module docstring names as the fix for the RAPTOR
defect described in the next section. `weft_index.payload.Representation` is attached
exactly as `hypothetical-questions` attaches it; `weft_generate.representation.
citable_nodes` already reads the *parent count* before ever trusting the marker, so a
combine-built summary is cited as itself rather than misattributed to one of several
members — that branch was written for this task before this task existed, per its own
docstring's closing paragraph.

**The correction this task exists to prove is not still a bug.** `04` category A: RAPTOR
summaries built with `relationships={}` ("global summary: no single source document") carry
no `ref_doc_id`, so no deletion path can ever reach them — there is one class of node that no
deletion mechanism in the system can reach: delete a document and its summaries remain
retrievable forever, describing content that is gone.
`Node.combine` makes that unrepresentable rather than merely avoided: it refuses an empty
`members` sequence, and `Lineage.derived` computes `sources` as the union of the members'
own sources, so a summary's `Lineage.sources` is never authored and never empty while it
has members — cascade delete reaches it by construction, the same guarantee `hypothetical-
questions` gets from `derive` one field over.

**Clustering is a fresh, small algorithm — never UMAP+GMM soft clustering.** What it
does is greedy single-pass grouping by cosine similarity to a running centroid
(`_cluster_by_similarity`, below): assign each node to the most similar open cluster if
that similarity clears `similarity_threshold` and the cluster is not yet at
`cluster_size`, otherwise open a new one. This is a different algorithm from the paper's
soft GMM clustering — Sarthi et al.'s own contribution is *recursive abstraction over a
similarity-based hierarchy*, not a specific clustering procedure, and every worked example
in the paper's own appendix describes clusters as "similar text segments," which greedy
cosine grouping produces honestly, just not probabilistically.

**The greedy pass consumes its input sorted by `Node.id`, ascending, not in whatever order
the caller handed it over** (`_cluster_by_similarity`, task **10.3**). A single-pass
algorithm that mutates clusters in place as it walks its input is order-dependent by
construction: which cluster a node joins depends on what was already open when it arrived,
so the same seven nodes produced different groupings, and different summary content, merely
because a different extraction run happened to hand them over in a different sequence. A
node id is a content digest and needs nothing this plugin does not already hold, so sorting
by it makes the answer a function of the node *set* rather than of the run. This is not a
step toward the paper's own clusterer: all four of this plugin's source papers (GMM/EM,
k-means, an entropy-minimising partition) use order-independent clustering and simply assume
the property this sort restores — a stable ordering fixes the defect without adopting the
least-evidenced component of any of them, and the divergence from UMAP+GMM stated above still
stands.

**One level per invocation, and today that is all this plugin claims.** A summary
`Node.combine` builds carries no embedding — `Node.combine`'s own docstring says only that
its parents are explicit and never empty; it is `Node.derive`'s docstring that states the
"embedding is not carried over" rule, corrected here after `docs/lessons.md` L10.14 found the
attribution wrong. Either way, a freshly combined summary starts with no vector of its own.
`max_levels` is still not a field on this plugin: chaining levels stays the caller's job
(`Expander.run` does not loop internally), not this plugin's.

**Embedding order, corrected against the paper rather than around it (task 10.4).** RAPTOR §3
(p.3): "The chunks and their corresponding SBERT embeddings form the leaf nodes of our tree
structure," then clustering runs on those embeddings, and "[o]nce clustered, a Language Model
is used to summarize the grouped texts. These summarized texts are then re-embedded, and the
cycle of embedding, clustering, and summarization continues." And p.4, flatly: "we embed all
nodes using SBERT." Embedding is a precondition of clustering, not something this plugin
computes in order to cluster — and a summariser re-embeds only what it just wrote. Weft
shipped the inverse: this plugin embedded the whole payload itself to cluster it, returned the
original nodes unembedded, and the `embed` stage downstream embedded every leaf a second time
— a doubled bill against a paid account, disclosed nowhere. Since 10.4, every node this plugin
is handed must already carry the embedding the `embed` stage gave it — `run` refuses a payload
that does not, by name, before any clustering or any prompt — clustering spends no `Embedder`
call at all, and this plugin makes exactly one `Embedder` call of its own: on the summaries it
just wrote, in one batch, before returning (`_embed_summaries`, below). A leaf is embedded
once per ingest; a summary is embedded once, by the plugin that authored it.

An earlier version of this section argued against a plugin embedding its own output, on the
grounds that it would make one `Expander.run` silently do a variable number of `Embedder`
calls depending on how deep clustering happened to go. **That argument is withdrawn**: it was
about *internal* recursion — embedding level after level inside a single call while depth
looped internally — and a single batch call over one level's own summaries, once, is not that
shape. Nothing about depth changed here; `max_levels` is still not a field on this plugin,
chaining levels stays the caller's job.

**The input precondition, named because it is new.** No other `Expander` this pack ships
requires anything of the vectors on the nodes it is handed — `hypothetical-questions` reads
only `content` and `media_type`. This plugin is the first with a real precondition, because
clustering needs a vector to compare and cannot manufacture one honestly. That precondition
is a real cost stated in the open rather than hidden in a stage-order convention: a pipeline
document that puts `raptor` before `embed` no longer silently degrades to "no clustering
happened," it fails, naming the stage that has to move.

**A tree deeper than one level, and each level built from the one below it alone (task
10.7).** `weft_kernel.runner`'s linear runner threads each stage's whole output straight
into the next stage's payload, so a second `raptor` stage in a pipeline document receives
the *entire* cumulative node set — the original leaves plus whatever an earlier `raptor`
stage already built — not an isolated "this level's nodes." `RaptorConfig.over_level`
is how a stage tells the difference: it names the level this stage's input is drawn from,
`0` meaning the leaves, and `run` clusters only the nodes selected at that level, passing
every other node it was handed straight through unchanged. A node's level *for selection*
is `node.ext_as(RaptorFacts).level`, or `0` when it carries no `RaptorFacts` at all — which
is not the same fact a leaf *states* about itself (it states none, `RaptorFacts.level`'s own
docstring and `test_a_leaf_states_no_level_at_all`); one is what this stage looks for, the
other is what a node claims. The level a built summary states is unchanged from task 10.6:
derived from its members, never from `over_level`, so a rung over level 1 produces level 2
because its members are at level 1 — the two are deliberately uncoupled, which is what keeps
a document's own arrangement of stages free to differ from what any one stage assumes about
its position.

**The stop criterion, and it is Weft's own.** A rung builds a level only when its selected
input holds at least `min_cluster_size` nodes to cluster; below that, `run` answers
`Produced` with the payload **unchanged**, building nothing. It must answer `Produced`,
never `NothingToProduce`: `weft_kernel.runner._run_one_batch` (around lines 908-917) returns
from the *whole batch* on any outcome that is not `Produced`, so a thin rung that answered
`NothingToProduce` would take the `store` stage down with it and the corpus would never be
written — the obvious reading of `Expander`'s own contract, "a batch with nothing to expand
still answers `NothingToProduce`," points the wrong way here, because what is thin is one
level of a tree, not the whole run. The depth *ceiling* is not this plugin's at all — it is
however many `raptor` rungs an operator's document declares; the width *floor* is
`min_cluster_size`, a field an operator already sets for the ordinary one-level case. Neither
number is drawn from either paper. Chucri Alg. 1 line 4 conjoins the same **shape** — a width
condition and a depth condition together, *"while the top layer contains more than 10 nodes
and there are fewer than 5 layers"* — with both constants asserted and no ablation behind
either; RAPTOR's own rule is *"until further clustering becomes infeasible"* (§3, p.3) and is
never defined, in its body or its appendix. This module does not assert that a deeper tree
answers better — no section of this task does; task 10.13 is where that is measured.

*(This section used to say chaining `raptor` stages "does not yet build a correct deeper
tree, and this module does not claim that it does," and that building one needed
`RaptorSummarizer` "to exclude, on the way in, any node a prior `raptor` stage already
consumed — filed as future work, not shipped here." `over_level` above is that exclusion,
shipped at task 10.7.)*

**What the tree is a tree of, named rather than left to be inferred (task 10.5).** It is a tree
of **the one collection** — the store this run is configured to write to (`weft_cli.ingest`'s own
"which store a run uses decides where the corpus is") — and **not one tree per document.** That
is Chucri et al.'s scope (§4.1, a tree over the dataset) and it is a **deliberate divergence from
the paper this plugin is named after**, whose p.9 is explicit the other way: *"The RAPTOR tree is
built for each of these stories."* The divergence is the owner's, taken 2026-09-07, and it is
recorded here, in `10` §1.2's row and in `index-with-raptor.yaml` so no reader has to infer it
from behaviour.

What it costs, stated because it is a property of this rung rather than a defect hidden in it:
**this plugin performs no store read.** It clusters over the payload it was handed and nothing
else, so *the collection is expected to be indexed in one run*. Index ten documents in one `weft
index` and they share one tree; index them in two commands and the second batch **founds a second
tree** rather than joining the first, and a re-indexed document leaves its old summaries standing.
Reading the store back to avoid that is a corpus-wide revisable pass, which is `11` D2's open
question about where such a pass runs and whether its output may be durable — not this plugin's to
answer by default. Chucri §6.5 (p.9) is the only measurement of a tree over a changing corpus in
the four papers and it favours the full rebuild, which is why the incremental join is filed and
unscheduled rather than built.

*(The scope this section used to leave unsaid was not corpus-wide either. `run` receives whatever
one `weft index` invocation was handed, so the shipped behaviour was **batch-wide** — the same ten
documents in one command and in two built different trees, which is neither paper's scope and was
nobody's decision. `docs/lessons.md` L10.1.)*

**Expanding a summary to its members, and what that walk costs (task 10.8).** A summary's
`Lineage.parents` names **the level directly below it and nothing else** — that is what 10.7
builds, one rung per level — so one hop reaches that level and reaching the leaves from level
*n* costs *n* hops. RAPTOR's own traversal retrieval wants exactly that shape (immediate
children, layer by layer); T-Retriever eq. 13 wants the leaf members in a single read, which
would need the walk flattened at index time or a second field, and Weft does neither and states
the cost instead.

**The mechanism is `NodeStore.get`, on the base contract, and no filter at all.** A summary
already carries its members' ids, so the ids *are* the query — `store.get(summary.lineage.parents)`
is one call and a store implementing nothing beyond `NodeStore` can walk a tree. The plan for
this task reasoned that expansion was reachable through `MetadataFilter.matching` with `contains`
on `lineage.parents`; that is true of the **reverse** walk — *given a node, which summary stands
over it* — and unnecessary for this one. Neither route needs the dedicated store method a change
to the `2.0.0` store family would have meant, and that ⛔ is not taken.

**Measured 2026-09-07, on both proven backends**, over a two-level tree of 673 nodes (512 leaves,
128 level-1, 33 level-2), median of seven calls: expansion hop one (`get`, 4 ids) **0.37 ms** on
pgvector and **1.84 ms** on Qdrant; hop two (`get`, 16 ids) **0.56 ms** and **2.05 ms**; the
reverse walk (`matching` with `contains`, one id) **0.38 ms** and **2.66 ms**. A full walk from a
level-2 summary to its leaves is under a millisecond on pgvector and about four on Qdrant, which
is the number that decided the ⛔ rather than an argument about it.

**What a degraded run says, and the one thing it still cannot say.** Three facts used to
arrive as one result — a corpus with nothing to cluster, a corpus whose clusters were all too
loose, and a run whose every summary request failed — because each answered
`Produced(payload)`. The third now answers `Failed` naming how many clusters it summarised
none of, which is the distinction `CLAUDE.md` demands: a success path and a failure path that
cannot be told apart is exactly the defect this pack was written against. **Partial** degradation
is still invisible: an `Expander` that summarised nine of ten clusters is `Produced` and says
nothing about the tenth. Recording that count needs a channel this plugin does not have —
`Produced` is frozen with one field, and writing `span.set_attribute` from a pack would settle
by default whether the registration seam is the only emitter of telemetry, which is an open
question and not this task's to answer.

**Per-summary coverage rides on the node itself, and does not wait on that channel.** Task
**10.2**: every summary this plugin returns carries `weft_index.payload.RaptorFacts` — how
many members its cluster held, how many of them were truncated, and how many characters the
model that wrote the summary actually saw versus how many the cluster held in full. A reader
can now tell a summary built from its whole cluster apart from one built from 40% of it,
which content alone never could. The run-level count named in the paragraph above — how many
of a run's clusters degraded — is a separate fact, about the run rather than about one
summary, and stays open for task 10.10.

**The retry halves what was sent, and that is the whole point of it.** `weft_llm.retry` already
owns retrying the same request, and `LLMContextLengthError` is classed *permanent*
(`weft_llm/errors.py:160`) precisely because re-sending an overflowing prompt fails identically
forever. So the only useful second attempt is a smaller one. It halves the rendered cluster
text rather than the configured budget, because a cluster already under `max_cluster_chars`
would otherwise be re-sent byte-identical — a call that cannot succeed where the first failed.
There is no third attempt: a cluster that fails twice degrades, which is this contract's stated
posture.

**What this does not ship, named rather than left to be assumed.** `10` §1.2's own row
carries `mode: collapsed | traversal` as a *retrieval*-time distinction. `collapsed` mode —
retrieving over the whole tree, flat — needs nothing from this plugin beyond what it
already does: a summary is just another node with its own embedding in the same store, so
the existing vector-search retriever finds it exactly the way it finds a hypothetical-
question node, the identical "no new Retriever" property task 2.31 already established.
`traversal` mode — an explicit top-down descent through parent/child structure at query
time — is not implemented here: it is a distinct `Retriever` position reading `Lineage.
parents` as a tree, and naming this plugin `raptor` does not claim it, on the same footing
`10` §1.4 states for `corrective` and `boolean-retrieval`'s own conditional rows.

**Every summary now states its own level (task 10.6).** `weft_index.payload.RaptorFacts.
level` is derived from the members a summary was actually built from, never from this
stage's own position in a pipeline — see that field's docstring for why. This is the
interface task 10.7 filters on, above, to build each level from the previous level's nodes
alone.
"""

import asyncio
import math
from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_embed.contract import Embedder
from weft_index.payload import RaptorFacts, Representation
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterRequest
from weft_kernel.context import Context
from weft_kernel.payload import (
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    Vector,
)
from weft_llm.contract import LLM
from weft_prompts.contract import Prompts

#: The name this plugin is registered and selectable under — see `weft_index.register`.
NAME = "raptor"


class RaptorConfig(BaseModel):
    """`raptor`'s `with:` config. Every field has a default, per this pack's own rule that a
    Phase 2 pack's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The most members one cluster can hold before a node that would have joined it opens
    #: a new cluster instead. Not "how many clusters" — that falls out of the corpus.
    cluster_size: int = Field(default=4, ge=2)
    #: Below this many members, a cluster is left as ordinary leaves rather than summarised
    #: — a "cluster" of one node has nothing to abstract over, and summarising it would be
    #: paraphrasing, not clustering. `10` §1.2's own row promises "clustered chunks."
    min_cluster_size: int = Field(default=2, ge=2)
    #: The cosine-similarity floor a node must clear against a cluster's running centroid to
    #: join it. This field, and `cluster_size` above, exist so a clustering knob that matters
    #: is never hard-coded.
    similarity_threshold: float = Field(default=0.75, ge=-1.0, le=1.0)
    #: The most cluster text one summary request may carry. This plugin previously had no cap:
    #: `_format_cluster` joined every member whole, so a single oversized
    #: cluster could exceed a model's context and take its summary with it. A budget, shared
    #: evenly across the cluster's members, so no one member can crowd out the rest.
    max_cluster_chars: int = Field(default=12_000, ge=100)
    #: How many summaries may be in flight at once. Unbounded `asyncio.gather` over every
    #: cluster meant a 200-cluster corpus fired 200 concurrent completions at whatever
    #: provider was configured. What a provider tolerates is an operator's fact, not this
    #: plugin's, which is why it is a field rather than a constant.
    max_concurrent_summaries: int = Field(default=8, ge=1)
    prompt: str = Field(default=SUMMARIZE_CLUSTER_NAME, min_length=1)
    role: str = Field(default="index", min_length=1)
    #: The level this rung's input is drawn from — `0` meaning the leaves, which is the
    #: default and keeps `index-with-raptor` exactly what it was. A second `raptor` stage in
    #: a document sets this to the level the first one built, so it clusters that level's
    #: summaries and leaves the leaves — and any other level in the payload — untouched. See
    #: the module docstring's *"A tree deeper than one level"* section for why the runner
    #: makes this necessary rather than optional.
    over_level: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _min_cluster_size_within_cluster_size(self) -> "RaptorConfig":
        if self.min_cluster_size > self.cluster_size:
            raise ValueError(
                f"min_cluster_size ({self.min_cluster_size}) cannot exceed cluster_size "
                f"({self.cluster_size}) — no cluster could ever reach the minimum needed "
                f"to be summarised"
            )
        return self


class RaptorSummarizer:
    """Clusters the nodes at `RaptorConfig.over_level` by embedding similarity, and derives
    one summary node per cluster that clears `min_cluster_size` — every other node it was
    handed, at any other level, continues into the output untouched (task 10.7).

    Satisfies `weft_index.contract.Expander` structurally. Each derived node is
    `Node.combine(members, content=summary, media_type=MediaType.TEXT)`, so its id is its
    own content digest, its `Lineage.parents` names every clustered member, and its
    `Lineage.sources` is the union of theirs — see the module docstring's *"the correction
    this task exists to prove"* section. `Representation(technique=NAME)` is attached so a
    citation can later tell it apart from an ordinary passage — see `weft_index.payload.
    Representation`.
    """

    config_model: ClassVar[type[RaptorConfig]] = RaptorConfig

    def __init__(self, config: RaptorConfig | None = None) -> None:
        self._config = config if config is not None else RaptorConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        if not payload:
            return NothingToProduce(reason="no nodes to cluster into summaries")

        # **Selection, not the whole payload.** The linear runner threads every stage's
        # whole output into the next stage's payload (`weft_kernel.runner._run_one_batch`),
        # so a second `raptor` stage in a document receives the leaves *and* whatever an
        # earlier rung already built, in one payload. `_node_level` reads what a node
        # carries for *selection* purposes — `0` for a node with no `RaptorFacts` at all —
        # which is deliberately not the same fact `RaptorFacts.level` states about a summary
        # (a leaf states no level; see that field's own docstring). Only nodes at
        # `over_level` are candidates for this rung's clustering; everything else rides
        # through in `payload` below, untouched, so a leaf can never be re-merged with an
        # abstraction already built from it.
        selected = [node for node in payload if _node_level(node) == self._config.over_level]

        unembedded = sum(1 for node in selected if node.embedding is None)
        if unembedded:
            return Failed(
                reason=(
                    f"'{NAME}' received {unembedded} node(s) with no embedding out of "
                    f"{len(selected)} at level {self._config.over_level}. This plugin clusters "
                    f"by the vectors it is handed and no longer computes them itself, so it "
                    f"must run after the 'embed' stage, not before it — move the '{NAME}' "
                    f"stage in the pipeline document to follow 'embed' and re-run"
                )
            )

        if len(selected) < self._config.min_cluster_size:
            # **Weft's own stop criterion's width half**, and it must answer `Produced`, not
            # `NothingToProduce` — see the module docstring's *"The stop criterion, and it is
            # Weft's own"* section. `weft_kernel.runner._run_one_batch` (around lines
            # 908-917) returns from the *whole batch* on any outcome that is not `Produced`,
            # so answering `NothingToProduce` here because one level is thin would take the
            # `store` stage down with it and the corpus would never be written at all. The
            # depth ceiling is the document's, not this plugin's: it simply has nothing to
            # build at this level and says so by changing nothing.
            return Produced(value=tuple(payload))

        embedded = tuple((node, node.embedding) for node in selected if node.embedding is not None)
        clusters = _cluster_by_similarity(
            embedded,
            cluster_size=self._config.cluster_size,
            similarity_threshold=self._config.similarity_threshold,
        )
        summarizable = [
            cluster for cluster in clusters if len(cluster) >= self._config.min_cluster_size
        ]
        if not summarizable:
            # Nothing clustered tightly enough — an embedder that could not run at all was
            # already turned into `Failed` above and never reaches this branch. Every
            # original node is still the output, unchanged, before a single LLM call was
            # even attempted — the module docstring's own degrade posture, but only for the
            # genuinely per-cluster case this branch is about.
            return Produced(value=tuple(payload))

        prompts = ctx.require(Prompts)
        llm = ctx.require(LLM)
        limit = asyncio.Semaphore(self._config.max_concurrent_summaries)

        async def _bounded(cluster: Sequence[Node]) -> Node | None:
            async with limit:
                return await self._summarize(cluster, prompts=prompts, llm=llm, ctx=ctx)

        summaries = await asyncio.gather(*(_bounded(cluster) for cluster in summarizable))
        derived = tuple(summary for summary in summaries if summary is not None)
        if not derived:
            # Every cluster degraded. Answering `Produced(payload)` here would be
            # byte-identical to the "nothing clustered tightly enough" branch above, and to a
            # complete run over a corpus with nothing to summarise — three different facts
            # arriving as one result, which is exactly the trap `CLAUDE.md` names outright.
            # Degrading a cluster is this contract's posture; degrading *every* cluster is the
            # ambient service being unusable, and that is worth saying.
            return Failed(
                reason=(
                    f"'{NAME}' summarised none of its {len(summarizable)} cluster(s): every "
                    f"summary request degraded, so the tree gained no level"
                )
            )
        embedded_derived = await self._embed_summaries(derived, ctx=ctx)
        if isinstance(embedded_derived, Failed):
            return embedded_derived
        return Produced(value=(*payload, *embedded_derived.value))

    async def _embed_summaries(
        self, summaries: Sequence[Node], *, ctx: Context
    ) -> Produced[tuple[Node, ...]] | Failed:
        """`summaries`, each carrying the embedding RAPTOR §3 (p.4) requires of every node —
        *"we embed all nodes using SBERT"* — computed here rather than by the caller, because
        this is the one node type nothing downstream of this stage will ever vectorise.

        A cluster too dissimilar to summarise and an `Embedder` that could not run at all are
        different failures and must not collapse into the same result — the same distinction
        `weft_retrieve.routing.NearestDescriptionPolicy` draws at its own `Embedder.run` call
        (`routing.py`, around its `_synthetic`/`vectors` block): `Failed` propagates as this
        stage's own `Failed`, and `NothingToProduce` becomes a `Failed` naming what the
        embedder itself said, because an `Expander`'s "degrade, never fail the run" posture
        (`weft_index.contract.Expander`'s own docstring) covers a *cluster* nothing could be
        generated for, not the ambient service the whole run depends on going dark. And a
        `Produced` that still hands back a summary with no vector is the same shape by another
        route: that summary would be stored and findable by nothing, and nothing runs after
        this stage now to give it one — a silent loss, not a degradation.
        """
        embedder = ctx.require(Embedder)
        outcome = await embedder.run(summaries, ctx)
        if isinstance(outcome, Failed):
            return outcome
        if isinstance(outcome, NothingToProduce):
            return Failed(
                reason=(
                    f"'{NAME}' produced {len(summaries)} summary node(s) but the configured "
                    f"embedder returned nothing for them: {outcome.reason}"
                )
            )
        unembedded = sum(1 for node in outcome.value if node.embedding is None)
        if unembedded:
            return Failed(
                reason=(
                    f"'{NAME}': the configured embedder returned {unembedded} of "
                    f"{len(summaries)} summary node(s) with no vector — a summary stored "
                    f"without one is unretrievable, and nothing downstream of '{NAME}' will "
                    f"embed it"
                )
            )
        return Produced(value=tuple(outcome.value))

    async def _summarize(
        self, members: Sequence[Node], *, prompts: Prompts, llm: LLM, ctx: Context
    ) -> Node | None:
        """One cluster's summary node, or `None` when generation degrades — never raised.
        `_config.prompt` and `_config.role` naming nothing registered still raises: that is
        an operator's own document being wrong, the identical split `hypothetical_
        questions._questions_for`'s own docstring draws.
        """
        # The retry halves the text that was actually sent, never the configured budget. A
        # cluster already comfortably under `max_cluster_chars` would otherwise be re-sent
        # byte-identical, which is a second call that cannot succeed where the first failed —
        # and `weft_llm.retry` already owns retrying the *same* request. What this branch adds
        # is the only move retry cannot make: a smaller one.
        budget = self._config.max_cluster_chars
        characters_held = sum(len(member.content) for member in members)
        for attempt in range(2):
            passages, characters_shown, members_truncated = _format_cluster(members, budget=budget)
            if attempt == 1:
                passages, characters_shown, members_truncated = _format_cluster(
                    members, budget=max(1, len(passages) // 2)
                )
            values = SummarizeClusterRequest(passages=passages)
            rendered = await prompts.render(self._config.prompt, values, ctx)
            if not isinstance(rendered, Produced):
                return None
            completion = await llm.complete(rendered.value, role=self._config.role, ctx=ctx)
            if not isinstance(completion, Produced):
                continue
            summary = completion.value.text.strip()
            if not summary:
                continue
            member_facts = (member.ext_as(RaptorFacts) for member in members)
            member_levels = (facts.level for facts in member_facts if facts is not None)
            level = max(member_levels, default=0) + 1
            facts = RaptorFacts(
                members=len(members),
                members_truncated=members_truncated,
                characters_held=characters_held,
                characters_shown=characters_shown,
                level=level,
            )
            return (
                Node.combine(members, content=summary, media_type=MediaType.TEXT)
                .with_ext(Representation(technique=NAME))
                .with_ext(facts)
            )
        return None


def _node_level(node: Node) -> int:
    """`node`'s level *for selection* — task 10.7 — never the level a node *states* about
    itself.

    A summary states its level in `RaptorFacts.level`; a leaf carries no `RaptorFacts` at
    all and states none (`test_a_leaf_states_no_level_at_all`). This function answers `0`
    for that leaf anyway, because a rung with the default `over_level=0` has to keep
    consuming the leaves `index-with-raptor` already relies on. The two are not the same
    claim: one is what this stage looks for on its way in, the other is what a node says
    about what it is.
    """
    facts = node.ext_as(RaptorFacts)
    return facts.level if facts is not None else 0


def _format_cluster(members: Sequence[Node], *, budget: int) -> tuple[str, int, int]:
    """One cluster's members, numbered, alongside how much of them actually went in.

    `weft_retrieve.prompts.PassageGradeRequest`'s own precedent for a batch offered to a
    template: joining is the plugin's job, not the template's, because a template
    substitution has no loop of its own.

    `budget` is shared **evenly across members** rather than spent first-come. Truncating the
    join as one string would let a single long member consume the whole allowance and leave
    its siblings out of the summary entirely, which would quietly turn a cluster summary into
    a paraphrase of its longest member — a wrong answer that still looks like a summary.

    Returns the rendered text, the total length of the passages actually sent (never the
    members' own content), and how many of those members were cut short — task **10.2**'s
    `RaptorFacts`, read here rather than recomputed from a second division of the same budget
    elsewhere, so the record can never disagree with the truncation it describes.
    """
    share = max(1, budget // max(1, len(members)))
    passages = [member.content[:share] for member in members]
    text = "\n\n".join(f"{index}. {passage}" for index, passage in enumerate(passages, 1))
    characters_shown = sum(len(passage) for passage in passages)
    members_truncated = sum(
        1
        for member, passage in zip(members, passages, strict=True)
        if len(passage) < len(member.content)
    )
    return text, characters_shown, members_truncated


class _Cluster:
    """One open cluster while `_cluster_by_similarity` is assigning nodes: its members so
    far, and a running centroid kept as a component-wise sum so the mean never needs
    recomputing from scratch as members join.
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
    centroid — see the module docstring's *"Clustering is a fresh, small algorithm"*
    section for why this, and not UMAP+GMM soft clustering, is what ships here.

    `embedded` is consumed in ascending `Node.id` order rather than in whatever order the
    caller handed it over, so the greedy pass's answer is a function of the node *set*, not
    of the run's own extraction or batching order — see the module docstring's *"Clustering
    is a fresh, small algorithm"* section. Sorting up front also fixes the order each
    returned cluster's own members are in, since a member is appended the moment it is
    visited: the same key answers both, so this is the only sort this function needs.
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
    """Cosine similarity between two same-length embeddings — no store, no index, just the
    two vectors this module already has in hand. `weft_retrieve.routing`'s own `_cosine`
    takes the identical shape one field over (`Vector` in, not a bare sequence); every pack
    in this tree writes its own rather than sharing one through the kernel, which names no
    capability to hang a shared helper off of.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
