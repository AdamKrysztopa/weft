"""`adrap` — the `Revisable` that joins a new document into a tree `raptor` already built.

Ledger **10.14**: "a newly indexed document joins the existing tree rather than founding a
second one, and no query ever returns both the old and the new summary of one cluster."
The paper this plugin is named after is Charbel Chucri, Rami Azouz, Joachim Ott, *Recursive
Abstractive Processing for Retrieval in Dynamic Datasets*, 2024, arXiv:2410.01736, and the
algorithm is its §4 (adRAP): incrementally joining new leaves into an existing RAPTOR tree
rather than rebuilding it from scratch.

**What this plugin does not claim, stated where the name is.** That same paper's §6.5 (p.9)
measures adRAP *below* a full rebuild on two of three datasets — it "falls short by at least
3%" on context relevance and "underperforms compared to RAPTOR in the MultiHop and QASPER
datasets". So the reason to run this rung is **operational and not qualitative**: it avoids
re-summarising a whole corpus to absorb one document. Ledger 10.22 measured that avoided
cost at 61.05 s of ingest over ten PDFs. `10` §2.1 rule 4 forbids a name promising more than
its code delivers, and the honest version of this one is "cheaper to keep current", never
"better".

**Two divergences from §4, deliberate, beside the name that makes the claim.** Chucri §4.2
persists fitted UMAP and GMM instances with the tree so a new point can be projected into
the model the tree was clustered under; Weft's clusterer fits no model, so there is nothing
to persist and a centroid is recomputed instead (see below). And §6.4's greedy variant
assigns to the nearest cluster and never refits — this plugin does the same, which the paper
measures as the worse of its two variants, because the better one needs the fitted state
Weft does not have.

**Grilling session G15 settled the shape.** `weft_index.contract.Revisable`'s own docstring
carries the reasoning for why this is a separate contract from `Expander` and why the
corpus is reached through `ctx.require(NodeStore)` rather than a bespoke read path; this
module is what that contract's first (and, as of this task, only) registration does with
it.

**What `auto` means here is not what it means in `raptor`, and that is the whole reason this
plugin cannot simply call `raptor`'s own resolution functions.** In `raptor`, `auto` derives
`cluster_size`/`similarity_threshold` from the run's *own* payload — the corpus being built.
Here the payload is one newly indexed document, and a threshold derived from it would
describe that one document rather than the corpus it is joining; the run's payload is not
the tree's population. `auto` therefore means: read `RaptorFacts.resolved_similarity_
threshold`/`.resolved_cluster_size` off the existing summaries — task 10.9 stored exactly
these numbers on every summary a run produced, for exactly a reader like this one. If the
tree's own summaries disagree (built across more than one `raptor` invocation, say, with a
config change between them), the most common stored value wins; if every existing summary
carries `None` for the field, the original run typed the value itself rather than letting
`auto` resolve it, and there is nothing here to read — that is answered `Failed`, naming the
field and telling the operator to type it into this stage's own `with:` block instead.

**Nothing this plugin persists is anything but a `Node`.** A cluster's centroid is
recomputed from its stored members on every run this plugin makes (`await
store.get(summary.lineage.parents)`, then the component-wise mean of their embeddings) and
never written back anywhere. Chucri §4.2 stores fitted UMAP and GMM instances alongside the
tree it grows incrementally; Weft's clusterer fits no model at all — greedy cosine grouping
against a running centroid, the same algorithm `raptor` uses — so a cluster's entire state
is already derivable from nodes already stored. Storing a centroid as its own row would be
new persisted state with no `Node` shape and no store method to hold it; recomputing it is
free by comparison and was the finding that made this task cheap (`docs/internal/build-ledger.md`
10.14's own unblocking note).

**Write new, then delete old — `NodeSupersedable`'s own contract, not a choice this plugin
makes.** `await store.supersede(old.id, new)` is a two-step operation with no cross-backend
transaction (`weft_store.contract.NodeSupersedable`'s own docstring), and it is written that
way so an interruption leaves a duplicate a `reconcile` pass can find rather than a hole
nothing can — this plugin adds nothing to that ordering, it only calls the method.

**Ancestors, and why they cannot be left alone.** A node's id is a content digest over its
own parents' ids (`weft_kernel.payload.node._content_digest`), so replacing a level-1
summary changes an id that a level-2 summary's own `Lineage.parents` names — the level-2
summary is now describing a cluster that, by identity, no longer exists. This plugin walks
upward from every summary it just replaced, rebuilding and superseding each ancestor in
turn, until it reaches a summary nothing superseded points at any more. The walk is over a
fixed, already-fetched set of stored summaries (a tree, not a graph with cycles), so it
terminates by construction: each pass either grows the set of replaced ids or stops.

**One tree, over the collection a store holds — the same scope `raptor`'s own module
docstring settles for the tree this plugin joins.** This plugin performs exactly the reads
and writes that scope implies: it finds the tree by asking the store for every stored
summary, joins the run's own new leaves into it, and touches nothing else.
"""

import math
import statistics
from collections import Counter
from collections.abc import Sequence
from typing import Annotated, ClassVar, NamedTuple, Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from weft_index.payload import RaptorFacts, Representation
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterRequest
from weft_index.raptor import NAME as RAPTOR_NAME
from weft_index.raptor import Auto, format_cluster
from weft_kernel.context import Context
from weft_kernel.payload import (
    Failed,
    MediaType,
    Node,
    NodeId,
    NothingToProduce,
    Outcome,
    Produced,
)
from weft_llm.contract import LLM
from weft_prompts.contract import Prompts
from weft_store import MetadataFilter, NodeStore, NodeSupersedable
from weft_store.contract import Filter, FilterOp

#: The name this plugin is registered and selectable under — see `weft_index.register`.
NAME = "adrap"

#: The filter every fetch of "the tree" uses: any stored node carrying `RaptorFacts` at all,
#: leaf or summary, states no level (see that model's own docstring) so this selects exactly
#: the summaries.
_SUMMARY_FILTER = Filter(op=FilterOp.EXISTS, field="ext.weft-index-raptor.level")


@runtime_checkable
class _JoiningStore(NodeStore, NodeSupersedable, Protocol):
    """The two store capabilities `_propagate_to_ancestors` calls once `run`'s own two
    refusals have already passed: `NodeStore.get`, to re-fetch an ancestor's untouched
    members, and `NodeSupersedable.supersede`, to replace it. `run` narrows `store` to this
    type with `cast` rather than a further `isinstance` check — the two checks it already
    ran are what actually gate this, and a Protocol combining both is structural, so a store
    satisfying each half separately satisfies this by construction; this type exists only so
    a type checker sees both capabilities on the one variable it is passed as.
    """


class AdrapConfig(BaseModel):
    """`adrap`'s `with:` config — the same shape `raptor.RaptorConfig` takes for the fields
    they share, because both plugins answer the same two questions (how similar is similar
    enough, how big may a cluster grow) and neither number was ever evidenced for either
    plugin — see this module's own docstring for what `auto` reads here instead of deriving.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The cosine-similarity floor a new leaf must clear against a cluster's centroid to join
    #: it. `Auto.AUTO` reads `RaptorFacts.resolved_similarity_threshold` off the tree's own
    #: summaries rather than deriving anything from this run's payload — see the module
    #: docstring. A typed `float` is honoured exactly, the same as `RaptorConfig`'s own field.
    similarity_threshold: Annotated[float, Field(ge=-1.0, le=1.0)] | Auto | str = Auto.AUTO
    #: The most members one cluster may hold before a leaf that would have joined it rides
    #: through unassigned instead. `Auto.AUTO` reads `RaptorFacts.resolved_cluster_size` off
    #: the tree's own summaries — see the module docstring. A typed `int` is honoured exactly.
    cluster_size: Annotated[int, Field(ge=2)] | Auto | str = Auto.AUTO
    #: The most cluster text one re-summarisation request may carry — `raptor.RaptorConfig`'s
    #: own field, same default, same reason: an unbounded join could hand a model an
    #: oversized cluster the moment enough leaves accumulate against it.
    max_cluster_chars: int = Field(default=12_000, ge=100)
    #: How many re-summarisation requests may be in flight at once — `raptor.RaptorConfig`'s
    #: own field and reasoning: what a configured provider tolerates is an operator's fact,
    #: not this plugin's.
    max_concurrent_summaries: int = Field(default=8, ge=1)
    prompt: str = Field(default=SUMMARIZE_CLUSTER_NAME, min_length=1)
    role: str = Field(default="index", min_length=1)

    @field_validator("similarity_threshold", "cluster_size", mode="before")
    @classmethod
    def _parse_auto_string(cls, value: object) -> object:
        """`raptor.RaptorConfig._parse_auto_string`'s own twin, over the same two fields, for
        the same reason: a pipeline document writes `auto` as a plain string, and this is
        where that string becomes the real sentinel or is refused, before this model's own
        field validation ever sees it.
        """
        if isinstance(value, str) and not isinstance(value, Auto):
            if value == Auto.AUTO.value:
                return Auto.AUTO
            raise ValueError(
                f"{value!r} is not a number and is not 'auto' either — type a number, or "
                f"write 'auto' to let this run read it off the tree being joined"
            )
        return value


class _JoinCluster(NamedTuple):
    """One level-1 summary of the tree being joined: its stored members, and the centroid
    recomputed from their embeddings — never persisted, see the module docstring.
    """

    summary: Node
    members: tuple[Node, ...]
    centroid: tuple[float, ...]


class AdrapJoiner:
    """Satisfies `weft_index.contract.Revisable` structurally — see that contract's own
    docstring for why no marker attribute makes it declared instead.
    """

    config_model: ClassVar[type[AdrapConfig]] = AdrapConfig

    def __init__(self, config: AdrapConfig | None = None) -> None:
        self._config = config if config is not None else AdrapConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        if not payload:
            return NothingToProduce(reason="no nodes to join into an existing tree")

        store = ctx.require(NodeStore)

        # **Refuse by name, changing nothing** — `weft_store.contract.NodeSupersedable`'s own
        # docstring: "`adrap` asks the store it was handed and refuses by name when the
        # answer is no." Checked before a single read, so a run that cannot finish never
        # starts.
        if not isinstance(store, NodeSupersedable):
            return Failed(
                reason=(
                    f"'{NAME}' joins a new document by replacing a stale cluster summary in "
                    f"place, which needs a store that can supersede a node (NodeSupersedable) "
                    f"— the configured store does not implement it. Configure a store that "
                    f"satisfies it (both shipped backends do), or drop '{NAME}' from this "
                    f"pipeline and let 'raptor' found a fresh tree on the next full ingest "
                    f"instead"
                )
            )
        if not isinstance(store, MetadataFilter):
            return Failed(
                reason=(
                    f"'{NAME}' finds the tree a new document should join by matching stored "
                    f"summaries, which needs a store implementing MetadataFilter — the "
                    f"configured store does not. Configure a store that satisfies it (both "
                    f"shipped backends do)"
                )
            )

        summaries = await _fetch_all_summaries(store)
        if not summaries:
            # Building the first tree is `raptor`'s job, not this stage's — see the module
            # docstring's own "one tree" paragraph.
            return Produced(value=tuple(payload))

        # New leaves: nodes this run was handed that carry no RaptorFacts at all. A node
        # that already carries RaptorFacts is a summary — nothing in `payload` short of a
        # second `adrap`/`raptor` stage in the same document would produce one, and joining
        # a summary into another summary's cluster is not this plugin's algorithm.
        new_leaves = [node for node in payload if node.ext_as(RaptorFacts) is None]
        if not new_leaves:
            return Produced(value=tuple(payload))

        unembedded = sum(1 for node in new_leaves if node.embedding is None)
        if unembedded:
            return Failed(
                reason=(
                    f"'{NAME}' received {unembedded} newly indexed node(s) with no "
                    f"embedding out of {len(new_leaves)}. This plugin clusters by the "
                    f"vectors it is handed and computes none itself, so it must run after "
                    f"the 'embed' stage, not before it — move the '{NAME}' stage in the "
                    f"pipeline document to follow 'embed' and re-run"
                )
            )
        leaves_with_vectors = tuple(
            (leaf, leaf.embedding.values) for leaf in new_leaves if leaf.embedding is not None
        )

        resolution = self._resolve_parameters(summaries)
        if isinstance(resolution, Failed):
            return resolution
        similarity_threshold, cluster_size, resolved_similarity_threshold, resolved_cluster_size = (
            resolution
        )

        clusters = await _build_clusters(summaries, store=store)

        assignments = _assign_leaves(
            leaves_with_vectors,
            clusters=clusters,
            cluster_size=cluster_size,
            similarity_threshold=similarity_threshold,
        )
        if not assignments:
            # No leaf was similar enough to any existing cluster's centroid — it rides
            # through unassigned rather than founding a second tree beside this one; see
            # the module docstring's own note on why founding one is never this plugin's
            # move.
            return Produced(value=tuple(payload))

        prompts = ctx.require(Prompts)
        llm = ctx.require(LLM)

        # `remap` grows by one entry per successful supersession — level-1 clusters first,
        # then ancestors above them — and is both "what to rebuild an ancestor's members
        # from" and "which old id no longer stands for a current summary."
        remap: dict[NodeId, Node] = {}
        rebuilt: list[Node] = []

        for cluster in clusters:
            assigned = assignments.get(cluster.summary.id)
            if not assigned:
                continue
            new_summary = await self._summarize(
                (*cluster.members, *assigned),
                prompts=prompts,
                llm=llm,
                ctx=ctx,
                resolved_similarity_threshold=resolved_similarity_threshold,
                resolved_cluster_size=resolved_cluster_size,
            )
            if new_summary is None:
                # Degrade: the LLM call failed or returned nothing usable. The cluster's
                # old summary is left standing rather than superseded with nothing —
                # `raptor`'s own posture for a cluster that cannot be summarised, taken
                # here for the identical reason.
                continue
            await store.supersede(cluster.summary.id, new_summary)
            remap[cluster.summary.id] = new_summary
            rebuilt.append(new_summary)

        await self._propagate_to_ancestors(
            summaries,
            store=cast(_JoiningStore, store),
            prompts=prompts,
            llm=llm,
            ctx=ctx,
            remap=remap,
            rebuilt=rebuilt,
            resolved_similarity_threshold=resolved_similarity_threshold,
            resolved_cluster_size=resolved_cluster_size,
        )

        return Produced(value=(*payload, *rebuilt))

    def _resolve_parameters(
        self, summaries: Sequence[Node]
    ) -> tuple[float, int, float | None, int | None] | Failed:
        """`(similarity_threshold, cluster_size, resolved_similarity_threshold,
        resolved_cluster_size)` — each pair's first element is what this run actually uses,
        the second is what rides onto a rebuilt summary's own `RaptorFacts` (`None` for a
        field the operator typed, matching `raptor`'s own `resolved_*` convention).
        """
        resolved_similarity_threshold: float | None = None
        resolved_cluster_size: int | None = None
        similarity_threshold = _typed_similarity_threshold(self._config.similarity_threshold)
        cluster_size = _typed_cluster_size(self._config.cluster_size)
        if similarity_threshold is Auto.AUTO:
            value = _read_resolved_similarity_threshold(summaries)
            if isinstance(value, Failed):
                return value
            resolved_similarity_threshold = value
            similarity_threshold = value
        if cluster_size is Auto.AUTO:
            value = _read_resolved_cluster_size(summaries)
            if isinstance(value, Failed):
                return value
            resolved_cluster_size = value
            cluster_size = value
        return (
            similarity_threshold,
            cluster_size,
            resolved_similarity_threshold,
            resolved_cluster_size,
        )

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
        """One cluster's rebuilt summary, or `None` when generation degrades — never raised.

        The same prompt/LLM path `raptor.RaptorSummarizer._summarize` uses —
        `format_cluster` for the character budget, `Prompts.render` with `self._config.
        prompt`, `LLM.complete` with `role=self._config.role` — without that method's
        retry-on-overflow halving, which this task's brief does not ask for and which would
        be a second design choice this module was not handed.
        """
        characters_held = sum(len(member.content) for member in members)
        passages, characters_shown, members_truncated = format_cluster(
            members, budget=self._config.max_cluster_chars
        )
        values = SummarizeClusterRequest(passages=passages)
        rendered = await prompts.render(self._config.prompt, values, ctx)
        if not isinstance(rendered, Produced):
            return None
        completion = await llm.complete(rendered.value, role=self._config.role, ctx=ctx)
        if not isinstance(completion, Produced):
            return None
        summary = completion.value.text.strip()
        if not summary:
            return None
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
        )
        return (
            Node.combine(members, content=summary, media_type=MediaType.TEXT)
            .with_ext(Representation(technique=RAPTOR_NAME))
            .with_ext(facts)
        )

    async def _propagate_to_ancestors(
        self,
        summaries: Sequence[Node],
        *,
        store: _JoiningStore,
        prompts: Prompts,
        llm: LLM,
        ctx: Context,
        remap: dict[NodeId, Node],
        rebuilt: list[Node],
        resolved_similarity_threshold: float | None,
        resolved_cluster_size: int | None,
    ) -> None:
        """Rebuild and supersede every stored summary whose `lineage.parents` names an id
        `remap` just replaced, then repeat for whatever that rebuild itself just replaced —
        see the module docstring's own "Ancestors" paragraph for why this is necessary and
        why it terminates. `summaries` is the fixed set fetched once at the top of `run`;
        `remap` is mutated in place as each pass finds new ancestors to rebuild.
        """
        while True:
            changed = False
            for ancestor in summaries:
                if ancestor.id in remap:
                    # Already a level-1 cluster this run rebuilt directly, or an ancestor an
                    # earlier pass of this same loop already rebuilt — either way, its
                    # current replacement is already in `remap` and there is nothing to redo.
                    continue
                parent_ids = ancestor.lineage.parents
                if not any(parent_id in remap for parent_id in parent_ids):
                    continue
                missing_ids = [parent_id for parent_id in parent_ids if parent_id not in remap]
                fetched = await store.get(missing_ids) if missing_ids else ()
                fetched_by_id = {node.id: node for node in fetched}
                members: list[Node] = []
                complete = True
                for parent_id in parent_ids:
                    if parent_id in remap:
                        members.append(remap[parent_id])
                    elif parent_id in fetched_by_id:
                        members.append(fetched_by_id[parent_id])
                    else:
                        complete = False
                        break
                if not complete:
                    # A member this ancestor needs could not be fetched — degrade, leave
                    # this ancestor (and anything above it) untouched, same posture as a
                    # cluster whose centroid could not be recomputed.
                    continue
                new_ancestor = await self._summarize(
                    members,
                    prompts=prompts,
                    llm=llm,
                    ctx=ctx,
                    resolved_similarity_threshold=resolved_similarity_threshold,
                    resolved_cluster_size=resolved_cluster_size,
                )
                if new_ancestor is None:
                    continue
                await store.supersede(ancestor.id, new_ancestor)
                remap[ancestor.id] = new_ancestor
                rebuilt.append(new_ancestor)
                changed = True
            if not changed:
                return


async def _fetch_all_summaries(store: MetadataFilter) -> tuple[Node, ...]:
    """Every stored summary — any node carrying `RaptorFacts` — across as many pages as
    `matching` hands back. `matching`'s own contract promises pages, never order, so nothing
    here relies on the sequence beyond "everything eventually comes back."
    """
    collected: list[Node] = []
    cursor = None
    while True:
        page = await store.matching(_SUMMARY_FILTER, cursor)
        collected.extend(page.items)
        if page.next_cursor is None:
            return tuple(collected)
        cursor = page.next_cursor


async def _build_clusters(
    summaries: Sequence[Node], *, store: NodeStore
) -> tuple[_JoinCluster, ...]:
    """One `_JoinCluster` per level-1 summary whose members could be fetched and carried at
    least one embedding between them — see the module docstring's own centroid paragraph.
    A summary whose members cannot be fetched, or which carry no embeddings at all, is
    skipped rather than joined against a centroid this plugin cannot honestly compute.
    """
    clusters: list[_JoinCluster] = []
    for summary in summaries:
        facts = summary.ext_as(RaptorFacts)
        if facts is None or facts.level != 1:
            continue
        members = await store.get(summary.lineage.parents)
        if not members:
            continue
        vectors = [member.embedding.values for member in members if member.embedding is not None]
        if not vectors:
            continue
        centroid = tuple(statistics.fmean(component) for component in zip(*vectors, strict=True))
        clusters.append(_JoinCluster(summary=summary, members=tuple(members), centroid=centroid))
    return tuple(clusters)


def _assign_leaves(
    leaves_with_vectors: Sequence[tuple[Node, tuple[float, ...]]],
    *,
    clusters: Sequence[_JoinCluster],
    cluster_size: int,
    similarity_threshold: float,
) -> dict[NodeId, list[Node]]:
    """Which new leaf joins which existing cluster, keyed by that cluster's current summary
    id — the greedy "nearest centroid above threshold, cluster not yet full" rule the module
    docstring states, applied in ascending `Node.id` order over the leaves so the answer is
    a function of the node set rather than of the order this run happened to hand them over
    — `raptor._cluster_by_similarity`'s own reasoning for the identical ordering, applied
    here to assignment rather than to forming fresh clusters.

    A cluster's centroid is fixed for the whole pass (recomputed once, from its *stored*
    members — see the module docstring); only its remaining capacity is tracked live, so two
    leaves in the same run can fill one cluster without either seeing the other's vector.
    """
    assignments: dict[NodeId, list[Node]] = {}
    capacity_used: dict[NodeId, int] = {cluster.summary.id: 0 for cluster in clusters}
    for leaf, vector in sorted(leaves_with_vectors, key=lambda pair: pair[0].id):
        best: _JoinCluster | None = None
        best_similarity = float("-inf")
        for cluster in clusters:
            if len(cluster.members) + capacity_used[cluster.summary.id] >= cluster_size:
                continue
            similarity = _cosine(cluster.centroid, vector)
            if similarity > best_similarity:
                best, best_similarity = cluster, similarity
        if best is not None and best_similarity >= similarity_threshold:
            assignments.setdefault(best.summary.id, []).append(leaf)
            capacity_used[best.summary.id] += 1
    return assignments


def _read_resolved_similarity_threshold(summaries: Sequence[Node]) -> float | Failed:
    """`similarity_threshold: auto`'s resolution — see the module docstring's own `auto`
    paragraph. The most common `RaptorFacts.resolved_similarity_threshold` among the
    summaries actually found, or `Failed` when every one of them states `None`.
    """
    values = [
        facts.resolved_similarity_threshold
        for facts in (summary.ext_as(RaptorFacts) for summary in _id_sorted(summaries))
        if facts is not None and facts.resolved_similarity_threshold is not None
    ]
    if not values:
        return _auto_unreadable_failure(
            field="similarity_threshold", attr="resolved_similarity_threshold"
        )
    most_common, _ = Counter(values).most_common(1)[0]
    return most_common


def _read_resolved_cluster_size(summaries: Sequence[Node]) -> int | Failed:
    """`cluster_size: auto`'s resolution — `_read_resolved_similarity_threshold`'s own twin,
    over `RaptorFacts.resolved_cluster_size`.
    """
    values = [
        facts.resolved_cluster_size
        for facts in (summary.ext_as(RaptorFacts) for summary in _id_sorted(summaries))
        if facts is not None and facts.resolved_cluster_size is not None
    ]
    if not values:
        return _auto_unreadable_failure(field="cluster_size", attr="resolved_cluster_size")
    most_common, _ = Counter(values).most_common(1)[0]
    return most_common


def _id_sorted(summaries: Sequence[Node]) -> list[Node]:
    """`summaries`, ordered by `Node.id` — `matching`'s own contract promises pages, never
    order, so the "most common value" `Counter.most_common` picks on a tie must not depend
    on whatever order a store's pages happened to arrive in.
    """
    return sorted(summaries, key=lambda summary: summary.id)


def _auto_unreadable_failure(*, field: str, attr: str) -> Failed:
    return Failed(
        reason=(
            f"'{NAME}': {field}: auto could not read a value from the tree being joined — "
            f"every existing summary's RaptorFacts.{attr} is None, meaning the run that "
            f"built this tree typed {field} itself rather than letting auto resolve it. "
            f"Type {field} in this stage's own with: block, matching what the tree was "
            f"built with"
        )
    )


def _typed_similarity_threshold(value: float | Auto | str) -> float | Auto:
    """Narrows `AdrapConfig.similarity_threshold`'s own declared type back down to what a
    validated `AdrapConfig` instance can actually hold — `raptor._typed_similarity_
    threshold`'s own twin and its own reasoning: the bare `str` arm exists only so
    `similarity_threshold: "auto"` type-checks as a constructor argument, and `_parse_auto_
    string` above already turns every legal string into `Auto.AUTO` or refuses it before an
    `AdrapConfig` instance exists at all.
    """
    if isinstance(value, Auto | float):
        return value
    raise AssertionError(
        f"AdrapConfig.similarity_threshold held a raw string ({value!r}) at run time — its "
        f"own validator should already have turned it into Auto.AUTO or refused it"
    )


def _typed_cluster_size(value: int | Auto | str) -> int | Auto:
    """`_typed_similarity_threshold`'s own twin, for `AdrapConfig.cluster_size`."""
    if isinstance(value, Auto | int):
        return value
    raise AssertionError(
        f"AdrapConfig.cluster_size held a raw string ({value!r}) at run time — its own "
        f"validator should already have turned it into Auto.AUTO or refused it"
    )


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two same-length embeddings.

    **Its own copy rather than `raptor`'s, and that is this tree's stated pattern rather than
    an oversight.** `raptor._cosine`'s docstring already records it: `weft_retrieve.routing`
    writes a third copy of the identical seven lines, because the kernel names no capability
    to hang a shared numeric helper off and every pack writes its own. Seven lines of
    arithmetic with a fixed definition cannot drift into disagreeing about what cosine
    similarity is, which is exactly why duplicating *this* is cheap where duplicating
    `format_cluster` — whose truncation `RaptorFacts` records as a divergence from the paper
    — is not, and that one is shared from `raptor` instead.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
