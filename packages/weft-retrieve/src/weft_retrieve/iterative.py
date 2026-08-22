"""`iterative-retrieval` — a looping technique that owns its own loop. `Retriever`.

Task **2.20**, `docs/build-ledger.md`: "an evidence-sufficiency loop is expressible, and its
stopping rule is one named, testable thing rather than four scattered breaks." `.phase2-
design.md` §4's own catalogue of where the thesis breaks names this module's whole shape
before a line of it is written: "a resolved pipeline is a finite ordered list … `iterative-
retrieval` … needs 'do it again, differently, if X'. No control flow is added to the grammar
… the concession: a looping technique is one plugin that owns its loop and reaches a sibling
through `StageLookup`." This module is that concession, taken up exactly once — `leaf`
(a `Retriever`, resolved by name) and `sufficiency` (a `Sufficiency`, resolved by name) are
both reached through `weft_retrieve.contract.StageLookup`, never imported or constructed
here, so a document swaps either by editing a string in a `with:` block rather than by
editing this file.

Peng Qi, Xiaowen Lin, Leo Mehr, Zijian Wang, Christopher D. Manning, *Answering Complex
Open-domain Questions Through Iterative Query Generation*, EMNLP-IJCNLP 2019,
arXiv:1910.07000 — the paper this plugin's name is earned against, per `10` §1.4 and task
2.26's own naming audit. `10` §1.1's own row on this technique names the reference's shape
directly: "`iterative.py:70-170` is Qi et al.'s loop with an LLM sufficiency critic in place
of a trained query generator" — which is this module's shape too, and the trained query
generator's replacement is not a second model call. `Assessment.missing` already names what a
follow-up query should go after (that field's own docstring), so the next round's query is
built from it directly, the same way `weft_retrieve.transforms._render_history` turns a
`Turn` tuple into text without a model call: `cost_bound`'s floor of one is one leaf call plus
one critic call, not two.

**Two reference defects, fixed by construction rather than by discipline — `10` §1.1's own row
names both.**

1. `min_loops=2` "forced a second round even when the critic said stop — no paper in the
   family does that." `min_rounds` is this build's answer, and its *default* (`1`) is what
   makes the fix real rather than renamed: nothing is forced unless an operator asks for it,
   the same "omittable by construction, not by discipline" shape `contextual-query-rewrite`
   (ledger 2.15) already gave the rewrite-on-every-strategy defect.
2. `critique.py:76-84` "treats any non-empty context as complete when the critique call
   failed, silently downgrading the strategy to single-shot." `on_critic_failure: OnFailure =
   FAIL` (published by `weft-llm`, not invented here — see that field's own docstring) is the
   fix: a hard critic failure fails the whole retrieval rather than being read as "good
   enough". See `test_a_hard_critic_failure_fails_the_whole_retrieval` in this module's
   mirror.

**The stopping rule is the whole task, and it is `stop_reason` — one function, tested on its
own, below.** Four scattered `break` statements inside a `while` would give a reader (or a
reviewer) no single place to check "does this loop ever stop, and does it say why" — the
order the checks happened to be written in decides which one fires first, invisibly. This
module states the order once, in `stop_reason`'s own docstring, and
`tests/unit/weft_retrieve/test_iterative.py`'s `test_stop_reason_*` group drives every branch
directly, with a hand-built `LoopState`, never by running the loop. `StopReason` is what makes
"the bound is hit" a *named*, reported outcome — `MAX_ROUNDS` — rather than the loop silently
returning whatever it has once the `for` runs out, which `.phase2-design.md`'s own line calls
"hiding having stopped early."

**Bounded twice, not once.** The `for round_number in range(1, max_rounds + 1)` below is
what actually stops the loop from spinning forever — a fact true regardless of whether
`stop_reason` itself is correct. `stop_reason` is what makes the stop *honest about why*,
which the `range` bound alone cannot do: reaching `max_rounds` without `stop_reason` also
agreeing would mean the last round's `LoopState` disagreed with the loop's own arithmetic,
which cannot happen (`round == max_rounds` forces `stop_reason`'s own ceiling branch), and
`test_the_loop_never_exceeds_max_rounds` checks the call count directly rather than trusting
the argument.

**No span is written here.** `weft_kernel.seam.wrap` owns spans, error attribution, blocking
detection and transient stripping structurally — this project's own rule, restated because a
looping technique is exactly the kind of module where "just attach one more attribute to the
span" is tempting. `StopReason` is reported the way every other cross-cutting fact this pack
hands downstream is: a namespaced `ExtModel` on the returned `Candidates.ext`
(`IterativeRetrievalTrace`, below) — inspectable by a caller, a test, or a future span
enricher that reads `ext` at the seam, without this module reaching for the tracer itself.

**`needs_store` is not declared.** Unlike `vector-top-k`, this plugin never touches a store
directly — `leaf` does, and `leaf` is resolved by name at `run` time, not at registration, so
there is no store capability this class itself could state ahead of time. `weft_retrieve.
no_retrieval.NoRetrieval` is the precedent for a `Retriever` that declares no `needs_store` at
all.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Outcome, Produced
from weft_kernel.runner import Stage
from weft_llm.payload import OnFailure
from weft_retrieve.contract import Retriever, StageLookup, Sufficiency
from weft_retrieve.payload import (
    Assessment,
    Candidates,
    Passage,
    Passages,
    Query,
    QueryOrigin,
    QuerySet,
    RankedList,
)

#: The name this retriever is registered and selectable under — see `weft_retrieve.register`.
NAME = "iterative-retrieval"


class StopReason(StrEnum):
    """Why the loop stopped. Reported, never inferred by a reader from the round count alone.

    Four members, because `10` §1.1's own row and `.phase2-design.md` §10's task table name
    exactly these four facts a loop can end on. There is no fifth member for "still going" —
    see `stop_reason`'s own docstring for why that is `None` rather than a member of this
    enum: this type names why the loop *stopped*, and "it has not stopped yet" is not a fact
    about a stop.
    """

    #: The critic judged the evidence in hand sufficient.
    SUFFICIENT = "sufficient"
    #: The configured ceiling was reached without the critic ever being satisfied.
    MAX_ROUNDS = "max-rounds"
    #: A round ran and added nothing the loop had not already seen — continuing would not
    #: change what the critic has to judge.
    NO_NEW_EVIDENCE = "no-new-evidence"
    #: The critic ran but could not judge (`Assessment.observed = False`) — a different fact
    #: from `sufficient=False`, and reported as one rather than folded into the ceiling.
    CRITIC_UNOBSERVED = "critic-unobserved"


class LoopState(BaseModel):
    """Exactly what `stop_reason` decides from, and nothing else.

    Built fresh each round by `IterativeRetrieval.run`, from facts that round itself
    measured — never accumulated silently inside a closure `stop_reason` could not see.
    Frozen, so a hand-built `LoopState` in a test is exactly what the loop itself would have
    passed for the same round.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: 1-indexed — the round that just ran.
    round: int = Field(ge=1)
    min_rounds: int = Field(ge=1)
    max_rounds: int = Field(ge=1)
    #: This round's own critique of the evidence accumulated so far.
    assessment: Assessment
    #: Whether this round's retrieval added anything the loop had not already seen —
    #: `IterativeRetrieval.run`'s own dedup, never re-derived inside `stop_reason`.
    gained_new_evidence: bool


def stop_reason(state: LoopState) -> StopReason | None:
    """Why the loop should stop after this round, or `None` to keep going.

    Checked in one fixed order, because more than one of the four conditions can be true in
    the same round and only one reason can be reported — which one fires first in a
    hand-written `while` depends on the order the checks happened to be written in, not on
    which fact is most useful to a reader debugging why the loop stopped. Here the order is
    a fact about this function, stated once:

    1. **The critic could not look** (`not assessment.observed`) — checked before the floor.
       Forcing further rounds against a critic with nothing to say about them would not make
       the eventual stop more honest, only later, and reporting `MAX_ROUNDS` several rounds
       after the critic first went silent would name the wrong reason.
    2. **The floor** (`round < min_rounds`) — keeps the loop going even past a critic that
       already said `sufficient=True`. The reference's `min_loops=2` fix, made genuinely
       optional: `IterativeRetrievalConfig.min_rounds` defaults to `1`, so nothing is forced
       unless an operator asks for it.
    3. **Sufficient** — the critic's own word that the evidence in hand answers the question.
    4. **The ceiling** (`round >= max_rounds`) — named by this function rather than left for
       the loop to run out silently.
    5. **No new evidence** — this round added nothing the loop had not already seen, and
       continuing would pay for a round the critic's opinion has nothing new to react to.

    Reaching the end with none of the above true means genuinely keep going.
    """
    if not state.assessment.observed:
        return StopReason.CRITIC_UNOBSERVED
    if state.round < state.min_rounds:
        return None
    if state.assessment.sufficient:
        return StopReason.SUFFICIENT
    if state.round >= state.max_rounds:
        return StopReason.MAX_ROUNDS
    if not state.gained_new_evidence:
        return StopReason.NO_NEW_EVIDENCE
    return None


class IterativeRetrievalTrace(ExtModel):
    """Why and when the loop stopped — attached to the returned `Candidates.ext`.

    The observable record of `stop_reason`'s own decision, for a caller, a test, or a future
    span enricher that reads a produced payload's `ext` — the mechanism `weft_retrieve.
    fusion`'s own module docstring already uses to cross the arity reduction, applied here to
    carry a fact out of a loop that (per this module's own rule) writes no span of its own.
    """

    __namespace__ = "weft-retrieve"
    __schema_version__ = "1.0.0"

    stop_reason: StopReason
    rounds_run: int = Field(ge=1)


class IterativeRetrievalConfig(BaseModel):
    """`IterativeRetrieval`'s `with:` config. Every field has a default, per this pack's own
    rule that a Phase 2 pack's settings must be constructible with none supplied — and per
    ledger 2.20's own line, which names every bound this loop has as configuration: how many
    rounds, how few, which critic, which leaf, and what a hard critic failure does.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The ceiling. `range(1, max_rounds + 1)` below is what makes this an actual bound
    #: rather than a claim — the loop cannot run more rounds than this regardless of what
    #: `stop_reason` decides.
    max_rounds: int = Field(default=3, ge=1)
    #: The floor. `1` — not the reference's `min_loops=2` — is what makes "no round is forced
    #: unless an operator asks for one" the *default* rather than an opt-in fix.
    min_rounds: int = Field(default=1, ge=1)
    #: The `Sufficiency` this loop's stopping rule is judged by, resolved by name through
    #: `StageLookup` — `weft_retrieve.contract.Sufficiency`'s own docstring: "a named contract
    #: with two implementations is what 'replaceable' means here." `llm-sufficiency` is
    #: task 2.24's, not built by this one — see the module docstring.
    sufficiency: str = Field(default="llm-sufficiency", min_length=1)
    #: `sufficiency`'s own `with:` block — the same lever as `leaf_config`, one field below,
    #: applied to the critic instead of the leaf. See `leaf_config`'s own docstring for the
    #: finding this pair repairs; nothing about the argument is specific to which of the two
    #: sub-plugins it is passed to.
    sufficiency_config: Mapping[str, object] | None = None
    #: The `Retriever` each round actually searches with, resolved by name through
    #: `StageLookup`. Defaulting to `vector-top-k` rather than to this plugin's own name is
    #: what stops a document from constructing a loop of loops by accident.
    leaf: str = Field(default="vector-top-k", min_length=1)
    #: `leaf`'s own `with:` block — passed straight through as `StageLookup.build`'s third
    #: argument, which exists (`weft_retrieve.contract.StageLookup`'s own docstring) so a
    #: *calling* plugin can hand a resolved sibling its configuration the same way a
    #: document's own `with:` block reaches a top-level stage. `None` reaches `leaf` exactly
    #: as an absent `with:` block would in a document — the leaf's own defaults, not this
    #: plugin's opinion of them. Repair for a finding this
    #: task shipped without: `vector-top-k` (the default `leaf`) is a real, richly configured
    #: plugin — `top_k`, `per_query_top_k`, `channels` — and running it twice with different
    #: settings across rounds is `.phase2-findings.md` finding 9's fourth clause ("a knob
    #: that exists in the library and not in the config model is a knob a third party cannot
    #: reach"), which that finding's own closing paragraph names as reaching "retrieval
    #: strategies (2.4)" too. Without this field, the only lever a document has over the
    #: leaf is swapping which *plugin* fills the role by name — this field is the lever over
    #: how the chosen one runs.
    leaf_config: Mapping[str, object] | None = None
    #: What a *hard* critic failure does — the `Sufficiency.assess` call itself answering
    #: `Failed`, never the softer `Assessment(observed=False)` `CRITIC_UNOBSERVED` reports.
    #: `FAIL` fixes the reference treating any non-empty context as complete when the critique
    #: call failed, silently downgrading to single-shot.
    on_critic_failure: OnFailure = OnFailure.FAIL
    #: Whether evidence — and the critic's own view of it — carries across rounds (`True`),
    #: or each round starts over from nothing (`False`). `True` is Qi et al.'s own shape: the
    #: critic judges what has been gathered *so far*, not just what the last round found.
    accumulate: bool = True

    @model_validator(mode="after")
    def _floor_within_ceiling(self) -> "IterativeRetrievalConfig":
        """`min_rounds` above `max_rounds` is not a loop that forces extra rounds — it is one
        that can never stop on its own ceiling, refused here rather than discovered as a
        `StopReason.MAX_ROUNDS` that fires below the floor `stop_reason` was told to honour.
        """
        if self.min_rounds > self.max_rounds:
            raise ValueError(
                f"min_rounds ({self.min_rounds}) cannot exceed max_rounds "
                f"({self.max_rounds}) — a floor above the ceiling is a loop with no ceiling "
                f"it can actually stop on."
            )
        return self


class IterativeRetrieval:
    """Retrieves, asks a critic whether the evidence suffices, and retrieves again on what is
    missing — the paper's own loop, owned end to end by this plugin. Satisfies `weft_retrieve.
    contract.Retriever` structurally.

    `cost_bound = (1, -1)`: a floor of one (a round always costs at least the critic's own
    call; `leaf`'s own floor is not assumed to be zero, since it is resolved by name and could
    be any registered `Retriever`), and an unbounded ceiling for the same reason — `leaf`
    could be a technique with its own model calls, run up to `max_rounds` times. `max_rounds`
    is the real bound in practice, and it is what an operator reads, not this tuple; see the
    module docstring's "bounded twice, not once."
    """

    config_model: ClassVar[type[IterativeRetrievalConfig]] = IterativeRetrievalConfig
    cost_bound: ClassVar[tuple[int, int]] = (1, -1)

    def __init__(self, config: IterativeRetrievalConfig | None = None) -> None:
        self._config = config if config is not None else IterativeRetrievalConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        """Retrieve, critique, retrieve again on what is missing — up to `max_rounds` times.

        `out.origin == in.origin` holds by construction: the `Candidates` returned below is
        always built with `payload.origin`, never with whichever derived query a later round
        happened to search with — the same obligation every query-path plugin in this pack
        carries (`QuerySet.origin`'s own docstring).
        """
        lookup = ctx.require(StageLookup)
        # `Retriever` is a `Protocol` subclass of `Stage[QuerySet, Candidates]`, and pyright
        # cannot solve `StageLookup.build`'s `In`/`Out` from a `type[Protocol subclass]` —
        # confirmed against a minimal reproduction rather than assumed; the cast states the
        # fact the contract already declares (`Retriever`'s own base list), it does not
        # invent one.
        retriever_contract = cast("type[Stage[QuerySet, Candidates]]", Retriever)
        leaf = await lookup.build(retriever_contract, self._config.leaf, self._config.leaf_config)
        sufficiency = await lookup.build_capability(
            Sufficiency, self._config.sufficiency, self._config.sufficiency_config
        )

        current = payload
        lists: list[RankedList] = []
        evidence: tuple[Passage, ...] = ()
        reason = StopReason.MAX_ROUNDS  # replaced every round; never left at this default.
        # `max_rounds >= 1` is enforced by `IterativeRetrievalConfig`'s own field, so the
        # `for` below always runs at least once — this is only what makes that guarantee
        # visible to the type checker, not a value the loop could actually fall back to.
        round_number = 0

        for round_number in range(1, self._config.max_rounds + 1):
            retrieved = await leaf(current, ctx)
            if not isinstance(retrieved, Produced):
                # A leaf that declined or failed is relayed exactly as it answered — never
                # synthesised into an empty round and continued past, which would make the
                # loop's own result claim a round that never actually happened.
                return retrieved
            candidates = retrieved.value
            fresh = tuple(hit for ranked in candidates.lists for hit in ranked.hits)

            if self._config.accumulate:
                new = _unseen(evidence, fresh)
                evidence = evidence + new
                lists.extend(candidates.lists)
            else:
                new = fresh
                evidence = fresh
                lists = list(candidates.lists)

            assessed = await sufficiency.assess(
                payload.origin, _as_passages(payload.origin, evidence), None, ctx
            )
            if not isinstance(assessed, Produced):
                # `on_critic_failure` has one member today (FAIL): relaying the critic's own
                # outcome *is* failing loudly — the fix for the reference's `critique.py:76-84`,
                # which read a failed critique call as "the context is complete". See the
                # module docstring.
                return assessed

            state = LoopState(
                round=round_number,
                min_rounds=self._config.min_rounds,
                max_rounds=self._config.max_rounds,
                assessment=assessed.value,
                gained_new_evidence=bool(new),
            )
            decided = stop_reason(state)
            if decided is not None:
                reason = decided
                break
            current = _next_round(payload, assessed.value.missing)

        return Produced(
            value=Candidates(
                origin=payload.origin,
                lists=tuple(lists),
                ext={
                    IterativeRetrievalTrace.__namespace__: IterativeRetrievalTrace(
                        stop_reason=reason, rounds_run=round_number
                    )
                },
            )
        )


def _unseen(accumulated: tuple[Passage, ...], fresh: tuple[Passage, ...]) -> tuple[Passage, ...]:
    """`fresh`, minus every passage whose node identity is already in `accumulated`.

    Deduped by `Node.id` — a content digest — rather than by passage equality, so the same
    node retrieved twice by two different rounds (a leaf's top hits rarely change) is
    recognised as the same evidence even if its score or rank differs between the two
    retrievals. This is what makes `gained_new_evidence` a fact about the *evidence*, not
    about whether the leaf happened to return an identically-shaped `Passage` twice.
    """
    seen = {passage.node.id for passage in accumulated}
    return tuple(passage for passage in fresh if passage.node.id not in seen)


def _as_passages(origin: Query, hits: tuple[Passage, ...]) -> Passages:
    """`hits`, labelled for the critic alone — never the labels a `ContextPacker` assigns.

    `Passages.passages` refuses a blank or repeated label (that type's own validator), and
    nothing upstream of a `ContextPacker` has assigned one yet — this loop is a `Retriever`,
    two positions before that one. The labels built here (`e0`, `e1`, …) exist only so
    `Sufficiency.assess` has a `Passages` to read; they are never the labels that reach a
    reader, because this plugin's own output is `Candidates`, not `Passages` — a packer
    downstream assigns citation labels of its own, independently.
    """
    labelled = tuple(
        Passage(scored=hit.scored, rank=rank, retrieved_by=hit.retrieved_by, label=f"e{rank}")
        for rank, hit in enumerate(hits)
    )
    return Passages(origin=origin, passages=labelled)


def _next_round(payload: QuerySet, missing: tuple[str, ...]) -> QuerySet:
    """The `QuerySet` the next round searches with — one derived `Query` built from what the
    critic said was missing, or the original question again when it named nothing specific.

    `Assessment.missing`'s own docstring: "what a follow-up query should go after." Building
    the next query from it directly is Qi et al.'s trained query generator, replaced by
    reading a fact the critic already computed rather than by a second model call — `10`
    §1.1's row on this technique names that replacement, and the module docstring records
    why it keeps `cost_bound`'s floor at one call per round instead of two.
    """
    text = "; ".join(missing) if missing else payload.origin.text
    derived = Query(
        text=text,
        origin=QueryOrigin.DERIVED,
        produced_by=NAME,
        locale=payload.origin.locale,
        filter=payload.origin.filter,
    )
    return QuerySet(
        origin=payload.origin, queries=(derived,), history=payload.history, ext=payload.ext
    )
