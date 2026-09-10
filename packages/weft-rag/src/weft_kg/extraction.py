"""`llm-facts` — a chunk's facts and mentions become nodes, once. Ledger **11.7**.

**An `Expander`, never an `Enhancer`.** `weft_index.contract.Expander`'s own distinction: every
node handed in continues, unchanged, into the output, and new nodes are *added* beside it, each
one `parent.derive(content=...)` so its id is its own content digest and its `Lineage` names the
chunk it came from. An `Enhancer` would instead attach a fact to the node it was handed and leave
its own id and content untouched — but a triple and a mention are each their own retrievable,
embeddable, cascade-deletable thing, not a fact *about* the chunk, so they must be nodes of their
own rather than ext data riding the chunk that named them.

**The tally is the run's, never the chunk's.** `weft_kg.payload.ExtractionTally`'s own docstring
states the invariant this stage builds it under; `weft_index.payload.RaptorFacts.
clusters_found`/`clusters_summarised` is the precedent it follows — a chunk whose every candidate
was dropped derives no node at all, so a per-chunk tally would have nowhere to ride and those
drops would vanish from anything a reader could find. One `ExtractionTally` is built after every
node in the call has been attempted and attached, unchanged, to every derived node the call
produced — never to a payload node, because attaching ext to what was handed in is what defines
an `Enhancer`, and this stage is an `Expander`.

**One model call per node, never one for the batch** — `weft_index.hypothetical_questions`'s own
argument, unchanged: batching several chunks into one numbered prompt makes the model's attention
to any one passage a function of how many chunks happened to land in this run, which is not a
property this stage's own prompt (`weft_kg.prompts`) asks for. The fan-out is bounded by
`asyncio.Semaphore(max_concurrent_nodes)` held across the whole call and one `asyncio.gather`,
copied in shape from that same module: a semaphore rather than chunked waves, because chunking
would run the batch in lockstep and let one slow completion idle every other permit until its own
wave finished.

**The five-rule filter this stage calls is carried prior work.** `weft_kg.atomicity.
non_atomic_reason` lives under `NOTICE` case 2, from the project owner's own `graph-study`; this
module is what dispatches to it, on both endpoints of every candidate, and what does everything
that filter does not: the row-shape checks, the per-node duplicate and over-limit checks, and the
tally those verdicts feed.

**What the filter does not catch, measured rather than guessed.** A real run through the shipped
binary on 2026-09-09 — three sentences, one model, eight facts kept and nothing dropped — produced
`the work`, `an existing tree`, `the two ranked lists` and `the Warsaw Institute` as entities
beside `adRAP`, `Chucri` and `Reciprocal Rank Fusion`. None of the five rules fires on any of
them: the trailing-stopword rule refuses a name that *ends* in a function word, and says nothing
about one that begins with a determiner. So this stage over-generates on generic noun phrases the
passage happened to make the object of a verb, and the graph gets low-value nodes that no later
question will name.

That is recorded rather than repaired here, for two reasons. A sixth rule would not be carried
work, and the five-rule filter is what this task's own line specifies; and a leading-determiner
rule is exactly the kind of judgement that should be made against a real corpus's mention sets
rather than against one demonstration, which is what `11.8`'s resolution pass is the first thing
in this pack to see. `10` §1.2's row for this plugin states the same limitation where a reader
choosing a rung will meet it.

**Ledger `11.11` adds a third layer, on top of the five-rule filter above: constrain, then
verify, against a curated schema.** `11.7`'s filter refuses a candidate on *shape* — a name that
is a clause, an equation, a citation. A curated schema (`weft_kg.schema.GraphSchema`) refuses on
*structure*: an operator has said which `(source_type, predicate, target_type)` arrangements this
corpus admits, and `Method wrote Person` uses nothing an operator did not approve while saying
something impossible — that module's own docstring has the worked example. **Constrain** means
`weft_kg.prompts.render_allowed` hands the model the admitted arrangements alongside the passage,
so most of a wrong answer never gets typed at all; **verify** means `_verdict` below drops
whatever the model returns anyway, under `DropReason.OFF_SCHEMA`, counted by the same
`ExtractionTally` machinery every other rule already uses. Either half alone is weaker than both:
constraining without verifying trusts a model that may not comply, and verifying without
constraining spends a call to throw most of it away. When `[packs.graph] schema_file` is unset —
still the ordinary case — this stage asks and keeps exactly as it did before this task: `schema`
is `None`, `render_allowed` returns `""`, and `_verdict` never reaches the new check.

**The schema is loaded once per `run`, never per node.** A curated schema file is read from disk
and does not change between the first node this call examines and the last, so reading it once
and passing the parsed `GraphSchema` down is the same amortisation `ExtractFactsPrompt` itself
already gets from being constructed once outside the fan-out below.
"""

import asyncio
from collections.abc import Sequence
from itertools import count
from pathlib import Path
from typing import ClassVar, NamedTuple, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kg.atomicity import MAX_ENTITY_WORDS, non_atomic_reason
from weft_kg.payload import (
    DroppedCandidates,
    DropReason,
    ExtractedFact,
    ExtractionTally,
    MentionedEntity,
)
from weft_kg.prompts import (
    ExtractFactsPrompt,
    ExtractFactsRequest,
    ProposedFact,
    ProposedFacts,
    render_allowed,
)
from weft_kg.schema import GraphSchema, load_schema
from weft_kg.store import GraphSettings
from weft_llm.contract import LLM
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt

#: The name this plugin is registered and selectable under — see `weft_kg.register`.
NAME = "llm-facts"


class _NodeExtraction(NamedTuple):
    """What one node's extraction produced, named rather than positional.

    `weft_prompts.cascade._tier_native`'s own rule, one pack over: a return whose meaning
    would otherwise live only in the reader's head gets names instead. Four values unpacked
    positionally at one call site is exactly the shape that reads wrong the first time
    somebody reorders it, and `candidates` and `kept` are two ints of the same type sitting
    next to each other.
    """

    derived: tuple[Node, ...]
    candidates: int
    kept: int
    dropped: tuple[DropReason, ...]


class LlmFactsConfig(BaseModel):
    """`llm-facts`'s `with:` config. Every field has a default, per this pack's own rule that a
    stage's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The ceiling this stage asks the model for and enforces itself — `weft_kg.prompts`'s own
    #: docstring on why the prompt asks for a ceiling rather than an exact count.
    max_facts_per_node: int = Field(default=12, ge=1)
    #: The same field name and the same default `hypothetical-questions` and `raptor` already
    #: carry for this bound — what a provider tolerates is an operator's fact, not this plugin's,
    #: and three stages fanning out against one configured provider should not disagree about it
    #: by accident.
    max_concurrent_nodes: int = Field(default=8, ge=1)
    #: `weft_kg.atomicity.non_atomic_reason`'s own word cap, exposed here rather than fixed —
    #: requirement 6's rule that the one number a filter turns on is an operator's, not a
    #: constant.
    max_entity_words: int = Field(default=MAX_ENTITY_WORDS, ge=1)
    role: str = Field(default="index", min_length=1)


class LlmFactExtractor:
    """Derives fact and mention nodes from every node it is handed. Satisfies `Expander`
    structurally.
    """

    config_model: ClassVar[type[LlmFactsConfig]] = LlmFactsConfig

    def __init__(
        self, config: LlmFactsConfig | None = None, *, settings: GraphSettings | None = None
    ) -> None:
        self._config = config if config is not None else LlmFactsConfig()
        # `settings` keyword-only and last — deliberately unlike `GraphStore(settings, config)`.
        # `GraphStore` cannot exist without a DSN; this stage must stay constructible with
        # nothing, because a document may name `llm-facts` in a project with no
        # `[packs.graph] schema_file` — or no `[packs.graph]` table at all.
        self._settings = settings if settings is not None else GraphSettings()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        if not payload:
            return NothingToProduce(reason="no nodes to extract facts from")

        # Loaded once for the whole call, never per node — see the module docstring's own note —
        # and **off the event loop**. `load_schema` opens a file, and every contract method here is
        # `async`: reading it inline blocks the loop thread, which the registration seam detects
        # and refuses (fitness function 7(b)). **Found by running the binary at `11.11`**, not by
        # any test in this pack — the unit tests construct this class directly and never cross the
        # seam that watches for it, which is the gap `CLAUDE.md`'s "a green gate is not a working
        # binary" names. `asyncio.to_thread` is the offload that message itself recommends.
        schema: GraphSchema | None = (
            await asyncio.to_thread(load_schema, Path(self._settings.schema_file))
            if self._settings.schema_file
            else None
        )
        llm = ctx.require(LLM)
        # `ExtractFactsPrompt` is constructed directly rather than resolved through
        # `StageLookup` — `weft_kg.prompts`' own module docstring has why the ingest path offers
        # no by-name lookup — and this stage is therefore the first in the tree to hand a
        # concrete prompt class to `execute` without a generic standing in between.
        #
        # **The cast is not this class falling short; no prompt in this tree satisfies `Prompt`
        # to a type checker.** Measured 2026-09-09: `_: Prompt = PassageRelevancePrompt()` fails
        # `reportAssignmentType` with *"version is not present"*, and so would every other
        # registered prompt. `Prompt.version` is declared under `if TYPE_CHECKING:` and assigned
        # to the Protocol object after its own class body — the two-audience pattern every
        # contract here shares — so it is a member pyright requires and `__protocol_attrs__`
        # excludes, which is what keeps `isinstance` honest. `StageLookup.build_capability[T]`
        # infers `T = Prompt` from its call site and never checks the concrete class, so every
        # existing caller is hidden from this. The runtime check the cast stands in for does
        # pass: `Prompt` is `@runtime_checkable` and `isinstance(ExtractFactsPrompt(), Prompt)`
        # is `True`. Whether the pattern itself should change is a question about every contract
        # in the tree and belongs to G9, not to this stage.
        prompt = cast(Prompt, ExtractFactsPrompt())
        limit = asyncio.Semaphore(self._config.max_concurrent_nodes)

        async def _bounded(node: Node) -> _NodeExtraction:
            async with limit:
                return await self._facts_for(node, llm=llm, prompt=prompt, ctx=ctx, schema=schema)

        results = await asyncio.gather(*(_bounded(node) for node in payload))

        derived: list[Node] = []
        total_candidates = 0
        total_kept = 0
        drop_counts: dict[DropReason, int] = {}
        for result in results:
            derived.extend(result.derived)
            total_candidates += result.candidates
            total_kept += result.kept
            for reason in result.dropped:
                drop_counts[reason] = drop_counts.get(reason, 0) + 1

        tally = ExtractionTally(
            candidates=total_candidates,
            kept=total_kept,
            dropped=tuple(
                DroppedCandidates(reason=reason, count=drop_counts[reason])
                for reason in sorted(drop_counts, key=lambda reason: reason.value)
            ),
        )
        derived = [node.with_ext(tally) for node in derived]
        return Produced(value=(*payload, *derived))

    async def _facts_for(
        self, node: Node, *, llm: LLM, prompt: Prompt, ctx: Context, schema: GraphSchema | None
    ) -> _NodeExtraction:
        """This one node's derived nodes, its candidate count, its kept-fact count and drops.

        Degrades to an empty extraction when the cascade could not produce a typed answer — the
        node itself still returns unchanged in `run`'s own output, and this contributes nothing
        to the run's tally: a model in a bad mood is not a candidate the operator asked about.
        """
        answered = await execute(
            llm=llm,
            prompt=prompt,
            values=ExtractFactsRequest(
                passage=node.content,
                max_facts=self._config.max_facts_per_node,
                allowed=render_allowed(schema, locale=ctx.locale),
            ),
            output=ProposedFacts,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(answered, Produced):
            return _NodeExtraction(derived=(), candidates=0, kept=0, dropped=())

        proposed = answered.value.value.facts
        kept: list[ProposedFact] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        reasons: list[DropReason] = []
        for candidate in proposed:
            verdict = _verdict(
                candidate,
                kept=seen,
                max_words=self._config.max_entity_words,
                limit=self._config.max_facts_per_node,
                already_kept=len(kept),
                schema=schema,
            )
            if verdict is not None:
                reasons.append(verdict)
                continue
            stripped = _stripped(candidate)
            seen.add(_key(stripped))
            kept.append(stripped)

        schema_id = schema.identity if schema is not None else ""
        ordinal = count()
        fact_nodes = tuple(
            node.derive(
                content=f"{fact.source} {fact.predicate} {fact.target}",
                media_type=MediaType.TEXT,
                ordinal=next(ordinal),
            ).with_ext(
                ExtractedFact(
                    source=fact.source,
                    source_type=fact.source_type,
                    predicate=fact.predicate,
                    target=fact.target,
                    target_type=fact.target_type,
                    schema_id=schema_id,
                )
            )
            for fact in kept
        )

        mentioned: dict[str, str] = {}
        for fact in kept:
            mentioned.setdefault(fact.source, fact.source_type)
            mentioned.setdefault(fact.target, fact.target_type)
        mention_nodes = tuple(
            node.derive(content=name, media_type=MediaType.TEXT, ordinal=next(ordinal)).with_ext(
                MentionedEntity(name=name, entity_type=mentioned[name])
            )
            for name in sorted(mentioned)
        )

        return _NodeExtraction(
            derived=(*fact_nodes, *mention_nodes),
            candidates=len(proposed),
            kept=len(kept),
            dropped=tuple(reasons),
        )


def _verdict(
    candidate: ProposedFact,
    *,
    kept: set[tuple[str, str, str, str, str]],
    max_words: int,
    limit: int,
    already_kept: int,
    schema: GraphSchema | None,
) -> DropReason | None:
    """The first rule this candidate fails, tried in the order `11.7`'s brief fixes, extended by
    `11.11`'s schema check.

    **Placed after the shape rules and before the batch-level ones, deliberately.** A schema
    arrangement is only worth checking once both endpoints are known to be well-shaped rows
    rather than a blank field or an unbounded fragment `non_atomic_reason` would refuse anyway —
    checking it first would report `OFF_SCHEMA` for a candidate that was never going to survive
    regardless. And it has to come *before* `DUPLICATE`/`OVER_LIMIT`: those two are facts about
    the batch this candidate arrived in, and an off-schema candidate must consume neither the
    duplicate set nor the per-node limit — dropping it after would let an arrangement the
    operator refused still crowd out an admissible fact competing for the same ceiling.
    """
    fields = (
        candidate.source,
        candidate.source_type,
        candidate.predicate,
        candidate.target,
        candidate.target_type,
    )
    if any(not field.strip() for field in fields):
        return DropReason.INCOMPLETE_ROW
    for endpoint in (candidate.source, candidate.target):
        reason = non_atomic_reason(endpoint, max_words=max_words)
        if reason is not None:
            return reason
    if schema is not None and not schema.admits(
        source_type=candidate.source_type,
        predicate=candidate.predicate,
        target_type=candidate.target_type,
    ):
        return DropReason.OFF_SCHEMA
    if _key(_stripped(candidate)) in kept:
        return DropReason.DUPLICATE
    if already_kept >= limit:
        return DropReason.OVER_LIMIT
    return None


def _stripped(candidate: ProposedFact) -> ProposedFact:
    return ProposedFact(
        source=candidate.source.strip(),
        source_type=candidate.source_type.strip(),
        predicate=candidate.predicate.strip(),
        target=candidate.target.strip(),
        target_type=candidate.target_type.strip(),
    )


def _key(fact: ProposedFact) -> tuple[str, str, str, str, str]:
    return (fact.source, fact.source_type, fact.predicate, fact.target, fact.target_type)


__all__ = ["NAME", "LlmFactExtractor", "LlmFactsConfig"]
