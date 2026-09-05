"""`cited-answer` — the one `Generator` this task ships. `Stage[Passages, Answer]`.

Task **2.9**, `docs/build-ledger.md`: "an answer carries citations a reader can follow
back to a passage — not to a document, and not to a paraphrase." `weft_generate.payload.
Answer._citations_resolve` already makes the *shape* of that unconstructable to violate;
this module is what builds an `Answer` in the first place, and what keeps the marker a
model writes and the passage `Answer.used` records honest with each other.

**One plugin, two behaviours, configuration — `01` requirement 6's second clause instead
of a second generator name.** `when_no_evidence` decides what happens when `Passages` is
empty: `REFUSE` answers `Answer(stance=NOT_IN_CORPUS)` and calls no model at all — the
line `.phase2-design.md` §3 states outright, "`cited-answer` is the stage that turns
empty evidence into `Answer(stance=NOT_IN_CORPUS)`" — and `ANSWER_FROM_MEMORY` asks the
same prompt with no passages shown, which is what `no-retrieval`'s own pipeline sets.

**Citations are extracted from the completion, never asked for as a second structured
field.** `docs/04-reference-inventory.md`'s corrected `PriorCitationManager` row records the
reference's second responsibility as "extract which sources were actually cited" through
four ordered, language-specific regexes over freeform text. This build does not need
them: `weft_retrieve.payload.Passages` already assigns every offered passage an exact,
known label before a model ever sees one, so "which sources were cited" is answered by a
literal substring search for `[label]` per offered passage — no language heuristic, and
no way for the search to disagree with what was actually shown, because the label
searched for and the label shown are the same string. This also settles a question the
reference's approach could not: a model is asked for prose, not for a second list of markers
that could name a passage never offered or drop one it clearly used — the two ways
`weft_retrieve.rerank`'s judgement-set check refuses a reranker's reply, in a shape this
plugin cannot have because it never asks for that second list.

**Page numbers are `weft_generate.page.page_for`'s, not this module's.** Every citation
this plugin builds carries whatever that function resolves for the cited node — `None`
when nothing in the pipeline attached the two facts it needs. See that module for why
`cited_answer.py` imports neither `weft_chunk` nor `weft_pdf` to get there.

**Task 2.31's own obligation, closed here — and it turned out to reach further than a
`Citation` field.** `.phase2-findings.md` §11: "a hit on any of them resolves through
lineage to the one parent chunk... which is what makes task 2.9's citations able to follow
back to a passage rather than to a paraphrase of one." The first attempt patched
`Citation.node_id` alone and `Answer._citations_resolve` refused it outright: that
validator requires a citation's `node_id` to be the id of the very passage `used` records
under the marker naming it, by construction, so a `Citation` cannot point at a different
node than the `Passage` it is paired with — the renumbering bug it exists to make
unconstructable is exactly the shape a citation-only patch would have produced. So the
resolution moves one step earlier: `_resolved_to_citable`, below, substitutes a
representation's own node for the one it stands in for — via `weft_generate.
representation.citable_nodes`, the same duck-typed, no-new-dependency read `page_for`
already sets a precedent for — on `offered` itself, before it becomes `_offer`'s prompt
text, before it becomes `Answer.used`, and before a `Citation` is built from it. One
substitution, three consumers agreeing, rather than three places that could disagree.
This also closes the corollary gap for free: a model asked to answer from a retrieved
question's own wording would have been shown that wording as "evidence"; now it reads the
real passage the representation stands in for, the same as everything else it is offered.

**What this does not do.** Two representations of the *same* parent occupying two offered
slots still occupy two — this substitutes identity, node for node, and applies no score
policy across slots. Collapsing that duplication before it reaches this stage at all is
`10` §1.2's `collapse-to-parent` row (ledger task 2.33), which owns a `Ranking`-level
merge policy this plugin's own 1:1 substitution neither needs nor should guess at.
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_generate.page import page_for
from weft_generate.payload import Answer, AnswerStance, Citation
from weft_generate.prompts import ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsRequest
from weft_generate.representation import citable_nodes
from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome, Produced, SourceId
from weft_llm.contract import LLM
from weft_prompts.contract import Prompt
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Passage, Passages
from weft_store.contract import NodeStore, Scored

#: The name this generator is registered and selectable under — see `weft_generate.register`.
NAME = "cited-answer"


class WhenNoEvidence(StrEnum):
    """What `cited-answer` does when `Passages.passages` is empty. `Enum`, project rule."""

    #: `Answer(stance=NOT_IN_CORPUS)`, no model call — the default, and what "the corpus
    #: does not contain it" means when nothing was ever retrieved to check.
    REFUSE = "refuse"
    #: Ask the model anyway, with no passages shown — what `no-retrieval`'s own pipeline
    #: sets, because the null-retrieval branch is a deliberate choice to answer from
    #: parametric memory (Roberts, Raffel & Shazeer 2020), not a retrieval failure.
    ANSWER_FROM_MEMORY = "answer_from_memory"


class CitedAnswerConfig(BaseModel):
    """`CitedAnswer`'s `with:` config. Every field has a default, per this pack's own rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(default=ANSWER_WITH_CITATIONS_NAME, min_length=1)
    role: str = Field(default="generate", min_length=1)
    max_passages: int = Field(default=8, ge=1)
    #: Presents the offered evidence grouped under the retriever that found it, rather
    #: than as one flat numbered list — useful once a fan-out or hybrid pipeline feeds
    #: this stage passages `Passage.retrieved_by` disagrees about.
    group_by_retriever: bool = False
    when_no_evidence: WhenNoEvidence = WhenNoEvidence.REFUSE


class CitedAnswer:
    """Turns packed, labelled evidence into a cited answer. Satisfies `contract.Generator`
    structurally.

    `cost_bound = (0, 1)` — zero when evidence is empty and `when_no_evidence=REFUSE`,
    because `run` returns before resolving anything; one otherwise, the same arithmetic
    `weft_retrieve.rerank.LlmRerank` states for its own single-call ceiling.
    """

    config_model: ClassVar[type[CitedAnswerConfig]] = CitedAnswerConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 1)

    def __init__(self, config: CitedAnswerConfig | None = None) -> None:
        self._config = config if config is not None else CitedAnswerConfig()

    async def run(self, payload: Passages, ctx: Context) -> Outcome[Answer]:
        """Ask under `origin` alone, never a derived query — `QuerySet.origin`'s own rule,
        applied at the last stage on the query path rather than only the first.
        """
        if not payload.passages:
            if self._config.when_no_evidence is WhenNoEvidence.REFUSE:
                return Produced(
                    value=Answer(
                        origin=payload.origin,
                        text="",
                        citations=(),
                        used=(),
                        stance=AnswerStance.NOT_IN_CORPUS,
                        answered_by=NAME,
                    )
                )
            offered: tuple[Passage, ...] = ()
        else:
            offered = await _resolved_to_citable(
                payload.passages[: self._config.max_passages], ctx=ctx
            )

        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        request = AnswerWithCitationsRequest(
            question=payload.origin.text,
            passages=_offer(offered, group_by_retriever=self._config.group_by_retriever),
        )
        rendered = await prompt.render(request, ctx)
        if not isinstance(rendered, Produced):
            # A prompt with nothing to ask is relayed exactly as it answered — the same
            # rule `weft_prompts.cascade.execute` and `weft_retrieve.rerank` both take.
            return rendered

        completion = await llm.complete(rendered.value, role=self._config.role, ctx=ctx)
        if not isinstance(completion, Produced):
            return completion
        text = completion.value.text

        citations = await _citations_for(offered, text=text, ctx=ctx)
        return Produced(
            value=Answer(
                origin=payload.origin,
                text=text,
                citations=citations,
                used=offered,
                stance=AnswerStance.ANSWERED,
                answered_by=NAME,
            )
        )


def _offer(passages: tuple[Passage, ...], *, group_by_retriever: bool) -> str:
    """The offered evidence as one string, numbered by each passage's own `label`.

    Never a re-derived index — see `weft_generate.prompts`' module docstring for why that
    is the one thing this function must not do.
    """
    if not passages:
        return ""
    if not group_by_retriever:
        return "\n\n".join(f"[{passage.label}] {passage.node.content}" for passage in passages)
    groups: dict[str, list[Passage]] = {}
    for passage in passages:
        groups.setdefault(passage.retrieved_by, []).append(passage)
    blocks = [
        f"From {retriever}:\n"
        + "\n\n".join(f"[{passage.label}] {passage.node.content}" for passage in group)
        for retriever, group in sorted(groups.items())
    ]
    return "\n\n".join(blocks)


async def _resolved_to_citable(
    offered: tuple[Passage, ...], *, ctx: Context
) -> tuple[Passage, ...]:
    """`offered`, with every representation's own node substituted for the one it stands in
    for — see the module docstring for why this runs once, here, rather than inside
    `_citations_for` alone. `rank`, `retrieved_by` and `label` are untouched; only which
    node the passage carries changes, via a fresh `Scored` around the resolved node and the
    passage's own original `score`.
    """
    if not offered:
        return offered
    store = ctx.require(NodeStore)
    resolved = await citable_nodes((passage.node for passage in offered), store=store)
    return tuple(
        passage
        if resolved[passage.node.id] is passage.node
        else Passage(
            scored=Scored(value=resolved[passage.node.id], score=passage.score),
            rank=passage.rank,
            retrieved_by=passage.retrieved_by,
            label=passage.label,
        )
        for passage in offered
    )


async def _citations_for(
    offered: tuple[Passage, ...], *, text: str, ctx: Context
) -> tuple[Citation, ...]:
    """One `Citation` per offered passage whose own bracketed label appears in `text`.

    A literal substring search, not a regex over prose: the label searched for is the
    exact string shown to the model, so there is nothing for a language-specific pattern
    to get right or wrong that this search does not already get right by construction.
    `offered` has already been resolved to citable nodes by `run`, so `passage.node` here
    is always the node a `Citation` should name.
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
    """`node`'s one source, or `None` when it has none or more than one to choose from.

    Zero is `Node.synthetic`'s legitimate root case — `Citation.source_id`'s own docstring.
    More than one is a summary node (`Node.combine`): naming one of several documents as
    *the* source would be a citation that misattributes a claim to a document it might not
    actually rest on, which is worse than a citation that says only "this is a summary".
    """
    sources = node.lineage.sources
    return next(iter(sources)) if len(sources) == 1 else None
