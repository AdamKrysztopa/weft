"""Fusers — the arity-reducing position, and the label every fuser weights on.

Task **2.7**, `docs/build-ledger.md`: "fusion and reranking are composable plugins a third
party can retune, not a fixed ladder." A fixed ladder risks exactly the failure this design
avoids: one algorithm reimplemented at each call site that needs it, every copy carrying its
own hardcoded top-k values and dead configuration, because fusion was something a strategy
did rather than a position a document fills. A capability that arrives after the mechanism
that would host it does not arrive is how that duplication happens — a second call site that
needs fusion writes its own rather than waiting for a shared position to exist. So fusion is
a `Fuser` here, and the only thing a pipeline document says
about it is which registered name fills the `fuse:` position and what goes in its `with:`
block.

**`single-list` is the null fuser, and it ships in this task because the baseline needs a
`fuse` position it can fill honestly.** `.phase2-design.md` §4: the V3 baseline document
*shows* where fusion goes — a document with a `fuse` stage in it is what makes the fan-out
pipeline of ledger 2.18 a one-line delta (`use: single-list` → `use: reciprocal-rank-fusion`)
rather than a new document with a new stage. That one-line delta is requirement 6's second
clause in the only form it can be checked in.

**`single-list` merges nothing, on purpose — that is `reciprocal-rank-fusion`'s job, built
below.** `contributor_label` is written above the null case rather than beside the real one
so that this plugin's `contributors` tuple and `ReciprocalRankFusion`'s `weights` mapping are
keyed on **one** spelling rather than on two written a task apart — preventing the
divergent-copies failure at the point a second implementation would otherwise invent its
own key. Fusion also never collapses a ranking to its parents: when one
chunk is indexed as several derived nodes (`.phase2-findings.md` §11), the several are
genuinely several hits and a fuser has no business deciding they are one. That is ledger
2.33's own named stage with its own stated policy, and it is a `Reranker` — `Stage[Ranking,
Ranking]`, so it composes after any fuser and before any packer with no new type, in a
document, exactly like every other rung of the non-ladder.

**`ext` crosses the arity reduction.** A `Candidates.ext` a transform attached under its own
namespace is copied onto the `Ranking`. `.phase2-design.md` §2 makes `ext` the settled answer
to "a strategy needs to pass something along" — the direct response to `01` → Phase 2's
"re-open G5 only if a strategy cannot express what it needs to pass along" — and a fuser that
dropped it would make that answer false at the one seam every query path crosses, which is
the trigger to stop and re-open G5 rather than a detail. What does *not* cross is per-query
attribution: `weft_retrieve.payload`'s own module docstring states that narrowing, and this
module holds to it — `contributors` names which retriever and which arm fed the fusion, never
which query found which hit.

**`reciprocal-rank-fusion` — ledger 2.18, and the one implementation that serves both
hybrid retrieval and query fan-out.** `weft_retrieve.contract.Fuser`'s own docstring states
the claim structurally: "hybrid retrieval and query fan-out are the same shape here, because
multiplicity is uniform in `Candidates`." `ReciprocalRankFusion.run` (below) is what makes
that true rather than merely typed — it walks `payload.lists` once, accumulates every hit by
`Node.id` under `contributor_label(ranked)`, and never asks *why* there is more than one
list. Two lists from `vector-top-k` searched on two channels for one query (hybrid) and two
lists from `vector-top-k` searched on one channel for two `multi-query`-derived queries
(fan-out) are indistinguishable to this method — deliberately, since two call sites each
growing their own copy of the same formula because fusion was reached from two different
places rather than through one resolvable position is exactly the failure this position
exists to close off.

Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher, *Reciprocal rank fusion outperforms
condorcet and individual rank learning methods*, SIGIR 2009, pp. 758-759,
DOI 10.1145/1571941.1572114 — the formula itself, `score(d) = Σ 1/(k + rank(d))` over every
list `d` appears in, `k=60` the paper's own constant and this plugin's own default, never
hardcoded into the arithmetic itself (`10` §1.1's own row on this technique). Edward A. Fox,
Joseph A. Shaw, *Combination of Multiple Searches*, TREC-2, NIST SP 500-215, 1994, p. 243 —
the earlier combination-of-ranks idea RRF is a response to, cited on the same row and named
here for the same reason `Hyde`
and `StepBack` name what they diverge from rather than leaving it for a reader to find.

**`Ranking.contributors` is the *distinct* set of labels that fed the fusion, not one entry
per list.** Sixteen lists from an eight-query, two-channel fan-out (`.phase2-design.md`'s own
worked example) carry only two distinct labels — `vector-top-k:vector` and
`vector-top-k:text` — and a `contributors` tuple with sixteen entries, fourteen of them
repeats, would say nothing sixteen `RankedList`s did not already say. Recorded as this
module's own decision, because `weft_retrieve.payload`'s own docstring for the field says only
"which retriever and which channel fed the fusion," not how many times each is allowed to
appear.

**A document is found by more than one list is decided by `Node.id`, never by content
equality.** Two `Passage`s wrapping the same `Node` compare unequal whenever their scores
differ (`Scored` carries no identity of its own), so summing by content or by `Passage`
equality would double-count nothing and dedupe nothing reliably. `Node.id` is the
content-addressed identity `weft_kernel.payload.node`'s own module already publishes for
exactly this purpose, reused rather than restated.

**The best-ranked contributing list names `retrieved_by`, and its own `Passage.node` supplies
the fused hit's identity.** A document found at rank 0 by one list and rank 4 by another was,
in the plainest sense, *found* by the first — ties keep whichever list this method reaches
first, which is deterministic because `payload.lists` and each list's own `hits` are ordered
tuples, never a set.

**`boolean-combine` — ledger 2.23, and the second half of the technique `weft_retrieve.
boolean` ships the first half of.** Where `ReciprocalRankFusion` decides *how much* a document
counts by summing reciprocal ranks, `BooleanCombine` decides *whether* a document counts at
all, by set algebra over `Node.id`: `and` intersects, `or` unions, `not` subtracts — never a
weighted score, because Manning's own model (Ch. 1, cited on `weft_retrieve.boolean`'s own
module docstring) has no notion of "how much" a document matches a Boolean query, only whether
it does. `requires = (BooleanPlan,)` is what lets `weft_kernel.runner.Runner.resolve` refuse
this plugin a document that never ran `boolean-retrieval` first, before either plugin sees a
query — `tests/unit/weft_retrieve/test_init.py`'s own resolution test drives that refusal
directly.

**A known defect, and why nothing here special-cases it.** `10` §1.1's row: "`AND`
returns the union when the intersection is empty … the logical opposite of what was asked."
`_evaluate` below never contains that special case — a `set` intersection that happens to be
empty simply *is* the empty set, and no line of this module reaches for `or`'s union as a
rescue. `on_empty_conjunction` (`EmptyConjunction` — `report` or `fail`, **no `union` member**,
the omission stated rather than merely true by absence) governs only *whether the caller is
told*, never *what the answer is*: scoped to the case where the whole parsed query's own root
combinator is `and` and its evaluated result is empty, since that is the shape a flat
`(operator, list[str])` representation could only ever represent one of anyway — a query
whose root is `or`
and comes back empty because every branch did is an ordinary empty result, not the specific
"a conjunction was asked and nothing satisfied it" fact this knob exists to surface.

**`not` is only evaluated inside an `and`, and refused everywhere else, by name.** Manning's
own Boolean model answers "not x" against the whole indexed corpus; this plugin only ever sees
what was *positively* retrieved, so it has no bounded universe to complement against — "and not
x" (subtract `x`'s ids from the rest) is well-defined without one, and nothing else here is.
`weft_retrieve.boolean`'s own module docstring records this as the deliberate split between
what the grammar accepts (`not` anywhere a primary is legal) and what evaluation can actually
answer.

**Leaf attribution is keyed off `BooleanPlan.producer`, never off `weft_retrieve.boolean.NAME`
hardcoded here.** `requires = (BooleanPlan,)` / `provides = (BooleanPlan,)` resolves for *any*
plugin that provides `BooleanPlan`, not only the built-in `boolean-retrieval` — that is the
whole point of stating the dependency on a type rather than on a name. A `_leaf_index` that
matched a literal `"boolean-retrieval#"` string regardless of what `BooleanPlan` actually said
would make that composability false at run time: a second, honestly-implemented
`QueryTransform` that stamps `produced_by` with its own registered name would resolve cleanly
and then have every one of its lists silently unattributed. `_group_by_leaf` reads the prefix
to match from `plan.producer` instead, and `run` fails loudly, naming the mismatch, if a
`BooleanPlan` arrives but not one retrieved list can be attributed to any of its leaves —
the same "unknown name fails loudly" rule applied to provenance instead of a plugin name.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Failed, NodeId, Outcome, Produced
from weft_retrieve.boolean import NAME as BOOLEAN_RETRIEVAL_NAME
from weft_retrieve.boolean import BooleanPlan, BoolExpr, BoolOp, leaves
from weft_retrieve.payload import Candidates, Passage, RankedList, Ranking
from weft_store.contract import Scored

#: The name this fuser is registered and selectable under — see `weft_retrieve.register`.
NAME = "single-list"

#: What `reciprocal-rank-fusion` (ledger 2.18) will name its `weights` keys, and what
#: `Ranking.contributors` holds. One constant rather than two `f"{a}:{b}"` expressions in two
#: modules, because the failure of the second spelling is silent: a weight keyed
#: `"hybrid/text"` against a contributor labelled `"hybrid:text"` simply never applies.
_LABEL_SEPARATOR = ":"


def contributor_label(ranked: RankedList) -> str:
    """`retriever:channel`, or the bare retriever name when the arm is unstated.

    `RankedList.channel` is `""` when a retriever draws no distinction between arms — an
    absence, per that field's own docstring, and not a third arm. Labelling it
    `"no-retrieval:"` would put a separator in front of nothing and give an operator reading a
    span a key they cannot type; the bare name is what they would write.
    """
    if not ranked.channel:
        return ranked.retriever
    return f"{ranked.retriever}{_LABEL_SEPARATOR}{ranked.channel}"


class SingleList:
    """Unwraps one list, passes nothing through two. Satisfies `contract.Fuser` structurally.

    No `config_model`: there is nothing here to tune. A `top_k` on this plugin would be a
    second place to truncate a list the retriever already truncated, and the `10` §2.1 rule
    this pack follows is that a knob invented to satisfy requirement 6 is worse than saying
    there is none — `no-retrieval` said the same thing one contract earlier.

    `cost_bound = (0, 0)` is checked by what `run` resolves: nothing. This class never calls
    `ctx.require`, and the parameter is deleted on the first line of the method body.
    """

    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: object = None) -> None:
        del config  # nothing here is configurable — see the class docstring

    async def run(self, payload: Candidates, ctx: Context) -> Outcome[Ranking]:
        """One list unwrapped, no lists reduced to an empty `Ranking`, two or more refused.

        **Two or more is a refusal, not a choice.** Concatenating them, taking the first and
        interleaving them are three different answers to "which of these is more relevant",
        and every one of them is a fusion algorithm this plugin does not implement. Picking
        one silently is the failure `CLAUDE.md` names outright — "a silent fallback is worse
        than a failure" — and it is precisely how a hidden ranking policy ends up inside a
        stage whose name says it has none. The refusal states how many lists arrived and names
        `reciprocal-rank-fusion`, so an operator's fix is a one-word edit to the `use:` line
        of the document they already have open.

        **No lists at all is not a refusal**, because it is `no-retrieval`'s own legitimate
        output: `Candidates(lists=())` means nothing was ever asked. The emptiness rule on
        every contract in `weft_retrieve.contract` applies — `Produced` carrying an empty
        `Ranking`, never `NothingToProduce`, which would stop the pipeline and leave a caller
        with no `Answer` at all where `09` §4's V2 requires "not in this corpus".
        """
        del ctx
        if not payload.lists:
            return Produced(value=Ranking(origin=payload.origin, ext=payload.ext))
        # Unpacked rather than indexed: `payload.lists` is a `tuple[RankedList, ...]`, and a
        # type checker reading `lists[0]` after a `len(...)` comparison cannot see that the
        # empty case already returned. The unpacking says the same thing in a shape it can.
        only, *rest = payload.lists
        if rest:
            labels = ", ".join(contributor_label(ranked) for ranked in payload.lists)
            return Failed(
                reason=(
                    f"'{NAME}' fuses nothing and was handed {len(payload.lists)} lists "
                    f"({labels}). Which of them ranks higher is a fusion policy this plugin "
                    f"does not have. Use 'reciprocal-rank-fusion' in this pipeline's fuse "
                    f"stage, or retrieve one list."
                )
            )
        return Produced(
            value=Ranking(
                origin=payload.origin,
                hits=only.hits,
                contributors=(contributor_label(only),),
                ext=payload.ext,
            )
        )


#: The name this fuser is registered and selectable under — see `weft_retrieve.register`.
RRF_NAME = "reciprocal-rank-fusion"


class ReciprocalRankFusionConfig(BaseModel):
    """`ReciprocalRankFusion`'s `with:` config. Every field has a default, per this pack's own
    rule — and per ledger 2.18's own line, which names every knob this technique has as
    configuration: the constant, the per-arm weight and the truncation, none of them written
    into `run`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Cormack, Clarke & Büttcher's own constant — SIGIR 2009, cited in full on the class
    #: below. `60` is the paper's own value, carried forward as a default an operator retunes
    #: rather than a number the arithmetic assumes.
    k: int = Field(default=60, ge=1)
    #: Per-contributor weight, keyed on `contributor_label` — the identical spelling
    #: `Ranking.contributors` uses, so a document's `weights` block cannot name a key this
    #: fuser never produces without an operator noticing the mismatch immediately: an unweighted
    #: contributor still fuses, at the implicit weight of `1.0`.
    weights: Mapping[str, float] = Field(default_factory=dict)
    #: Truncate the fused ranking to its top entries, or keep all of them. Distinct from any
    #: retriever's own `top_k`: that one bounds how much evidence reaches this stage: this one
    #: bounds how much survives it.
    top_k: int | None = None


class ReciprocalRankFusion:
    """Merges k ranked lists into one by Cormack, Clarke & Büttcher's reciprocal rank fusion.
    Satisfies `weft_retrieve.contract.Fuser` structurally.

    Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher, *Reciprocal rank fusion
    outperforms condorcet and individual rank learning methods*, SIGIR 2009, pp. 758-759,
    DOI 10.1145/1571941.1572114 — `score(d) = Σ 1/(k + rank(d))`, summed over every list `d`
    appears in, weighted per contributor. Edward A. Fox, Joseph A. Shaw, *Combination of
    Multiple Searches*, TREC-2, NIST SP 500-215, 1994, p. 243 — the earlier combination
    method RRF answers, cited on the module docstring's own row in `10` §1.1.

    **The one implementation ledger 2.18 asks for.** See the module docstring's own paragraph
    on this class: nothing here asks whether a list arrived from a second retrieval arm on the
    same query or from the same arm on a `multi-query`-derived one — both are simply "another
    list this document was found in, at this rank, under this label."

    `cost_bound = (0, 0)`: pure computation over what already arrived. `run` resolves no
    service and calls no model.
    """

    config_model: ClassVar[type[ReciprocalRankFusionConfig]] = ReciprocalRankFusionConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: ReciprocalRankFusionConfig | None = None) -> None:
        self._config = config if config is not None else ReciprocalRankFusionConfig()

    async def run(self, payload: Candidates, ctx: Context) -> Outcome[Ranking]:
        """Every hit in every list, scored once per list it appears in and summed, ordered by
        the total, truncated to `top_k`.

        **The emptiness rule** — no lists at all fuses to an empty `Ranking`, the identical
        case `SingleList.run` handles above, for the identical reason: `no-retrieval`'s own
        legitimate output must never become `NothingToProduce` and stop the pipeline.
        """
        del ctx
        if not payload.lists:
            return Produced(value=Ranking(origin=payload.origin, ext=payload.ext))

        scores: dict[NodeId, float] = {}
        best_rank: dict[NodeId, int] = {}
        best_passage: dict[NodeId, Passage] = {}
        best_label: dict[NodeId, str] = {}
        for ranked in payload.lists:
            label = contributor_label(ranked)
            weight = self._config.weights.get(label, 1.0)
            for rank, passage in enumerate(ranked.hits):
                node_id = passage.node.id
                scores[node_id] = scores.get(node_id, 0.0) + weight / (self._config.k + rank + 1)
                if node_id not in best_rank or rank < best_rank[node_id]:
                    best_rank[node_id] = rank
                    best_passage[node_id] = passage
                    best_label[node_id] = label

        ordered = sorted(scores, key=lambda node_id: -scores[node_id])
        if self._config.top_k is not None:
            ordered = ordered[: self._config.top_k]
        hits = tuple(
            Passage(
                scored=Scored(value=best_passage[node_id].node, score=scores[node_id]),
                rank=rank,
                retrieved_by=best_label[node_id],
            )
            for rank, node_id in enumerate(ordered)
        )
        # The *distinct* labels that fed the fusion, order-preserved on first appearance —
        # see the module docstring's own paragraph on why this is not one entry per list.
        contributors = tuple(dict.fromkeys(contributor_label(ranked) for ranked in payload.lists))
        return Produced(
            value=Ranking(
                origin=payload.origin, hits=hits, contributors=contributors, ext=payload.ext
            )
        )


#: The name this fuser is registered and selectable under — see `weft_retrieve.register`.
BOOLEAN_COMBINE_NAME = "boolean-combine"


class EmptyConjunction(StrEnum):
    """What `BooleanCombine` does when the whole query's own root `and` matches nothing.

    Deliberately **no `union` member** — see the module docstring's own paragraph on this
    plugin for the defect that omission closes. `report` keeps the pipeline going with
    an honestly empty `Ranking`; `fail` is for a caller who would rather the run stop than
    answer a Boolean query with no evidence at all.
    """

    REPORT = "report"
    FAIL = "fail"


class BooleanCombineConfig(BaseModel):
    """`BooleanCombine`'s `with:` config. Every field has a default, per this pack's own
    rule that a Phase 2 pack's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    on_empty_conjunction: EmptyConjunction = EmptyConjunction.REPORT


class BooleanCombine:
    """Evaluates a parsed `BoolExpr` against retrieved candidates by set algebra over
    `Node.id`. Satisfies `weft_retrieve.contract.Fuser` structurally.

    `requires = (BooleanPlan,)` — see the module docstring's own paragraph on this plugin for
    what that buys at resolution.

    `cost_bound = (0, 0)`: pure computation over what already arrived, exactly like
    `SingleList` and `ReciprocalRankFusion` above. `run` resolves no service and calls no
    model.
    """

    config_model: ClassVar[type[BooleanCombineConfig]] = BooleanCombineConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)
    requires: ClassVar[tuple[type[ExtModel], ...]] = (BooleanPlan,)

    def __init__(self, config: BooleanCombineConfig | None = None) -> None:
        self._config = config if config is not None else BooleanCombineConfig()

    async def run(self, payload: Candidates, ctx: Context) -> Outcome[Ranking]:
        """`payload.lists`, combined by `payload.ext`'s own `BooleanPlan` — or a `Failed`
        naming why the tree could not be evaluated against what was retrieved.

        `weft_kernel.runner.Runner.resolve` refuses a document that reaches this stage
        without `boolean-retrieval` (or another `provides = (BooleanPlan,)` plugin) ahead of
        it — `requires`, above — but that check is static, over a document's declared stage
        order, and says nothing about whether the *instance* actually arrived on this
        `Candidates.ext` at run time. This defends the same fact defensively, the same
        "unknown name fails loudly" rule applied to a missing extension rather than a missing
        plugin name, naming the pack that would attach it rather than raising a bare
        `KeyError`.
        """
        del ctx
        plan = payload.ext.get(BooleanPlan.__namespace__)
        if not isinstance(plan, BooleanPlan):
            found = "nothing" if plan is None else type(plan).__name__
            return Failed(
                reason=(
                    f"'{BOOLEAN_COMBINE_NAME}' needs a BooleanPlan on Candidates.ext, "
                    f"attached by '{BOOLEAN_RETRIEVAL_NAME}' (or another "
                    f"'provides = (BooleanPlan,)' plugin) upstream and carried forward by "
                    f"the retriever between them; found {found} under namespace "
                    f"'{BooleanPlan.__namespace__}'."
                )
            )

        leaf_prefix = f"{plan.producer}#"
        leaf_ids, leaf_passages = _group_by_leaf(payload.lists, leaf_prefix)
        expected_leaves = frozenset(
            leaf.leaf_index for leaf in leaves(plan.expr) if leaf.leaf_index is not None
        )
        if payload.lists and not (expected_leaves & leaf_ids.keys()):
            return Failed(
                reason=(
                    f"'{BOOLEAN_COMBINE_NAME}' found a BooleanPlan produced by "
                    f"'{plan.producer}' but could not attribute any of the "
                    f"{len(payload.lists)} retrieved list(s) to any of its "
                    f"{len(expected_leaves)} leaves. Every 'Query' this producer derives must "
                    f"stamp 'produced_by' as '{leaf_prefix}<leaf_index>' — check that "
                    f"'{plan.producer}' does, the way 'boolean-retrieval' does."
                )
            )
        result = _evaluate(plan.expr, leaf_ids, leaf_passages)
        if isinstance(result, Failed):
            return result
        ids, passages = result
        contributors = tuple(dict.fromkeys(contributor_label(ranked) for ranked in payload.lists))

        if plan.expr.op is BoolOp.AND and not ids:
            note = (
                f"the conjunction {_describe(plan.expr)} matched no document in common — "
                f"each operand retrieved something on its own, but the intersection is empty."
            )
            if self._config.on_empty_conjunction is EmptyConjunction.FAIL:
                return Failed(reason=note)
            return Produced(
                value=Ranking(
                    origin=payload.origin, contributors=contributors, note=note, ext=payload.ext
                )
            )

        ordered = sorted(ids, key=lambda node_id: -passages[node_id].score)
        hits = tuple(
            Passage(
                scored=passages[node_id].scored,
                rank=rank,
                retrieved_by=passages[node_id].retrieved_by,
            )
            for rank, node_id in enumerate(ordered)
        )
        return Produced(
            value=Ranking(
                origin=payload.origin, hits=hits, contributors=contributors, ext=payload.ext
            )
        )


def _group_by_leaf(
    lists: tuple[RankedList, ...], leaf_prefix: str
) -> tuple[dict[int, frozenset[NodeId]], dict[int, dict[NodeId, Passage]]]:
    """Every retrieved hit, grouped by which `BoolExpr` leaf it answers — read off
    `RankedList.query.produced_by`, matched against `leaf_prefix` (`f"{plan.producer}#"`, the
    caller's own `BooleanPlan.producer`), never against a name hardcoded in this module. A
    `RankedList` whose query does not carry that prefix (a stray list from some other transform
    sharing this `Candidates`, or one whose producer really did use a different prefix)
    contributes nothing here rather than raising: what to do with evidence this plugin cannot
    attribute to a leaf is a decision for whoever composed the document this way, not a fact
    `boolean-combine` can name on its own — `BooleanCombine.run`'s own defensive check is what
    catches the case where *nothing at all* could be attributed, which usually means the
    producer's own name and its `produced_by` stamp disagree.
    """
    ids: dict[int, set[NodeId]] = {}
    passages: dict[int, dict[NodeId, Passage]] = {}
    for ranked in lists:
        leaf_index = _leaf_index(ranked.query.produced_by, leaf_prefix)
        if leaf_index is None:
            continue
        seen = ids.setdefault(leaf_index, set())
        stored = passages.setdefault(leaf_index, {})
        for passage in ranked.hits:
            node_id = passage.node.id
            seen.add(node_id)
            if node_id not in stored or passage.score > stored[node_id].score:
                stored[node_id] = passage
    return {index: frozenset(found) for index, found in ids.items()}, passages


def _leaf_index(produced_by: str, leaf_prefix: str) -> int | None:
    if not produced_by.startswith(leaf_prefix):
        return None
    try:
        return int(produced_by[len(leaf_prefix) :])
    except ValueError:
        return None


#: What one node of the tree evaluates to: the `Node.id`s it matches and the `Passage` each
#: one is reported through, or a `Failed` naming why this node could not be evaluated.
_Evaluated = tuple[frozenset[NodeId], dict[NodeId, Passage]] | Failed


def _evaluate(
    expr: BoolExpr,
    leaf_ids: dict[int, frozenset[NodeId]],
    leaf_passages: dict[int, dict[NodeId, Passage]],
) -> _Evaluated:
    """`expr`, evaluated to what it matches — one small dispatch, three real branches below.

    **`not`, reached here directly, is always refused.** `_evaluate_and` never calls this
    function on a `not` clause for its own combined result — it reaches inside a `not`
    clause's single operand instead, which is the one place a `not` result is actually used
    (see that function's own docstring). Reaching this branch means `not` was the whole query,
    or nested under another `not` or under `or`, none of which has a bounded universe to
    complement against.
    """
    if expr.op is BoolOp.TERM:
        index = expr.leaf_index
        if index is None:
            return Failed(reason=f"'{BOOLEAN_COMBINE_NAME}' found an unindexed leaf; this is a bug")
        return leaf_ids.get(index, frozenset()), leaf_passages.get(index, {})
    if expr.op is BoolOp.AND:
        return _evaluate_and(expr, leaf_ids, leaf_passages)
    if expr.op is BoolOp.OR:
        return _evaluate_or(expr, leaf_ids, leaf_passages)
    return Failed(
        reason=(
            f"'{BOOLEAN_COMBINE_NAME}' cannot evaluate 'not' on its own — an unbounded "
            f"corpus-wide negation is not something a retrieval index can answer. Wrap it "
            f"inside an 'and' with at least one positive operand."
        )
    )


def _evaluate_and(
    expr: BoolExpr,
    leaf_ids: dict[int, frozenset[NodeId]],
    leaf_passages: dict[int, dict[NodeId, Passage]],
) -> _Evaluated:
    """Intersects every non-`not` clause's ids, then subtracts every `not` clause's — "and not
    x" is a set difference, well-defined without a corpus to complement against.

    Passages for the surviving ids are read from the *first* positive clause alone, the same
    deterministic tie-break `ReciprocalRankFusion`'s own docstring states for "whichever list
    this method reaches first" — every surviving id is, by construction of the intersection,
    present in every positive clause's own passage map, so any one of them is as true as another.
    """
    positive = tuple(clause for clause in expr.clauses if clause.op is not BoolOp.NOT)
    negative = tuple(clause for clause in expr.clauses if clause.op is BoolOp.NOT)
    if not positive:
        return Failed(
            reason=(
                f"'{BOOLEAN_COMBINE_NAME}' cannot evaluate an 'and' whose every operand is "
                f"negated — there is nothing positively retrieved to subtract from."
            )
        )
    resolved: list[tuple[frozenset[NodeId], dict[NodeId, Passage]]] = []
    for clause in positive:
        one = _evaluate(clause, leaf_ids, leaf_passages)
        if isinstance(one, Failed):
            return one
        resolved.append(one)
    ids = resolved[0][0]
    for other_ids, _ in resolved[1:]:
        ids = ids & other_ids
    for clause in negative:
        subtracted = _evaluate(clause.clauses[0], leaf_ids, leaf_passages)
        if isinstance(subtracted, Failed):
            return subtracted
        ids = ids - subtracted[0]
    passages = {node_id: resolved[0][1][node_id] for node_id in ids}
    return frozenset(ids), passages


def _evaluate_or(
    expr: BoolExpr,
    leaf_ids: dict[int, frozenset[NodeId]],
    leaf_passages: dict[int, dict[NodeId, Passage]],
) -> _Evaluated:
    """Unions every clause's ids; a `not` as a *direct* child is refused — the module
    docstring's own paragraph on this plugin states why `and` can answer "and not x" and `or`
    cannot answer "or not x" the same way.
    """
    if any(clause.op is BoolOp.NOT for clause in expr.clauses):
        return Failed(
            reason=(
                f"'{BOOLEAN_COMBINE_NAME}' cannot evaluate 'not' as a direct operand of "
                f"'or' — 'not' only has a bounded meaning inside an 'and', where it "
                f"subtracts from what was positively retrieved; an 'or' branch has no "
                f"corpus-wide universe to complement against. Move 'not' inside an 'and'."
            )
        )
    resolved: list[tuple[frozenset[NodeId], dict[NodeId, Passage]]] = []
    for clause in expr.clauses:
        one = _evaluate(clause, leaf_ids, leaf_passages)
        if isinstance(one, Failed):
            return one
        resolved.append(one)
    ids: set[NodeId] = set()
    passages: dict[NodeId, Passage] = {}
    for other_ids, other_passages in resolved:
        ids |= other_ids
        for node_id, passage in other_passages.items():
            if node_id not in passages or passage.score > passages[node_id].score:
                passages[node_id] = passage
    return frozenset(ids), passages


def _describe(expr: BoolExpr) -> str:
    """`expr`, rendered for a reader — what an empty-conjunction `note` names as "the disjoint
    operands" rather than leaving them to be reconstructed from `Candidates.lists` by hand.
    """
    if expr.op is BoolOp.TERM:
        return f"'{expr.term}'"
    if expr.op is BoolOp.NOT:
        return f"not {_describe(expr.clauses[0])}"
    joiner = " and " if expr.op is BoolOp.AND else " or "
    return "(" + joiner.join(_describe(clause) for clause in expr.clauses) + ")"
