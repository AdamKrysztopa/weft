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

**What a partly degraded run says, riding on the same channel as everything else (task
10.10).** Three facts used to arrive as one result — a corpus with nothing to cluster, a
corpus whose clusters were all too loose, and a run whose every summary request failed —
because each answered `Produced(payload)`. The third now answers `Failed` naming how many
clusters it summarised none of, which is the distinction `CLAUDE.md` demands: a success path
and a failure path that cannot be told apart is exactly the defect this pack was written
against. **Partial** degradation used to be invisible the same way: an `Expander` that
summarised nine of ten clusters answered `Produced` and said nothing about the tenth. It rides
on the nodes instead — the channel task 10.2's per-summary coverage record and task 10.9's
resolved `auto` values already use — rather than waiting on a channel this plugin does not
have: `weft_index.payload.RaptorFacts.clusters_found`/`.clusters_summarised` are a run-level
pair, computed once every cluster in the run has been attempted and carried unchanged onto
every summary the run produced, because the degraded cluster is exactly the one that produces
no node to carry the count instead. A reader who finds any one summary from the run finds the
whole run's tally beside it. `02` §2's registration-seam doctrine is untouched by this: no
pack writes a span, and whether that seam is the only emitter of telemetry stays an open
question this task does not answer.

*(This section used to say the partial case "needs a channel this plugin does not have —
`Produced` is frozen with one field, and writing `span.set_attribute` from a pack would settle
by default whether the registration seam is the only emitter of telemetry, which is an open
question and not this task's to answer." The nodes were already the answer; the question about
telemetry was never this task's to open, and task 10.10 leaves it exactly as unopened as it
found it.)*

**Per-summary coverage rides on the node itself, task 10.2.** Every summary this plugin
returns carries `weft_index.payload.RaptorFacts` — how many members its cluster held, how many
of them were truncated, and how many characters the model that wrote the summary actually saw
versus how many the cluster held in full. A reader can now tell a summary built from its whole
cluster apart from one built from 40% of it, which content alone never could.

**A cluster holding a node that is not text (task 10.11) — the rule, and it is Weft's own.**
Every member is read through its `content` and nothing else: the index-form text that node's own
extractor produced. `11` §2.4 already fixes what that is per kind — a `TABLE` node carries *the
index-form serialisation*, an `IMAGE` node *the caption the document supplied, else the OCR text
beneath it* — so a summariser reading `content` is reading exactly what the pack that owns the
format decided was that node's text. The summary built over them is `MediaType.TEXT`: it is prose
*about* a table and a figure, not a table and not an image, and claiming either would make it
unreadable to every stage that routes on media type.

**No paper says this, and the docstring says so rather than borrowing authority.** The one paper
in this plugin's four that touches modality is Yasuno (arXiv:2602.00030), and it never puts a
non-text node in a summariser's view: eq. 1–3 blend a visual vector into each *chunk's* own
vector, eq. 4 clusters those chunk vectors, every parent is text, and "table" never appears as a
content type. So what a parent over mixed-modality children should contain is first principles,
and this is the cheapest true answer — which is why the five Phase 9 lines carrying a *Phase 10
note* (9.2, 9.6, 9.7, 9.11, 9.14) anticipated it.

**What the rule forbids is the expensive alternative.** Re-deriving a table from its `TableGrid`,
or re-describing a figure from its pixels, would make this plugin second-guess the extractor and
require services it has never required — a `raptor` needing a `Describer` could not run in a
pipeline that has none, which is most of them. It requires neither that nor a `BlobStore`, and a
test asserts their absence from the context before running rather than asserting it of the source.

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

**`cluster_size` and `similarity_threshold` are typed by an operator or resolved by `auto`,
never both, and `cluster_size` stays the only cluster-*size* threshold (task 10.9).** `10`
§1.2's own row and every paper in the set assert their own numbers with no sweep behind
them — T-Retriever never reports its KDE bandwidth at all, Yasuno's α = 0.7 is "empirically
optimized" and cited nowhere further. Weft's shipped `4` and `0.75` were exactly as
unevidenced, which is why `Auto` exists: an `Enum` sentinel, never a `Literal` (this
project's standing rule), whose one member a pipeline document spells `auto`. A typed value
is honoured exactly as before; `auto` is resolved **once per run, from that run's own
payload, and persisted nowhere** — computed configuration that does not survive between
runs raises no question about where a derived default should live, which is what keeps
`11` D3 unreached. `weft_index.payload.RaptorFacts.resolved_similarity_threshold` and
`.resolved_cluster_size` carry what a given run's `auto` actually resolved to, so a reader
can tell an operator's own number from one this run computed — `None` means the former.

`cluster_size: auto` answers RAPTOR §3 (p.4)'s own criterion for this quantity — "[s]hould
a local cluster's combined context ever exceed the summarization model's token threshold,
our algorithm recursively applies clustering within the cluster, ensuring that the context
remains within the token threshold" — against Weft's analogue of that threshold,
`max_cluster_chars`: how many members of *this run's own payload* fit that budget without
truncation, `max_cluster_chars // mean(len(node.content) for node in selected)`, floored at
2 because a cluster of one is not a cluster (`_resolve_cluster_size`, below).

`similarity_threshold: auto` is **Weft's own, with no paper behind it**: the 75th
percentile of the pairwise cosine similarities this run's own payload actually exhibits
(`_resolve_similarity_threshold`, below). Sampling **all** pairs rather than a subset keeps
the answer a function of the id-sorted node set the same way task 10.3 made the clusterer's
own greedy pass — never of the order the run's extraction happened to hand nodes over, and
never by `random`.

**The degeneracy check, and the criterion is measured rather than intuited.** A percentile
always clears something, so a naive `auto` would turn today's honest silence under `hash`
into confident summaries over meaningless groupings. The obvious candidate — refuse a
distribution too *narrow* to threshold — is wrong and was falsified before it was written
(`docs/lessons.md` L10.22): measured 2026-09-07 on 107 real chunks embedded both ways,
`hash` gives min/p10/median/p75/p90/max **−0.4150 / −0.1638 / −0.0028 / 0.0834 / 0.1607 /
0.4079** (spread p90−p10 **0.3245**) and `openai-embeddings` gives **0.0096 / 0.3114 /
0.4328 / 0.4948 / 0.5765 / 0.8469** (spread **0.2651**). The *meaningless* vectors are the
more spread out — `hash` produces near-orthogonal random directions, which are spread
precisely because they share no meaning — so a spread-based check passes on `hash` and
could refuse a good embedder. The criterion that actually holds is the **median observed
pairwise similarity, refused at or below zero**: where the typical pair is orthogonal or
worse there is no relationship in the vectors for a threshold to describe, and zero needs
no tuning to justify it. The refusal names the embedder and the word `auto`, and states the
remedy — configure an embedder whose vectors carry meaning, or type a `similarity_threshold`
if there is a stated claim about the corpus `auto` should not second-guess. **It applies
only when `auto` was asked to resolve**: an operator who typed a number has made that claim
already and gets today's behaviour exactly, including building nothing.

`min_cluster_size` is **not** a third `auto` field. Its own docstring already argues it from
what a cluster *is* — a cluster of one node has nothing to abstract over — which is a
constant, not a number a paper tuned per dataset; an `auto` that always resolved to 2 would
be that same constant wearing a costume. The ledger line for this task named three numbers
nothing measured; this is the correction, recorded here because a docstring is where a
reader looks for it.
"""

import asyncio
import math
import statistics
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class Auto(StrEnum):
    """The sentinel a `RaptorConfig` field takes instead of an operator-typed number, task
    **10.9**. An `Enum`, never a `Literal[...]` — this project's standing rule — with one
    member whose value is the literal string `"auto"`, so a pipeline document that omits
    `cluster_size:`/`similarity_threshold:` or writes `auto` explicitly parses to the same
    thing. See `weft_index.raptor`'s own module docstring, *"`cluster_size` and
    `similarity_threshold` are typed by an operator or resolved by `auto`"*, for what each
    field resolves to and why neither number was ever evidenced enough to keep hard-coding.
    """

    AUTO = "auto"


class RaptorConfig(BaseModel):
    """`raptor`'s `with:` config. Every field has a default, per this pack's own rule that a
    Phase 2 pack's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The most members one cluster can hold before a node that would have joined it opens
    #: a new cluster instead. Not "how many clusters" — that falls out of the corpus.
    #: Defaults to `Auto.AUTO`: resolved once per run from this run's own payload
    #: (`_resolve_cluster_size`) rather than typed, because no paper in `10` §1.2 evidences a
    #: number here either. A typed `int` is honoured exactly. The declared type carries a
    #: bare `str` alongside `int | Auto` only so a pipeline document's `cluster_size: auto` —
    #: YAML has no enum syntax, so that is a plain string by the time it reaches this model —
    #: type-checks as a constructor argument; `_parse_auto_string` below intercepts every
    #: string before this field's own validation ever sees one, so nothing downstream ever
    #: observes the `str` arm (`_resolved_cluster_size`'s own docstring narrows it back).
    cluster_size: Annotated[int, Field(ge=2)] | Auto | str = Auto.AUTO
    #: Below this many members, a cluster is left as ordinary leaves rather than summarised
    #: — a "cluster" of one node has nothing to abstract over, and summarising it would be
    #: paraphrasing, not clustering. `10` §1.2's own row promises "clustered chunks." **Not**
    #: an `auto` field: this is a constant argued from what a cluster *is*, not a number a
    #: paper tuned per dataset — see the module docstring's closing paragraph.
    min_cluster_size: int = Field(default=2, ge=2)
    #: The cosine-similarity floor a node must clear against a cluster's running centroid to
    #: join it. Defaults to `Auto.AUTO`: resolved once per run as the 75th percentile of the
    #: pairwise cosine similarities this run's own payload actually exhibits
    #: (`_resolve_similarity_threshold`) — **Weft's own criterion, with no paper behind it**.
    #: Refused, naming the embedder, when the payload's median pairwise similarity is at or
    #: below zero — see the module docstring's *"The degeneracy check"* section for why that
    #: is the measured criterion and not a spread-based one. A typed `float` is honoured
    #: exactly, including that refusal never applying to it. Carries a bare `str` in its
    #: declared type for the same reason `cluster_size` does, immediately above — see that
    #: field's own comment.
    similarity_threshold: Annotated[float, Field(ge=-1.0, le=1.0)] | Auto | str = Auto.AUTO
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

    @field_validator("cluster_size", "similarity_threshold", mode="before")
    @classmethod
    def _parse_auto_string(cls, value: object) -> object:
        """A pipeline document writes `auto` as a plain string — YAML has no enum syntax for
        it — so a bare `str` rides in each field's own declared type purely so that string
        type-checks as a constructor argument at all. This runs first and closes that gap
        for real: `Auto.AUTO`'s own value passes straight through unchanged (it is already
        an `Auto`, not a plain `str`, even though `Auto` happens to subclass `str`), the
        exact string `"auto"` becomes the sentinel itself rather than surviving as a raw
        string, and any other string is refused here rather than silently accepted by the
        permissive `str` arm the type carries — nothing past this point, and no reader of
        either field, ever sees anything but `int`/`float` or `Auto`.
        """
        if isinstance(value, str) and not isinstance(value, Auto):
            if value == Auto.AUTO.value:
                return Auto.AUTO
            raise ValueError(
                f"{value!r} is not a number and is not 'auto' either — type a number, or "
                f"write 'auto' to let this run resolve it from its own payload"
            )
        return value

    @model_validator(mode="after")
    def _min_cluster_size_within_cluster_size(self) -> "RaptorConfig":
        # Only checkable against a typed `cluster_size` — `Auto.AUTO` is not resolved until
        # `run` sees this run's own payload, so there is nothing to compare yet.
        if isinstance(self.cluster_size, int) and self.min_cluster_size > self.cluster_size:
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

        # **Refusal B, task 10.19 — an `over_level` no chain of rungs could have produced.**
        # See `_refuse_unreachable_over_level`'s own docstring for the argument; drawn this
        # early, before selection or embedding checks even run, because it is entirely about
        # the payload's own shape.
        over_level_refusal = _refuse_unreachable_over_level(
            payload, over_level=self._config.over_level
        )
        if over_level_refusal is not None:
            return over_level_refusal

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

        # **Refusal C, task 10.21 — a level a prior rung in this same run already consumed.**
        # See `_refuse_level_already_consumed`'s own docstring for the argument. Drawn here,
        # once `selected` names which nodes this rung would cluster, and before the embedding
        # and cluster-size checks below, which are about whether this rung *can* run rather
        # than whether it *should*.
        already_consumed_refusal = _refuse_level_already_consumed(
            payload, selected=selected, over_level=self._config.over_level
        )
        if already_consumed_refusal is not None:
            return already_consumed_refusal

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

        resolution = self._resolve_auto_parameters(selected, embedded)
        if isinstance(resolution, Failed):
            return resolution
        cluster_size, similarity_threshold, resolved_cluster_size, resolved_similarity_threshold = (
            resolution
        )

        clusters = _cluster_by_similarity(
            embedded,
            cluster_size=cluster_size,
            similarity_threshold=similarity_threshold,
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
                return await self._summarize(
                    cluster,
                    prompts=prompts,
                    llm=llm,
                    ctx=ctx,
                    resolved_similarity_threshold=resolved_similarity_threshold,
                    resolved_cluster_size=resolved_cluster_size,
                )

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
        # **The run-level tally, task 10.10.** Neither count is knowable inside `_summarize`,
        # which sees one cluster and never the run: `clusters_found` is the width of
        # `summarizable` and `clusters_summarised` is how many of `_bounded`'s results
        # actually came back a `Node`, so both exist only once every cluster in the run has
        # been attempted. `_summarize` builds each summary's `RaptorFacts` with a placeholder
        # pair it cannot make true on its own; this pass is what makes it true, on every
        # summary the run produced, before anything downstream ever reads one.
        derived = tuple(
            _with_run_counts(
                summary,
                clusters_found=len(summarizable),
                clusters_summarised=len(derived),
            )
            for summary in derived
        )
        embedded_derived = await self._embed_summaries(derived, ctx=ctx)
        if isinstance(embedded_derived, Failed):
            return embedded_derived
        return Produced(value=(*payload, *embedded_derived.value))

    def _resolve_auto_parameters(
        self, selected: Sequence[Node], embedded: Sequence[tuple[Node, Vector]]
    ) -> tuple[int, float, int | None, float | None] | Failed:
        """`cluster_size`/`similarity_threshold`, each either the operator's own typed value or
        this run's own `auto` resolution over `selected`/`embedded` — task **10.9** — alongside
        the resolved numbers themselves (`None` for a field the operator typed), or `Failed`
        when resolution finds a configuration that could never have produced a summary.

        See the module docstring's own *"`cluster_size` and `similarity_threshold` are typed by
        an operator or resolved by `auto`"* section for why each is derived the way it is, and
        why neither is persisted anywhere: a value computed here lives only on the
        `RaptorFacts` of the summaries `run` produces, never as configuration that must survive
        to a later run. Pulled out of `run` itself, task **10.19**, once refusing a resolved
        `cluster_size` below `min_cluster_size` gave this method a second way to fail and pushed
        `run`'s own branching over this pack's complexity ceiling.
        """
        resolved_cluster_size: int | None = None
        resolved_similarity_threshold: float | None = None
        cluster_size = _typed_cluster_size(self._config.cluster_size)
        similarity_threshold = _typed_similarity_threshold(self._config.similarity_threshold)
        if cluster_size is Auto.AUTO:
            resolved_cluster_size = _resolve_cluster_size(
                selected, max_cluster_chars=self._config.max_cluster_chars
            )
            cluster_size = resolved_cluster_size
            # **Refusal A, task 10.19 — the resolved rule must survive `auto`, or `auto` is an
            # exemption from it.** See `_refuse_cluster_size_below_minimum`'s own docstring for
            # the argument.
            cluster_size_refusal = _refuse_cluster_size_below_minimum(
                min_cluster_size=self._config.min_cluster_size,
                resolved_cluster_size=resolved_cluster_size,
            )
            if cluster_size_refusal is not None:
                return cluster_size_refusal
        if similarity_threshold is Auto.AUTO:
            threshold, median = _resolve_similarity_threshold(embedded)
            if median <= 0.0:
                # **The degeneracy check — measured, not intuited.** See the module
                # docstring's *"The degeneracy check"* section for why the criterion is the
                # median rather than the spread. Applies only here, because only here did
                # `auto` do the resolving; a typed `similarity_threshold` never reaches this
                # branch at all.
                return Failed(
                    reason=(
                        f"'{NAME}': similarity_threshold: auto could not resolve a threshold "
                        f"from this run's own embeddings — the median pairwise cosine "
                        f"similarity is {median:.4f}, at or below zero, meaning the typical "
                        f"pair here is orthogonal or worse and there is no relationship in "
                        f"these vectors for a threshold to describe. "
                        # **`[services] embed` does not apply here, and this message named it
                        # until task 10.18.** This stage is reachable only from a pipeline
                        # document, and a `--pipeline` run deliberately does not read
                        # `[services]` — `weft_cli.run_services` says so in its own words
                        # (*"On a `--pipeline` run `[services] embed` is deliberately not
                        # read"*), and `index-text.yaml`'s *"What `--pipeline` costs you"*
                        # paragraph already carried the real remedy. So the old wording sent
                        # every operator who saw it to a setting their run ignores: a loud
                        # failure naming an inert remedy, which is worse than the silence 10.9
                        # replaced, because they cannot tell their fix from one that could never
                        # work. Found by running the binary at Phase 10's close, from a
                        # directory whose `weft.toml` had already set it.
                        f"Derive this pipeline document using `weft pipeline derive` and "
                        f"`replace:` its `embed` stage with an embedder whose vectors carry "
                        f"semantic meaning, or type "
                        f"a similarity_threshold yourself if you have a stated claim about "
                        f"this corpus that auto should not second-guess"
                    )
                )
            resolved_similarity_threshold = threshold
            similarity_threshold = threshold
        return (
            cluster_size,
            similarity_threshold,
            resolved_cluster_size,
            resolved_similarity_threshold,
        )

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
        self,
        members: Sequence[Node],
        *,
        prompts: Prompts,
        llm: LLM,
        ctx: Context,
        resolved_similarity_threshold: float | None,
        resolved_cluster_size: int | None,
    ) -> Node | None:
        """One cluster's summary node, or `None` when generation degrades — never raised.
        `_config.prompt` and `_config.role` naming nothing registered still raises: that is
        an operator's own document being wrong, the identical split `hypothetical_
        questions._questions_for`'s own docstring draws.

        `resolved_similarity_threshold`/`resolved_cluster_size` are this run's own `auto`
        resolution — `None` when the operator typed the field instead — and ride onto the
        returned node's own `RaptorFacts` unchanged, task **10.9**.

        `RaptorFacts.clusters_found`/`.clusters_summarised` — task **10.10** — are run-level
        facts this one call cannot know: it sees a single cluster, never how many the run had
        or how many of them came back a summary. Left at their own default here for exactly
        that reason; `run` overwrites both with the real tally on every summary it keeps, in
        `_with_run_counts`, before anything downstream of `_summarize` ever reads one.
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
                resolved_similarity_threshold=resolved_similarity_threshold,
                resolved_cluster_size=resolved_cluster_size,
                # `clusters_found`/`clusters_summarised` left at their own default — see this
                # method's own docstring. `run` overwrites both once every cluster in the run
                # has been attempted.
            )
            return (
                Node.combine(members, content=summary, media_type=MediaType.TEXT)
                .with_ext(Representation(technique=NAME))
                .with_ext(facts)
            )
        return None


def _with_run_counts(node: Node, *, clusters_found: int, clusters_summarised: int) -> Node:
    """`node`'s own `RaptorFacts`, with `clusters_found`/`clusters_summarised` overwritten to
    this run's real tally — task **10.10**. Every node reaching here was just built by
    `_summarize`, which always attaches a `RaptorFacts` before returning one, so the `facts is
    None` branch below can never actually fire; it exists for the same reason
    `_typed_cluster_size`'s own `AssertionError` does — pyright cannot see that a summary node
    is never one without facts.
    """
    facts = node.ext_as(RaptorFacts)
    if facts is None:
        raise AssertionError(
            f"'{NAME}' derived a summary node with no RaptorFacts attached — _summarize "
            f"always attaches one before returning a node, so this should be unreachable"
        )
    return node.with_ext(
        facts.model_copy(
            update={
                "clusters_found": clusters_found,
                "clusters_summarised": clusters_summarised,
            }
        )
    )


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


def _refuse_unreachable_over_level(payload: Sequence[Node], *, over_level: int) -> Failed | None:
    """`None` when `over_level` is reachable by some chain of rungs over `payload`; `Failed`
    naming the field, the value it was given and the deepest level actually present when it
    is not — task **10.19**.

    `over_level: 5` over a payload whose deepest level is 0 is a typo, not an outcome of the
    data: no arrangement of `raptor` rungs in this run could ever reach it, however well each
    one had done. The `+ 1` is the whole point and must not be dropped —
    `over_level == deepest_present + 1` is the shipped `index-with-deep-raptor`'s own
    second-rung case, where the first rung built fewer than `min_cluster_size` summaries and
    the next rung's job is to find that level empty and pass the payload through unchanged
    (`run`'s own thin-level branch, below this call); `tests/integration/test_raptor_depth.py`
    asserts that exact shape in its own failure message. Only a gap of *more* than one is
    unreachable by any chain of rungs, so that is the line drawn here.
    """
    deepest_present = max((_node_level(node) for node in payload), default=0)
    if over_level > deepest_present + 1:
        return Failed(
            reason=(
                f"'{NAME}': over_level={over_level} is more than one level above the deepest "
                f"level actually present in this payload ({deepest_present}) — no chain of "
                f"rungs in this run could have produced it, however well each one had done"
            )
        )
    return None


def _refuse_level_already_consumed(
    payload: Sequence[Node], *, selected: Sequence[Node], over_level: int
) -> Failed | None:
    """`None` when nothing in `payload` was already built *from* a node in `selected`;
    `Failed` naming `over_level` and the level it should have consumed instead when some
    node was — task **10.21**.

    The linear runner threads every stage's whole output into the next stage's payload, so
    two `raptor` rungs sharing an `over_level` in one document both see this rung's leaves
    *and* whatever an earlier rung already built over them. Two summaries then exist over one
    cluster — one from each rung — and the store keeps both, because a summary's id is its
    own content digest and the two differ in text. A query reaching this level counts them as
    independent evidence instead of one abstraction.

    A node is that prior summary when it *carries `RaptorFacts`* and names a node from
    `selected` among its own `lineage.parents`: only a summary carries `RaptorFacts` at all,
    so keying on parents alone would fire on the very first rung of an ordinary ingest — a
    leaf chunk's own parents name the document root it was split from, and that is not a
    level anything has consumed. `_node_level` is deliberately not used for this check: it
    answers `0` for a node with no `RaptorFacts`, which cannot tell "a leaf" apart from "a
    summary that states level 0" — nothing states level 0, but the point of this rule is the
    presence of `RaptorFacts` itself, not the level it reports.
    """
    selected_ids = {node.id for node in selected}
    for node in payload:
        if node.ext_as(RaptorFacts) is None:
            continue
        if selected_ids.intersection(node.lineage.parents):
            return Failed(
                reason=(
                    f"'{NAME}': over_level={over_level} has already been consumed by an "
                    f"earlier rung in this run — a node in this payload carries RaptorFacts "
                    f"and was built from a node at level {over_level}. A second rung over the "
                    f"same level would give one cluster two independent-looking abstractions "
                    f"in the store; if this rung is meant to build the next level up, set "
                    f"over_level to {over_level + 1} instead"
                )
            )
    return None


def _refuse_cluster_size_below_minimum(
    *, min_cluster_size: int, resolved_cluster_size: int
) -> Failed | None:
    """`None` when `resolved_cluster_size` can satisfy `min_cluster_size`; `Failed` when it
    cannot — task **10.19**, the resolved twin of `RaptorConfig.
    _min_cluster_size_within_cluster_size`.

    That validator already refuses `min_cluster_size > cluster_size` when `cluster_size` is a
    typed `int`, by its own comment because `Auto.AUTO` is not resolved until `run` sees the
    payload. Now that it has been, the identical comparison against the number it actually
    resolved to must hold too — otherwise the same effective configuration is loud when typed
    and silent when reached through `auto`: every cluster capped below the minimum,
    `summarizable` permanently empty, and a `Produced` with the payload unchanged that is
    indistinguishable from an honestly-too-loose corpus.
    """
    if min_cluster_size > resolved_cluster_size:
        return Failed(
            reason=(
                f"'{NAME}': min_cluster_size ({min_cluster_size}) cannot exceed cluster_size "
                f"({resolved_cluster_size}), which cluster_size: auto resolved to for this "
                f"run — no cluster could ever reach the minimum needed to be summarised"
            )
        )
    return None


def _typed_cluster_size(value: int | Auto | str) -> int | Auto:
    """Narrows `RaptorConfig.cluster_size`'s own declared type back down to what a
    validated `RaptorConfig` instance can actually hold.

    That field carries a bare `str` in its type only so `cluster_size: "auto"` type-checks
    as a constructor argument — see the field's own comment. `RaptorConfig._parse_auto_string`
    already turns every legal string into `Auto.AUTO` and refuses every other one before a
    `RaptorConfig` instance exists at all, so the `AssertionError` below can never actually
    fire; it exists because pyright has no way to know that a validator already closed the
    gap its own declared type has to leave open.
    """
    if isinstance(value, Auto | int):
        return value
    raise AssertionError(
        f"RaptorConfig.cluster_size held a raw string ({value!r}) at run time — its own "
        f"validator should already have turned it into Auto.AUTO or refused it"
    )


def _typed_similarity_threshold(value: float | Auto | str) -> float | Auto:
    """`_typed_cluster_size`'s own twin, for `RaptorConfig.similarity_threshold`."""
    if isinstance(value, Auto | float):
        return value
    raise AssertionError(
        f"RaptorConfig.similarity_threshold held a raw string ({value!r}) at run time — its "
        f"own validator should already have turned it into Auto.AUTO or refused it"
    )


def _resolve_cluster_size(selected: Sequence[Node], *, max_cluster_chars: int) -> int:
    """`cluster_size: auto`'s resolution, task **10.9** — see the module docstring's own
    section for the argument. RAPTOR §3 (p.4)'s criterion for this quantity, restated
    against Weft's analogue of its token threshold: how many of *this run's own* selected
    nodes fit `max_cluster_chars` without truncation, floored at 2 because a cluster of one
    is not a cluster.
    """
    mean_chars = statistics.fmean(len(node.content) for node in selected)
    if mean_chars <= 0:
        return 2
    return max(2, int(max_cluster_chars // mean_chars))


def _pairwise_similarities(embedded: Sequence[tuple[Node, Vector]]) -> list[float]:
    """Every pairwise cosine similarity `embedded` exhibits, computed over the *id-sorted*
    node list so the answer is a function of the node set, never of the order this run's own
    extraction happened to hand nodes over — the same determinism task 10.3 gave
    `_cluster_by_similarity`'s own greedy pass, applied here because a run-derived default
    must not depend on arrival order either.
    """
    ordered = sorted(embedded, key=lambda pair: pair[0].id)
    values = [vector.values for _, vector in ordered]
    return [
        _cosine(values[i], values[j]) for i in range(len(values)) for j in range(i + 1, len(values))
    ]


def _resolve_similarity_threshold(embedded: Sequence[tuple[Node, Vector]]) -> tuple[float, float]:
    """`similarity_threshold: auto`'s resolution, task **10.9** — **Weft's own, with no paper
    behind it**: the 75th percentile of the pairwise cosine similarities this run's own
    payload actually exhibits. Returns that value alongside the *median* of the same
    distribution, which is the degeneracy criterion `run` checks before trusting either —
    see the module docstring's own *"The degeneracy check"* section for why the median, and
    not the spread, is what is measured.
    """
    similarities = _pairwise_similarities(embedded)
    if len(similarities) == 1:
        return similarities[0], similarities[0]
    percentile_75 = statistics.quantiles(similarities, n=4, method="inclusive")[2]
    return percentile_75, statistics.median(similarities)


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
