"""Query transforms — the position before retrieval. `contextual-query-rewrite` is the first.

Task **2.15**, `docs/build-ledger.md`: "a query transform is a composable stage a caller can
omit, so no strategy pays for a rewrite it did not ask for." `weft_retrieve.contract.
QueryTransform` is `Stage[QuerySet, QuerySet]` — declared in task 2.4, not here — and that
single fact is the whole mechanism: identical `In` and `Out` is what makes inserting or
removing a transform a document edit that changes nothing about the seams either side of it.
This module's job is not to invent that property; it is to ship the first plugin that stands
on it without weakening it, because `hyde` (2.16) and `step-back` (2.17) register into this
same position next and inherit whatever shape this module gets wrong.

**Omittable by construction, not by discipline.** A follow-up-question rewrite applied to
every strategy including the baseline, unconditionally, is "un-nameable and
un-disableable" (`.phase2-design.md` §10's own words for it). `contextual-query-rewrite` is a
plugin like any other `Retriever` or `Fuser`: a document that does not name it never pays for
it, and `skip_without_history` below is what makes "nothing to rewrite" a zero-cost path
through the *same* plugin rather than a reason to fork a second one.

**`out.origin == in.origin`, always — even on the skip path.** `QuerySet.origin`'s own
docstring records the defect this closes: a hallucinated rewrite fed to a
cross-encoder *as the query*. This plugin never constructs a `QuerySet` without threading
`payload.origin` through unchanged, and every test in this module's mirror asserts it rather
than assuming it — `weft_kernel.runner` does not check `QuerySet.origin` itself; task 2.4's
ledger line leaves that obligation to each query-path plugin.

**`hyde` (task 2.16) joins below.** It reuses `_StubLLM` and `_RefusingLLM` as-is and adds
`_hyde_lookup` beside `_lookup`, because both plugins reach a typed answer through the same
`weft_prompts.cascade.execute` and the stub shape that proves it is the same shape either
way.

**`hyde` always calls — there is no skip path.** Unlike a follow-up rewrite, which has
nothing to do without history, HyDE is not conditioned on anything in the payload:
`Hyde.cost_bound` is `(1, 1)`, not `(0, 1)`, and `Hyde.run` resolves `LLM` and `StageLookup`
unconditionally on every invocation.

**`step-back` (task 2.17) joins below too, and settles the shared-base question task 2.16
left open — with evidence rather than by fiat.** `.phase2-design.md`'s stated decision —
"`hyde`, `step-back`, `multi-query` and `contextual-query-rewrite` share one base class and
one code path" — named `step-back`'s own landing as the point where a *third* concrete case
would exist to check the common shape against. It does now, and the shape holds: `StepBack`
renders a prompt, gets exactly one derived `Query` back, and combines it with the literal
one under `keep_question` — the same three steps `Hyde` takes with `N` derived queries
instead of one. The "third fact" task 2.16's own note worried about — "which derived query
is which kind, not just how many there are" — turns out not to need a new mechanism at all:
`Query.produced_by` already carries it, stamped `STEP_BACK_NAME` here exactly as `HYDE_NAME`
and `NAME` are stamped by the other two, so a consumer reading it back (a citation grouping
by which question found what) already has the fact it needs without this plugin inventing a
field for it.

So why is the base still three separate classes rather than one? Because the fourth case
this decision was always weighed against — `multi-query` (ledger 2.18a) — has not landed,
and its own row in `.phase2-design.md` §10 carries axes none of these three do:
`require_distinct` (a check across the derived set, not per-item) and `expansion:
ExpansionKind` (a choice between rendering strategies, not just a different prompt name).
Factoring now would still be guessing at *that* shape from three data points that do not
have it — the same premature-abstraction failure mode, one case closer to being wrong about
it rather than zero. What has changed is the reason: not "not
enough cases yet" but "the fourth case is the one that might reshape this, and it has not
been built." Left for task 2.18a to settle, once `multi-query` exists to check the
abstraction against rather than to guess about.

**`multi-query` (task 2.18a) has now landed below, and the shared-base question is closed —
not by folding it in, but by naming why it does not fold.** The three-step common part still
holds for the *shape* of a single seed: render a prompt, get one or more derived `Query`s
back, combine them under `keep_question`. What does not fold is *how many prompts get
rendered and how the answer is read back*. `Hyde` and `StepBack` always have exactly one
seed (`payload.origin`); `multi-query`'s own row adds `expand_origins`, which can select
*more than one* existing query as a seed at once (`.phase2-design.md`'s own worked example:
"it expands only queries whose `produced_by` is `""`", plural queries), and `cost_bound`
staying `(1, 1)` regardless of how many seeds matched means the cascade call has to be
*batched* — one rendered prompt offering every seed by index, one structured answer keyed
back to those same indices (`_offer_seeds`, `_groups_by_index`, mirroring `weft_retrieve.
rerank._offer` / `_scores_by_index` for the identical reason: a template cannot iterate).
`Hyde` and `StepBack` have no index to keep straight because they never have more than one
seed to keep straight it *against*. A shared base written for "one prompt in, one or more
queries out" would either grow multi-seed batching neither `Hyde` nor `StepBack` needs, or
stay single-seed and make `multi-query`'s own worked example — composing two fan-out stages
without multiplying — impossible to implement against it. Both are the guess `.phase2-design.
md`'s note warned against, now checked with the fourth case rather than guessed about: the
common part was real for three cases and stops being real at the fourth, so it stays three
classes plus this one rather than four, or three plus a base this one alone would have to
special-case around.
"""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Failed, Outcome, Produced
from weft_llm.contract import LLM
from weft_llm.payload import OnFailure
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Channel, Query, QueryOrigin, QuerySet, Turn
from weft_retrieve.prompts import (
    HYDE_DOCUMENT_NAME,
    MULTI_QUERY_VARIANTS_NAME,
    STANDALONE_QUESTION_NAME,
    STEP_BACK_QUESTION_NAME,
    HydeDocumentRequest,
    HydeDocuments,
    MultiQueryVariants,
    MultiQueryVariantsRequest,
    StandaloneQuestion,
    StandaloneQuestionRequest,
    StepBackQuestion,
    StepBackRequest,
)

#: The name this transform is registered and selectable under — see `weft_retrieve.register`.
NAME = "contextual-query-rewrite"


class ContextualQueryRewriteConfig(BaseModel):
    """`ContextualQueryRewrite`'s `with:` config. Every field has a default, per this pack's
    own rule that a Phase 2 pack's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many trailing `QuerySet.history` turns are rendered into the rewrite prompt.
    #: History arrives on the payload, never through the passport (`ctx` carries a run's
    #: tenant and locale, not a conversation) — a fact about *this ask*, not about the run.
    history_turns: int = Field(default=4, ge=0)
    prompt: str = Field(default=STANDALONE_QUESTION_NAME, min_length=1)
    role: str = Field(default="rewrite", min_length=1)
    #: Keep the literal follow-up in `queries` alongside the rewrite, or replace it outright.
    #: `True` is belt-and-braces: a rewrite that quietly narrowed the question's meaning still
    #: leaves the original searched for. `False` is what an operator who trusts the rewrite
    #: reaches for, so a retriever is not asked to search the ambiguous form twice.
    keep_question: bool = True
    #: The omittable-by-configuration switch: no history, no model call, no cost. Without
    #: this, the first turn of every conversation would still pay for a rewrite that has
    #: nothing to rewrite against — an unconditional call reintroduced one flag at a time
    #: rather than as a single hard-coded strategy.
    skip_without_history: bool = True
    on_failure: OnFailure = OnFailure.FAIL


class ContextualQueryRewrite:
    """Rewrites a conversational follow-up into a standalone question. Satisfies `contract.
    QueryTransform` structurally.

    `cost_bound = (0, 1)` — zero on the skip path (`run` returns before resolving `LLM` or
    `StageLookup` at all, see `test_no_history_and_skip_without_history_returns_the_payload_
    unchanged`'s refusing stub), one otherwise: a cascade stepping down through its own tiers
    is one ask re-put, not a second question — the same arithmetic `weft_retrieve.rerank`'s
    own `(0, 1)` uses for the identical reason.
    """

    config_model: ClassVar[type[ContextualQueryRewriteConfig]] = ContextualQueryRewriteConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 1)

    def __init__(self, config: ContextualQueryRewriteConfig | None = None) -> None:
        self._config = config if config is not None else ContextualQueryRewriteConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]:
        """`payload`, plus a standalone rewrite of the follow-up, or `payload` unchanged.

        The skip path returns `payload` itself — not a reconstruction of it — so
        `out.origin == in.origin` holds trivially there and the identity is one less thing a
        reader has to check. On the model path, the new `QuerySet` is built with
        `payload.origin` threaded through explicitly: see the module docstring for why that
        line is the one this plugin exists to get right.
        """
        if self._config.skip_without_history and not payload.history:
            return Produced(value=payload)

        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        values = StandaloneQuestionRequest(
            question=payload.origin.text,
            history=_render_history(payload.history, turns=self._config.history_turns),
        )
        rewritten = await execute(
            llm=llm,
            prompt=prompt,
            values=values,
            output=StandaloneQuestion,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(rewritten, Produced):
            # `on_failure` has one member today (`FAIL`): relaying the cascade's own outcome
            # *is* failing loudly, refusing a silent single-shot degrade to an unrewritten
            # question.
            # A second member, when a task needs one, adds a branch here — see
            # `weft_llm.payload.OnFailure`'s own docstring for why none exists yet.
            return rewritten

        derived = Query(
            text=rewritten.value.value.text,
            origin=QueryOrigin.DERIVED,
            produced_by=NAME,
            locale=payload.origin.locale,
            filter=payload.origin.filter,
        )
        queries = (*payload.queries, derived) if self._config.keep_question else (derived,)
        return Produced(
            value=QuerySet(
                origin=payload.origin,
                queries=queries,
                history=payload.history,
                ext=payload.ext,
            )
        )


#: The name this transform is registered and selectable under — see `weft_retrieve.register`.
HYDE_NAME = "hyde"


class HydeConfig(BaseModel):
    """`Hyde`'s `with:` config. Every field has a default, per this pack's own rule that a
    Phase 2 pack's settings must be constructible with none supplied — and per ledger 2.16's
    own line, which names three of these fields explicitly: sample count, query inclusion
    and failure behaviour are all configuration, never a number written into `run`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many hypothetical documents one cascade call is asked to write. `.phase2-design.
    #: md` §10's own row is explicit that no number is asserted in a docstring here — `10`
    #: §5 records that the paper's own count was not confirmed at source — so `3` is a
    #: starting default an operator retunes, never a claim about what the paper used.
    samples: int = Field(default=3, ge=1)
    #: Keep the user's own words in `queries` alongside the hypothetical documents, or
    #: replace them outright. The paper embeds the query's own embedding together with the
    #: hypothetical documents' before averaging. `True` is what carries that inclusion
    #: forward here — see `Hyde`'s own docstring for the one respect in which this plugin
    #: does not otherwise reproduce the paper's arithmetic.
    keep_question: bool = True
    prompt: str = Field(default=HYDE_DOCUMENT_NAME, min_length=1)
    role: str = Field(default="hyde", min_length=1)
    #: Which arms the *hypothetical* documents are searched on — never the arms `keep_
    #: question`'s literal query is searched on, which keeps its own default `channels=()`
    #: ("every channel this retriever offers") untouched. **HyDE is a claim about dense
    #: retrieval**: a hallucinated passage is a good probe for an embedding index and a bad
    #: one for lexical search, so the default is `(VECTOR,)` alone — this is what stops the
    #: hallucinated text from ever reaching a `TextSearch` arm.
    #:
    #: **Typed `tuple[str, ...]`, matching `Query.channels` itself, not `tuple[Channel,
    #: ...]`.** Unlike `vector-top-k`, which declares `needs_store = (VectorSearch,)` and
    #: is structurally unable to call anything else, `hyde` calls no store at all — it only
    #: stamps a tag for whichever retriever runs downstream. Closing this field to the
    #: two-member first-party enum would forbid aiming a hypothetical document at any arm a
    #: third-party store contributes (a `graph` search, per `Channel`'s own docstring), the
    #: exact axis `Query.channels` was opened up to support. A blank name is still refused,
    #: by `Query`'s own `_no_arm_is_nameless` validator, which runs when this tuple is
    #: written into every derived `Query.channels` below.
    channels: tuple[str, ...] = (Channel.VECTOR.value,)
    on_failure: OnFailure = OnFailure.FAIL


class Hyde:
    """Generates hypothetical answer documents and retrieves against them instead of the
    literal question. Satisfies `weft_retrieve.contract.QueryTransform` structurally.

    Luyu Gao, Xueguang Ma, Jimmy Lin, Jamie Callan, *Precise Zero-Shot Dense Retrieval
    without Relevance Labels*, arXiv:2212.10496 (2022), ACL 2023 pp. 1762-1777 — the paper
    this plugin's name is earned against, per `10` §1.4 and task 2.26's own naming audit.

    **What is implemented and what is not, named rather than left for a reader to
    discover.** The paper embeds several hypothetical documents *and* the query's own
    embedding, then averages all of them into one dense vector before search. This plugin
    does not average: each hypothetical document becomes its own `Query`, retrieved on its
    own `RankedList` and combined with the others only downstream, by a `Fuser` such as
    `reciprocal-rank-fusion` (ledger 2.18) — `hyde-fanout-rrf.yaml`'s own worked example.
    `keep_question` defaulting `True` is what carries the paper's inclusion of the literal
    query forward; fusion in place of averaging is the one respect in which this plugin
    earns its name without literally reproducing the paper's arithmetic, and it is recorded
    here so nobody has to diff this module against the paper to find it out.

    `cost_bound = (1, 1)`: always exactly one cascade call (`weft_prompts.cascade.execute`
    counts as one ask regardless of which of its three tiers answers, the same arithmetic
    `ContextualQueryRewrite`'s own docstring uses for its `(0, 1)`), and there is no skip
    path — HyDE is not conditioned on history or on anything else in the payload, so the
    floor and the ceiling are the same number.
    """

    config_model: ClassVar[type[HydeConfig]] = HydeConfig
    cost_bound: ClassVar[tuple[int, int]] = (1, 1)

    def __init__(self, config: HydeConfig | None = None) -> None:
        self._config = config if config is not None else HydeConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]:
        """`payload`'s own question, plus one derived `Query` per hypothetical document.

        `out.origin == in.origin` holds by construction: the `QuerySet` built below threads
        `payload.origin` through unchanged, never substituted for the hallucinated text this
        plugin itself generates. This is the query-path plugin ledger 2.4's own line names
        directly — the one whose loss of this property *is* the cross-encoder-scores-a-
        hallucination defect, because `hyde` is the transform that manufactures the
        hallucinated text a substitution would otherwise leak downstream.
        """
        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        values = HydeDocumentRequest(question=payload.origin.text, samples=self._config.samples)
        generated = await execute(
            llm=llm,
            prompt=prompt,
            values=values,
            output=HydeDocuments,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(generated, Produced):
            # `on_failure` has one member today (`FAIL`): relaying the cascade's own outcome
            # *is* failing loudly, exactly as `ContextualQueryRewrite.run` does for the same
            # stated reason — see that method's own comment on this line.
            return generated

        derived = tuple(
            Query(
                text=document,
                origin=QueryOrigin.DERIVED,
                produced_by=HYDE_NAME,
                locale=payload.origin.locale,
                filter=payload.origin.filter,
                channels=self._config.channels,
            )
            for document in generated.value.value.documents
        )
        queries = (*payload.queries, *derived) if self._config.keep_question else derived
        return Produced(
            value=QuerySet(
                origin=payload.origin,
                queries=queries,
                history=payload.history,
                ext=payload.ext,
            )
        )


#: The name this transform is registered and selectable under — see `weft_retrieve.register`.
STEP_BACK_NAME = "step-back"


class StepBackConfig(BaseModel):
    """`StepBack`'s `with:` config. Every field has a default, per this pack's own rule that a
    Phase 2 pack's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Not `STEP_BACK_NAME` — see `weft_retrieve.prompts.STEP_BACK_QUESTION_NAME`'s own
    #: docstring for why the plugin name and its default prompt name may not be the same
    #: string here, unlike the two-different-strings pattern `hyde`/`hyde-document` and
    #: `contextual-query-rewrite`/`standalone-question` already use for the identical reason.
    prompt: str = Field(default=STEP_BACK_QUESTION_NAME, min_length=1)
    role: str = Field(default="stepback", min_length=1)
    #: Keep the literal question in `queries` alongside the abstraction. `False` would leave
    #: only the step-back question searched for, which is not the paper's own design — Zheng
    #: et al. retrieve for *both* the abstract and the original question and ground the
    #: final answer in both contexts, which is exactly what `True` (the default) carries
    #: forward: both `Query`s reach the retriever, distinguishable by `Query.produced_by`
    #: (`""` for the literal one, `STEP_BACK_NAME` for the abstraction). `.phase2-design.md`
    #: §15's own "what is hard about this" names the limit honestly: `produced_by` does not
    #: survive into a `Passage` — fusion collapses `Candidates` into one `Ranking` and keeps
    #: only which *retriever* found a hit (`Passage.retrieved_by`), not which *query* did —
    #: so a document that wants the two contexts kept genuinely separate downstream needs
    #: two retriever positions, not this flag alone.
    keep_question: bool = True
    on_failure: OnFailure = OnFailure.FAIL


class StepBack:
    """Abstracts a question into a more general one and retrieves for both. Satisfies
    `weft_retrieve.contract.QueryTransform` structurally.

    Huaixiu Steven Zheng, Swaroop Mishra, Xinyun Chen, Heng-Tze Cheng, Ed H. Chi, Quoc V. Le,
    Denny Zhou, *Take a Step Back: Evoking Reasoning via Abstraction in Large Language
    Models*, ICLR 2024 (poster; OpenReview forum `3bq3jsvcQ1`), arXiv:2310.06117 — the paper
    this plugin's name is earned against, per `10` §1.4 and task 2.26's own naming audit.
    `10` §1.1's own entry for it records the specific failure this design avoids: a blocking
    call path that keeps the literal and abstract contexts in separate prompt slots can have
    a streaming twin that ends in a generic cited-context helper instead, discarding the
    split — so under streaming the strategy silently becomes dual-query retrieval with
    fusion and the paper's step 2 goes missing entirely. "One name, two techniques, and the
    weaker one is the interactive default."

    **This is task 2.17's own ledger line, made true by construction rather than by
    discipline.** There is no streaming twin here to keep in sync, because there is nowhere
    for one to live: `weft_llm.client.LLMClient.complete` — the one path `run` below reaches
    a model through — always calls `provider.stream(...)` and returns a decided
    `Outcome[Completion]` only once the stream is drained (`.phase2-design.md` §7, `01` →
    *Colour*'s streaming consequence, G6). A caller who wants to *see* tokens arrive attaches
    a `TokenSink`; `StepBack.run` neither knows nor cares whether one is attached, so the
    text it builds `StepBackQuestion` and the derived `Query` from is identical whichever
    way the answer arrived. `tests/unit/weft_retrieve/test_transforms.py`'s own equivalence
    test drives this exact method through two providers that answer with the same words —
    one in a single chunk, one word by word — and asserts the resulting `QuerySet`s are
    equal, which is the blocking-vs-streaming divergence above checked directly rather than
    reasoned about.

    `cost_bound = (1, 1)`: like `Hyde`, step-back is not conditioned on anything in the
    payload — there is no "nothing to step back from" the way a follow-up rewrite has
    nothing to rewrite without history — so the floor and the ceiling are the same number.
    """

    config_model: ClassVar[type[StepBackConfig]] = StepBackConfig
    cost_bound: ClassVar[tuple[int, int]] = (1, 1)

    def __init__(self, config: StepBackConfig | None = None) -> None:
        self._config = config if config is not None else StepBackConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]:
        """`payload`'s own question, plus one derived `Query` abstracting it.

        `out.origin == in.origin` holds by construction: the `QuerySet` built below threads
        `payload.origin` through unchanged, the same obligation every query-path plugin in
        this module carries — see the module docstring.
        """
        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        values = StepBackRequest(question=payload.origin.text)
        generated = await execute(
            llm=llm,
            prompt=prompt,
            values=values,
            output=StepBackQuestion,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(generated, Produced):
            # `on_failure` has one member today (`FAIL`): relaying the cascade's own outcome
            # *is* failing loudly, exactly as `ContextualQueryRewrite.run` and `Hyde.run` do
            # for the same stated reason — see `ContextualQueryRewrite.run`'s own comment on
            # this line.
            return generated

        derived = Query(
            text=generated.value.value.text,
            origin=QueryOrigin.DERIVED,
            produced_by=STEP_BACK_NAME,
            locale=payload.origin.locale,
            filter=payload.origin.filter,
        )
        queries = (*payload.queries, derived) if self._config.keep_question else (derived,)
        return Produced(
            value=QuerySet(
                origin=payload.origin,
                queries=queries,
                history=payload.history,
                ext=payload.ext,
            )
        )


def _render_history(history: tuple[Turn, ...], *, turns: int) -> str:
    """The last `turns` exchanges, oldest first, one line each — what a rewrite is judged
    against.

    Turning a `Turn` tuple into one string is this plugin's work rather than the prompt's:
    `weft_prompts.template` renders `${name}` over `string.Template`, which substitutes a
    field as its own text and cannot iterate — `weft_retrieve.rerank._offer`'s own reason for
    numbering its candidates itself, applied here to formatting history instead.
    """
    trimmed = history[-turns:] if turns > 0 else ()
    return "\n".join(f"{turn.role.value}: {turn.text}" for turn in trimmed)


#: The name this transform is registered and selectable under — see `weft_retrieve.register`.
MULTI_QUERY_NAME = "multi-query"


class ExpansionKind(StrEnum):
    """How `multi-query` varies a seed question — a rendering *strategy*, not wording.

    Nicholas J. Belkin, Paul Kantor, Edward A. Fox, Joseph A. Shaw, *Combining the evidence of
    multiple query representations for information retrieval*, Information Processing &
    Management 31(3), pp. 431-448, 1995, and George W. Furnas, Thomas K. Landauer, Louis M.
    Gomez, Susan T. Dumais, *The vocabulary problem in human-system communication*, CACM
    30(11), pp. 964-971, 1987 — the vocabulary mismatch that motivates `TERM` and `ASPECT`.
    `10` §1.1's own row on this technique names what a paraphrase-only prompt asks for
    instead: "the prompt … asks for *paraphrases*, which forbids the two things the expansion
    literature credits: new terms, and aspect coverage." `PARAPHRASE` still ships, for an
    operator who genuinely wants that narrower behaviour back; it is simply not what
    a fresh install runs.
    """

    #: Restate the question in different words, keeping its exact meaning — the narrower
    #: default this technique starts from, and the one member of this enum that cannot reach
    #: the other two axes.
    PARAPHRASE = "paraphrase"
    #: Ask about a different facet or sub-question of the same underlying question.
    ASPECT = "aspect"
    #: Use vocabulary the corpus might use instead of the asker's own — Furnas et al.'s
    #: vocabulary problem, addressed directly rather than left to a paraphrase to stumble into.
    TERM = "term"


#: What each `ExpansionKind` asks the model for, in the one language this build ships the
#: instruction in. Unlike `weft_retrieve.prompts.MultiQueryVariantsPrompt.texts`, which carries
#: a full bilingual system/user message, this clause is computed by the plugin and substituted
#: into `${expansion}` the same way `_render_history` computes `${history}` — a rendering
#: choice, not the model-facing question itself. Recorded as this build's smallest defensible
#: choice rather than left silent: a locale-keyed table for three short clauses would be a
#: second, un-reviewed translation surface for a three-word technical distinction, and
#: `hedge-phrases` (ledger 2.20's sibling contract) is where a locale-keyed *table as
#: configuration* is this pack's actual answer to that need, not a private dict here.
_EXPANSION_INSTRUCTIONS: dict[ExpansionKind, str] = {
    ExpansionKind.PARAPHRASE: ("restating it in different words while keeping its exact meaning"),
    ExpansionKind.ASPECT: (
        "each covering a different facet or sub-question of the same underlying question, "
        "not just a reworded copy"
    ),
    ExpansionKind.TERM: (
        "each using different vocabulary a source document might use for the same "
        "underlying question — synonyms and adjacent terms, not just a reworded copy"
    ),
}


class MultiQueryConfig(BaseModel):
    """`MultiQuery`'s `with:` config. Every field has a default, per this pack's own rule that
    a Phase 2 pack's settings must be constructible with none supplied — and per ledger 2.18a's
    own row, which names every one of these as configuration: how many variants, which
    expansion strategy, whether near-duplicates survive, and which existing queries are seeds.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many alternative queries one cascade call is asked to write **per matched seed**.
    variants: int = Field(default=4, ge=1)
    #: Keep each expanded seed in `queries` alongside its own variants, or replace it. `False`
    #: is what an operator who trusts the fan-out reaches for, so a retriever downstream is not
    #: asked to search the seed's own wording a second time.
    keep_question: bool = True
    expansion: ExpansionKind = ExpansionKind.ASPECT
    #: Drop a variant whose normalised text (whitespace-collapsed, casefolded) duplicates the
    #: seed's own text or another kept query's — `10` §1.1's own finding: "near-duplicate
    #: queries also weaken the fusion, whose benefit comes from rankings that disagree." `False`
    #: keeps every variant the model returned, even an exact repeat of the question it was
    #: asked to vary.
    require_distinct: bool = True
    #: Which existing queries this transform treats as seeds to expand, matched against each
    #: `Query.produced_by`. The default, `("",)`, selects only the literal question — never
    #: what an earlier transform already derived, which is what lets `hyde` then `multi-query`
    #: compose without the second stage re-expanding the first stage's own output
    #: (`.phase2-design.md`'s own worked example, `hyde-fanout-rrf.yaml`).
    expand_origins: tuple[str, ...] = ("",)
    prompt: str = Field(default=MULTI_QUERY_VARIANTS_NAME, min_length=1)
    role: str = Field(default="fanout", min_length=1)


class MultiQuery:
    """Fans one or more seed questions out into several alternative search queries, retrieved
    independently and combined downstream by a `Fuser`. Satisfies `weft_retrieve.contract.
    QueryTransform` structurally.

    Belkin, Kantor, Fox & Shaw, *Combining the evidence of multiple query representations for
    information retrieval*, Information Processing & Management 31(3), pp. 431-448, 1995 — the
    idea this plugin is named after: several representations of one question, retrieved and
    combined, outperform any one of them alone. Furnas, Landauer, Gomez & Dumais, *The
    vocabulary problem in human-system communication*, CACM 30(11), pp. 964-971, 1987 — the
    problem `ExpansionKind.TERM` and `.ASPECT` exist to reach past what a paraphrase cannot.
    Jagerman, Zhuang, Qin, Wang & Bendersky, *Query Expansion by Prompting Large Language
    Models*, arXiv:2305.03653, 2023 — generating the alternatives through a model call, the
    mechanism `run` (below) implements.

    **This is task 2.18's own claim, made true by construction rather than by two
    implementations.** `weft_retrieve.contract.Fuser`'s own docstring states it structurally:
    "fan-in is expressed in the type, not by a combinator … hybrid retrieval and query fan-out
    are the same shape here, because multiplicity is uniform in `Candidates`." This plugin is
    the half of that claim that is a `QueryTransform` — one query becomes several — and
    `weft_retrieve.fusion.ReciprocalRankFusion` (ledger 2.18b) is the one `Fuser` implementation
    that fuses what this produces exactly as it fuses a hybrid retriever's multiple channels,
    with no branch anywhere asking which kind of multiplicity it was handed.

    **Batched, not one call per seed.** `cost_bound = (1, 1)` regardless of how many queries
    `expand_origins` matches: one cascade call offers every matched seed by index
    (`_offer_seeds`) and one structured answer is read back keyed to those same indices
    (`_groups_by_index`) — the same numbered-offer-and-parse shape `weft_retrieve.rerank._offer`
    / `_scores_by_index` use for the identical reason (`string.Template` cannot iterate). See
    the module docstring for why this is also the reason `multi-query` does not share `Hyde`'s
    and `StepBack`'s common base: neither of them ever has more than one seed to batch.

    **No seed matched is a refusal, not a silent no-op.** `cost_bound`'s floor of one describes
    a *successful* run; a document whose `expand_origins` matches nothing in a given `QuerySet`
    is a mismatch between the document and the queries actually flowing through it, and `run`
    names that mismatch rather than either skipping silently (which would make the floor of
    `cost_bound` false) or asking a model to expand zero seeds (which is not a request that
    means anything).
    """

    config_model: ClassVar[type[MultiQueryConfig]] = MultiQueryConfig
    cost_bound: ClassVar[tuple[int, int]] = (1, 1)

    def __init__(self, config: MultiQueryConfig | None = None) -> None:
        self._config = config if config is not None else MultiQueryConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]:
        """`payload`, with every seed matching `expand_origins` expanded into `variants`
        alternative queries.

        `out.origin == in.origin` holds by construction: the `QuerySet` built below threads
        `payload.origin` through unchanged, the same obligation every query-path plugin in
        this module carries — see the module docstring.
        """
        seeds = tuple(
            query for query in payload.queries if query.produced_by in self._config.expand_origins
        )
        if not seeds:
            present = sorted({query.produced_by for query in payload.queries})
            return Failed(
                reason=(
                    f"'{MULTI_QUERY_NAME}' expands queries whose produced_by is one of "
                    f"{list(self._config.expand_origins)}, and none of this QuerySet's "
                    f"{len(payload.queries)} quer{'y' if len(payload.queries) == 1 else 'ies'} "
                    f"matched — produced_by present here: {present}. Widen expand_origins to "
                    f"cover one of them, or drop this stage from the document."
                )
            )

        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        values = MultiQueryVariantsRequest(
            questions=_offer_seeds(seeds),
            variants=self._config.variants,
            expansion=_EXPANSION_INSTRUCTIONS[self._config.expansion],
        )
        generated = await execute(
            llm=llm,
            prompt=prompt,
            values=values,
            output=MultiQueryVariants,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(generated, Produced):
            # `on_failure` has no field here yet — the same one-member arithmetic every other
            # transform in this module uses; see `ContextualQueryRewrite.run`'s own comment.
            return generated

        groups = _groups_by_index(generated.value.value, offered=len(seeds))
        if isinstance(groups, Failed):
            return groups

        seen: set[str] = (
            {_normalised(query.text) for query in payload.queries}
            if self._config.require_distinct
            else set()
        )
        derived: list[Query] = []
        for index, seed in enumerate(seeds):
            for text in groups[index]:
                if self._config.require_distinct:
                    key = _normalised(text)
                    if key in seen:
                        continue
                    seen.add(key)
                derived.append(
                    Query(
                        text=text,
                        origin=QueryOrigin.DERIVED,
                        produced_by=MULTI_QUERY_NAME,
                        locale=seed.locale,
                        filter=seed.filter,
                        channels=seed.channels,
                    )
                )

        kept = (
            payload.queries
            if self._config.keep_question
            else tuple(
                query
                for query in payload.queries
                if query.produced_by not in self._config.expand_origins
            )
        )
        return Produced(
            value=QuerySet(
                origin=payload.origin,
                queries=(*kept, *derived),
                history=payload.history,
                ext=payload.ext,
            )
        )


def _offer_seeds(seeds: tuple[Query, ...]) -> str:
    """The seed questions, one per line, numbered by the index a group answers back against.

    Mirrors `weft_retrieve.rerank._offer`'s own numbering, for the same reason: the numbering
    is written here and read back in `_groups_by_index`, so the two cannot disagree about what
    `[1]` meant.
    """
    return "\n".join(f"[{index}] {seed.text}" for index, seed in enumerate(seeds))


def _groups_by_index(
    variants: MultiQueryVariants, *, offered: int
) -> dict[int, tuple[str, ...]] | Failed:
    """One variant group per offered seed index, or a `Failed` naming exactly how the set was
    wrong.

    Mirrors `weft_retrieve.rerank._scores_by_index`'s own three-way refusal, applied to groups
    instead of scores: an index nobody offered means the model invented a seed, a missing index
    means it skipped one, and a repeated index means it answered for the same seed twice.
    """
    groups: dict[int, tuple[str, ...]] = {}
    unknown: list[int] = []
    repeated: list[int] = []
    for group in variants.groups:
        if group.index >= offered:
            unknown.append(group.index)
        elif group.index in groups:
            repeated.append(group.index)
        else:
            groups[group.index] = group.variants
    missing = [index for index in range(offered) if index not in groups]
    if unknown or repeated or missing:
        return Failed(
            reason=(
                f"'{MULTI_QUERY_NAME}' offered {offered} seed question(s) and asked for one "
                f"answer each, and the model did not answer that: index/indices "
                f"{unknown or 'none'} were never offered, {repeated or 'none'} were answered "
                f"more than once, and {missing or 'none'} were not answered at all."
            )
        )
    return groups


def _normalised(text: str) -> str:
    """`text`, whitespace-collapsed and casefolded — what `require_distinct` compares by.

    Exact after normalisation, not fuzzy: a genuine near-duplicate detector would need a
    similarity model this plugin resolves no service for, and `10` §1.1's own finding is
    about *near-duplicate* queries specifically arising from a model restating the same words
    with different spacing or capitalisation, which this catches without one.
    """
    return " ".join(text.split()).casefold()
