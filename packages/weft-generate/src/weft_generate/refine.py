"""`refine-on-uncertainty` — the one `Generator` this task ships. `Stage[Passages, Answer]`.

Task **2.24**, `docs/build-ledger.md`: "a draft's uncertainty is a replaceable, named signal
rather than a phrase list, so the trigger cannot break silently under another language or
model." `10` §1.1's own `refine-on-uncertainty` row states the reference's actual defect, and it
is precise about what fails, and how: "`adaptive.py:83-85` tests the draft against a
nine-phrase localised list (`en.yaml:944-953`) with `str.__contains__` … This fires on
*hedging*, never on *unsupportedness*, and breaks silently under another language or system
prompt." Nothing about that failure raises, logs, or fails a test — a phrase list that does
not match a Polish hedge simply never fires, which is exactly the property this task's own
line names as the thing to close.

**The fix is that there is no phrase list here at all.** `self._config.signal` names a
`weft_retrieve.contract.Sufficiency` (task 2.4's contract; `weft_retrieve.sufficiency`, task
2.24's other half, is where its two implementations live), resolved by name through
`StageLookup` — the identical concession `weft_retrieve.iterative`'s own `sufficiency` field
already takes for the same contract. This module never imports `llm-sufficiency` or
`hedge-phrases` and does not know which one a document names: an operator who swaps
`signal: hedge-phrases` for `signal: llm-sufficiency` (or the reverse) in a `with:` block
changes the mechanism the trigger fires on without touching a line of this file, which is the
ledger line's own claim made mechanical rather than argued in prose.

Zhengbao Jiang, Frank F. Xu, Luyu Gao, Zhiqing Sun, Qian Liu, Jane Dwivedi-Yu, Yiming Yang,
Jamie Callan, Graham Neubig, *Active Retrieval Augmented Generation*, EMNLP 2023,
pp. 7969-7992, arXiv:2305.06983 — `10` §1.1's own row names this as "the nearest published
ancestor, and the reference does not cite it". Cited here for the same reason, not as a claim
this plugin *is* FLARE: FLARE's own signal is the drafting model's **token probability**,
regenerated sentence by sentence as it writes; Self-RAG's is a **trained reflection token**.
Neither mechanism is implemented — `.phase2-design.md` §10's own task row for this plugin
states it outright: "Not `self-rag`, not `flare`: `10` §4 reserves both." This plugin's own
signal is a *whole-draft* verdict, asked once per round, from whichever `Sufficiency` a
document names — coarser than either paper's mechanism, and honestly named for what it is
rather than for what it is not. `10` §1.1's closing note on the reference — "capped at one extra
round despite metadata calling it 'iterative'" — is not repeated by omission here:
`max_rounds` is a real, documented, configured field (default `1`, matching what the reference
actually did), never a cap the code enforces while a label elsewhere claims otherwise.

**Draft, check, maybe retrieve and redraft — owned end to end, the same concession
`weft_retrieve.iterative`'s own module docstring names for a looping technique.** `.phase2-
design.md` §4: "`iterative-retrieval`, `corrective` and `refine-on-uncertainty` all need 'do
it again, differently, if X'." This plugin is the third. Unlike `iterative-retrieval`, the
loop here is not about evidence volume — it is about whether the *drafted answer* is
confident enough to hand back, so the signal is always asked with the draft's own text
(`Sufficiency.assess`'s `draft` parameter, `None` for `iterative-retrieval`'s own use, never
`None` here).

**Why this is a `Generator`, not a `Retriever`, even though it retrieves.** `.phase2-
design.md` §2: "`refine-on-uncertainty` retrieves again after drafting, so it looks like a
`Retriever` that needs `Answer`. It is therefore published as a `Generator` in `weft-generate`
and reaches a retriever through the `StageLookup` service, not through an import." Publishing
it any other way would put `Answer` in `weft-retrieve`, breaking the one-way dependency chain
`weft-kernel ← weft-store ← weft-llm ← weft-prompts ← weft-retrieve ← weft-generate`; this
module is where that consequence lands rather than where it is merely stated.

**Drafting is this plugin's own call, not a delegated `Generator`.** `cost_bound = (2, 4)` is
a *fixed* pair, unlike `iterative-retrieval`'s `(1, -1)`: this plugin does not resolve an
arbitrary third-party `Generator` by name to draft with (which could cost anything) — it asks
`self._config.prompt` directly through `llm.complete`, the same single call
`weft_generate.cited_answer` makes for the same reason, defaulting to that plugin's own
registered prompt (`answer-with-citations`) rather than adding a near-duplicate. **Bounded
twice, not once** — the same shape `weft_retrieve.iterative`'s own module docstring states
for its loop: `range(1, max_rounds + 2)` below is what actually stops this loop, a fact true
regardless of whether `refinement_stop` itself is correct; `refinement_stop` is what makes
the stop honest about *why*. Floor: one draft call plus one signal call, when the first draft
is already confident. Ceiling, at the default `max_rounds=1`: two full rounds (draft, signal,
draft, signal) = four. A document that raises `max_rounds` raises the real ceiling past what
this fixed tuple states — an operator reads `max_rounds`, not this tuple, the same reading
`weft_retrieve.iterative`'s own bound gets.

**Citations, page numbers and "which sources were cited" are `weft_generate.cited_answer`'s
own mechanism, restated here rather than imported** — the same small, plugin-local
duplication `weft_generate.contradiction`'s own module docstring already carries for the
identical reason: each prompt's own numbering is the plugin's work, not a shared one.
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_generate.page import page_for
from weft_generate.payload import Answer, AnswerStance, Citation
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsRequest
from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Node, Outcome, Produced, SourceId
from weft_kernel.runner import Stage
from weft_llm.contract import LLM
from weft_llm.payload import OnFailure
from weft_prompts.contract import Prompt
from weft_retrieve.contract import Retriever, StageLookup, Sufficiency
from weft_retrieve.payload import (
    Assessment,
    Candidates,
    Passage,
    Passages,
    Query,
    QueryOrigin,
    QuerySet,
)
from weft_store.contract import NodeStore

#: The name this generator is registered and selectable under — see `weft_generate.register`.
NAME = "refine-on-uncertainty"


class RefinementStop(StrEnum):
    """Why this round's draft is the one returned. Reported, never left implicit — the same
    "named, testable stopping rule" shape `weft_retrieve.iterative.StopReason` already gives
    a looping technique in this tree, applied here to a refining one.
    """

    #: The signal judged the draft sufficient, at or above `threshold`.
    CONFIDENT = "confident"
    #: The configured ceiling was reached without the signal ever being satisfied.
    MAX_ROUNDS = "max-rounds"
    #: A retrieval round ran and added nothing the loop had not already seen — redrafting
    #: against unchanged evidence would not change what the signal has to judge.
    NO_NEW_EVIDENCE = "no-new-evidence"
    #: The signal ran but could not judge (`Assessment.observed = False`) — a different fact
    #: from `sufficient=False`, and reported as one rather than folded into the ceiling.
    SIGNAL_UNOBSERVED = "signal-unobserved"


def refinement_stop(
    *, round: int, max_rounds: int, assessment: Assessment, threshold: float
) -> RefinementStop | None:
    """Why this round's draft should be returned, or `None` to retrieve more and redraft.

    Checked in one fixed order, for the same reason `weft_retrieve.iterative.stop_reason`'s
    own docstring gives: more than one condition can be true in the same round, and only one
    reason can be reported.

    1. **The signal could not look** (`not assessment.observed`) — a hard cascade failure is
       a different code path (`on_signal_failure`); this is the contract's own "I looked and
       could not tell" case. Forcing another round against a signal with nothing to say would
       not make the eventual stop more honest, only later.
    2. **Confident** — `sufficient` alone is not enough: a signal that says "sufficient" at
       confidence `0.1` is not the same fact as one that says so at `0.95`, and `threshold`
       is the field an operator tunes to decide how much confidence "confident enough" means.
    3. **The ceiling** — this round is the last one `max_rounds` allows.

    Reaching the end with none of the above true means retrieve more and try again — the
    `NO_NEW_EVIDENCE` case is decided one level up, in `RefineOnUncertainty.run`, once a
    retrieval this function cannot see has actually happened.
    """
    if not assessment.observed:
        return RefinementStop.SIGNAL_UNOBSERVED
    if assessment.sufficient and assessment.confidence >= threshold:
        return RefinementStop.CONFIDENT
    if round > max_rounds:
        return RefinementStop.MAX_ROUNDS
    return None


class RefinementTrace(ExtModel):
    """Why and after how many rounds `refine-on-uncertainty` returned its draft — attached to
    the returned `Answer.ext`, the same no-span-in-a-plugin convention `weft_retrieve.
    iterative.IterativeRetrievalTrace` and `weft_retrieve.corrective.CorrectiveTrace` already
    carry: spans are the registration seam's concern, not a plugin's.
    """

    __namespace__ = "weft-generate"
    __schema_version__ = "1.0.0"

    stopped_because: RefinementStop
    rounds_run: int = Field(ge=1)


class RefineOnUncertaintyConfig(BaseModel):
    """`RefineOnUncertainty`'s `with:` config. Every field has a default, per this pack's own
    rule. `signal`, `retriever`, `threshold`, `max_rounds` and `on_signal_failure` are
    `.phase2-design.md` §10's own task-table fields for this row. `prompt`, `role`,
    `max_passages`, `signal_config` and `retriever_config` are recorded additions, on
    `iterative-retrieval`'s own precedent (`leaf_config`/`sufficiency_config`) for the finding
    that names them: a knob that exists in the library and not in the config model is a knob
    a third party cannot reach (`.phase2-findings.md` finding 9).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(default=ANSWER_WITH_CITATIONS_NAME, min_length=1)
    role: str = Field(default="generate", min_length=1)
    max_passages: int = Field(default=8, ge=1)
    #: The `Sufficiency` this plugin's trigger is judged by, resolved by name through
    #: `StageLookup` — this task's own line: the mechanism is a name in this field, never a
    #: phrase list in this file.
    signal: str = Field(default="llm-sufficiency", min_length=1)
    #: `signal`'s own `with:` block — passed straight through as `StageLookup.build_
    #: capability`'s third argument, the same lever `IterativeRetrievalConfig.
    #: sufficiency_config` already gives its own signal.
    signal_config: Mapping[str, object] | None = None
    #: The `Retriever` a low-confidence round searches with, resolved by name.
    retriever: str = Field(default="vector-top-k", min_length=1)
    retriever_config: Mapping[str, object] | None = None
    #: How confident `signal` must be, at or above `sufficient=True`, before this plugin
    #: stops and returns the draft in hand.
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    #: How many *extra* rounds beyond the first draft are allowed. `1` is the reference's own
    #: real behaviour (`10` §1.1: "capped at one extra round"), now a field an operator reads
    #: and can change, not a cap the code enforces while metadata claims otherwise.
    max_rounds: int = Field(default=1, ge=0)
    #: What a *hard* signal failure does — the `Sufficiency.assess` call itself answering
    #: `Failed`, never the softer `Assessment(observed=False)` `SIGNAL_UNOBSERVED` reports.
    #: One member today (`FAIL`) — see that field's own docstring on `weft_llm.payload.
    #: OnFailure` for why a second is added only in the commit that needs it.
    on_signal_failure: OnFailure = OnFailure.FAIL


class RefineOnUncertainty:
    """Drafts, asks a named signal whether the draft is confident, and — if not — retrieves
    once more and redrafts, up to `max_rounds` extra times. Satisfies `weft_generate.
    contract.Generator` structurally.

    `cost_bound = (2, 4)` — see the module docstring's own arithmetic.
    """

    config_model: ClassVar[type[RefineOnUncertaintyConfig]] = RefineOnUncertaintyConfig
    cost_bound: ClassVar[tuple[int, int]] = (2, 4)

    def __init__(self, config: RefineOnUncertaintyConfig | None = None) -> None:
        self._config = config if config is not None else RefineOnUncertaintyConfig()

    async def run(self, payload: Passages, ctx: Context) -> Outcome[Answer]:
        """Draft under `origin` alone at every round, never a derived query — the obligation
        every plugin closing the query path carries (`weft_retrieve.payload.QuerySet.
        origin`'s own docstring). The `QuerySet` built for a low-confidence round is what
        searches; the `Answer` returned is always built with `payload.origin`.
        """
        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        draft_prompt = await lookup.build_capability(Prompt, self._config.prompt)
        signal = await lookup.build_capability(
            Sufficiency, self._config.signal, self._config.signal_config
        )
        retriever_contract = cast("type[Stage[QuerySet, Candidates]]", Retriever)
        retriever = await lookup.build(
            retriever_contract, self._config.retriever, self._config.retriever_config
        )

        current = payload
        seen_ids = {passage.node.id for passage in current.passages}
        text = ""
        offered: tuple[Passage, ...] = ()
        reason = RefinementStop.MAX_ROUNDS  # replaced every round; never left at this default
        round_number = 0

        for round_number in range(1, self._config.max_rounds + 2):
            offered = current.passages[: self._config.max_passages]
            rendered = await draft_prompt.render(
                AnswerWithCitationsRequest(question=payload.origin.text, passages=_offer(offered)),
                ctx,
            )
            if not isinstance(rendered, Produced):
                # A prompt with nothing to ask is relayed exactly as it answered — the same
                # rule every generator in this pack takes.
                return rendered
            completion = await llm.complete(rendered.value, role=self._config.role, ctx=ctx)
            if not isinstance(completion, Produced):
                return completion
            text = completion.value.text

            assessed = await signal.assess(payload.origin, current, text, ctx)
            if not isinstance(assessed, Produced):
                # `on_signal_failure` has one member today (FAIL): relaying the signal's own
                # outcome *is* failing loudly — the same arithmetic `on_critic_failure`
                # states on `weft_retrieve.iterative`.
                return assessed
            assessment = assessed.value

            decided = refinement_stop(
                round=round_number,
                max_rounds=self._config.max_rounds,
                assessment=assessment,
                threshold=self._config.threshold,
            )
            if decided is not None:
                reason = decided
                break

            retrieved = await retriever(_next_round(payload, assessment.missing), ctx)
            if not isinstance(retrieved, Produced):
                # A retriever that declined or failed is relayed exactly as it answered —
                # never synthesised into an empty round and continued past, the same rule
                # `weft_retrieve.iterative.IterativeRetrieval.run` states for its own leaf.
                return retrieved
            fresh = tuple(hit for ranked in retrieved.value.lists for hit in ranked.hits)
            new = tuple(hit for hit in fresh if hit.node.id not in seen_ids)
            if not new:
                reason = RefinementStop.NO_NEW_EVIDENCE
                break
            seen_ids.update(hit.node.id for hit in new)
            current = _merge_passages(current, new)

        citations = await _citations_for(offered, text=text, ctx=ctx)
        return Produced(
            value=Answer(
                origin=payload.origin,
                text=text,
                citations=citations,
                used=offered,
                stance=AnswerStance.ANSWERED,
                answered_by=NAME,
                ext={
                    RefinementTrace.__namespace__: RefinementTrace(
                        stopped_because=reason, rounds_run=round_number
                    )
                },
            )
        )


def _next_round(payload: Passages, missing: tuple[str, ...]) -> QuerySet:
    """The `QuerySet` a low-confidence round searches with — one derived `Query` built from
    what the signal said was missing, the same replacement `weft_retrieve.iterative.
    _next_round`'s own docstring states for a trained query generator: reading a fact the
    signal already computed rather than a second model call.
    """
    text = "; ".join(missing) if missing else payload.origin.text
    derived = Query(
        text=text,
        origin=QueryOrigin.DERIVED,
        produced_by=NAME,
        locale=payload.origin.locale,
        filter=payload.origin.filter,
    )
    return QuerySet(origin=payload.origin, queries=(derived,))


def _merge_passages(current: Passages, new: tuple[Passage, ...]) -> Passages:
    """`current`'s own passages, plus `new`, relabelled from `1` so every passage the next
    round's draft can cite has a label unique across the merged set — the same `str(position
    + 1)` labelling `weft_retrieve.repack.Repack`'s own packer assigns, applied here because a
    retrieval round changes *how many* passages there are, not just their order.
    """
    combined = current.passages + new
    relabelled = tuple(
        Passage(
            scored=passage.scored, rank=rank, retrieved_by=passage.retrieved_by, label=str(rank + 1)
        )
        for rank, passage in enumerate(combined)
    )
    return Passages(origin=current.origin, passages=relabelled, ext=current.ext)


def _offer(passages: tuple[Passage, ...]) -> str:
    """The offered evidence as one string, numbered by each passage's own `label` — the same
    shape `weft_generate.cited_answer._offer` and `weft_generate.contradiction._offer` build,
    restated here rather than imported for the reason both those modules' own docstrings give.
    """
    if not passages:
        return ""
    return "\n\n".join(f"[{passage.label}] {passage.node.content}" for passage in passages)


async def _citations_for(
    offered: tuple[Passage, ...], *, text: str, ctx: Context
) -> tuple[Citation, ...]:
    """One `Citation` per offered passage whose own bracketed label appears in `text` — a
    literal substring search, the same one `weft_generate.cited_answer._citations_for`
    performs, restated here for the same small-plugin-local-duplication reason.
    """
    cited = [
        (passage, _source_id(passage.node)) for passage in offered if f"[{passage.label}]" in text
    ]
    store = ctx.require(NodeStore)
    uris = await _uris_for((source_id for _, source_id in cited), store=store)
    return tuple(
        Citation(
            marker=passage.label,
            node_id=passage.node.id,
            source_id=source_id,
            uri=uris.get(source_id, "") if source_id is not None else "",
            page=page_for(passage.node),
        )
        for passage, source_id in cited
    )


async def _uris_for(
    source_ids: Iterable[SourceId | None], *, store: NodeStore
) -> dict[SourceId, str]:
    """Every distinct known source's `uri`, looked up once each rather than once per citation."""
    wanted = {source_id for source_id in source_ids if source_id is not None}
    uris: dict[SourceId, str] = {}
    for source_id in wanted:
        record = await store.get_source(source_id)
        uris[source_id] = record.uri if record is not None else ""
    return uris


def _source_id(node: Node) -> SourceId | None:
    """`node`'s one source, or `None` when it has none or more than one to choose from — see
    `weft_generate.cited_answer._source_id`'s own docstring for the two cases this refuses to
    guess between.
    """
    sources = node.lineage.sources
    return next(iter(sources)) if len(sources) == 1 else None
