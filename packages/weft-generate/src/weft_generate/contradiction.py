"""`contradiction-check` — the one `Generator` this task ships. `Stage[Passages, Answer]`.

Task **2.22**, `docs/build-ledger.md`: "a query about whether the sources agree is
answerable, and a critic that could not look says so instead of reporting agreement."
`docs/10-technique-catalogue.md` §1.1 names the reference's own `rag_consensus` and states
what this plugin must not repeat: "`critique.py:158-166` reports `has_consensus=True`
when the critique call fails — a disagreement detector that claims agreement when it
cannot look." `weft_generate.prompts.ConflictStatus.UNDETERMINED` is the fix, and it is
not a placeholder third value — it is what `on_critic_failure`'s one member, `FAIL`,
does here: **a critic whose cascade could not be parsed reports `UNDETERMINED` in the
`Agreement` this plugin returns, never a defaulted `AGREE`**, and the run still proceeds
to answer the question rather than emptying the pipeline of an answer entirely, which is
what `09` §4's V2 requires of every query the engine takes. The distinction is checked
directly, against the same returned type a clean pass produces, in
`tests/unit/weft_generate/test_contradiction.py::
test_a_critic_whose_cascade_cannot_be_parsed_reports_undetermined_not_agreement`.

**One retrieval, one critic call, one generation call — never sampling and voting.**
`docs/10-technique-catalogue.md`'s own row states the rename is mandatory, not a
preference: "`rag_consensus` names sampling-and-voting and would burn `self-consistency`
(`10` §1.4)." This module asks the offered passages whether *they* agree with each
other, once, through `weft_prompts.cascade.execute` — never the model's own answer
sampled several times and voted on, which is a different technique this name must stay
free for.

**Two calls, always — `cost_bound = (2, 2)`, no skip path.** The critic's own cascade
(`contradiction-critic`) and the final answer (`contradiction-answer`) are both asked on
every invocation, the same "no skip path" arithmetic `weft_retrieve.transforms.Hyde`'s
own docstring states for its single fixed call: this technique is not conditioned on
anything in the payload the way a follow-up rewrite is on history, so there is nothing
to skip on.

**Citations are extracted from the final answer's own completion, never asked for as a
second structured field.** Exactly `weft_generate.cited_answer`'s own reasoning, restated
here rather than imported: the passages are already labelled before either model call in
this module runs, so "which sources were cited" is a literal substring search for
`[label]`, and the two private helpers below (`_citations_for`, `_uris_for`) are that
search, not a second copy of `cited_answer`'s own — `weft_generate.cited_answer._offer`
and this module's own `_offer` are the same kind of small, plugin-local duplication
`weft_retrieve.rerank._offer` and `weft_retrieve.graded._offer` already carry for the
identical reason: each prompt's own numbering is the plugin's work, not a shared one.

**The critic's own working note is not the citation a reader follows.** `ContradictionCritique.
agreed` and `.conflicts` (`weft_generate.prompts`) may reference an offered passage's
label in their own prose, but they are never validated against `Answer._citations_resolve`
the way `Answer.citations` is — they are what `_findings_text` folds into the second
call's prompt, and the *final* answer's own bracketed markers are what this plugin reads
citations back out of, the one place `Answer.citations` is actually built.
"""

from collections.abc import Iterable
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_generate.page import page_for
from weft_generate.payload import Answer, AnswerStance, Citation
from weft_generate.prompts import (
    CONTRADICTION_ANSWER_NAME,
    CONTRADICTION_CRITIC_NAME,
    ConflictStatus,
    ContradictionAnswerRequest,
    ContradictionCriticRequest,
    ContradictionCritique,
)
from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Node, Outcome, Produced, SourceId
from weft_llm.contract import LLM
from weft_llm.payload import OnFailure
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Passage, Passages
from weft_store.contract import NodeStore

#: The name this generator is registered and selectable under — see `weft_generate.register`.
NAME = "contradiction-check"


class Agreement(ExtModel):
    """Whether the offered sources agree, attached to `Answer.ext` under this pack's own
    namespace rather than growing two fields on a type eleven other techniques share —
    `.phase2-design.md` §2's own recorded reason for `ext` existing at all.

    `status`, `agreed` and `conflicts` are exactly `ContradictionCritique`'s own three
    fields, carried through unchanged: the critic's judgement *is* what this plugin
    reports, not a value this plugin derives a second time from the final answer's prose.
    """

    __namespace__ = "weft-generate"
    __schema_version__ = "1.0.0"

    status: ConflictStatus
    agreed: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


class ContradictionCheckConfig(BaseModel):
    """`ContradictionCheck`'s `with:` config. Every field has a default, per this pack's
    own rule.

    `max_passages` is not a field the design table's own row for this task names, but the
    number of passages a critic and an answer prompt are both shown is exactly the kind
    of knob `.phase2-findings.md` finding 9 refuses to leave hard-coded — the same lever
    `weft_generate.cited_answer.CitedAnswerConfig.max_passages` gives its own prompt.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    critic_prompt: str = Field(default=CONTRADICTION_CRITIC_NAME, min_length=1)
    answer_prompt: str = Field(default=CONTRADICTION_ANSWER_NAME, min_length=1)
    #: Two independent roles, not one shared knob, because the two calls this plugin
    #: makes are structurally different — see the module docstring's "two calls, always".
    #: `critic_role` names the judgement `weft_prompts.cascade.execute` makes (the same
    #: `"grade"` default `weft_retrieve.graded`'s own single call uses); `answer_role`
    #: names the final completion that writes the cited answer a reader sees (the same
    #: `"generate"` default `weft_generate.cited_answer`'s own single call uses, and the
    #: CLI's `TokenSink` display set — `.phase2-design.md`'s "Streaming attaches at the
    #: client" — defaults to `{"generate"}`, so this is also what makes the final answer,
    #: and not the critic's own internal call, the one that streams to the reader).
    #: `weft_llm.contract.LLM`'s own reason for the role mechanism at all: "generate and
    #: grade can run on different models without either technique's code knowing which."
    critic_role: str = Field(default="grade", min_length=1)
    answer_role: str = Field(default="generate", min_length=1)
    max_passages: int = Field(default=8, ge=1)
    #: What a critic cascade that could not be parsed does — see the module docstring.
    #: One member today (`FAIL`), the same arithmetic `weft_llm.payload.OnFailure`'s own
    #: docstring states for every other consumer: a task that needs a second behaviour
    #: adds the member in the commit that needs it.
    on_critic_failure: OnFailure = OnFailure.FAIL


class ContradictionCheck:
    """Asks whether the offered passages agree, then answers with agreement and conflict
    separated and cited. Satisfies `weft_generate.contract.Generator` structurally.

    `cost_bound = (2, 2)` — see the module docstring's "no skip path".
    """

    config_model: ClassVar[type[ContradictionCheckConfig]] = ContradictionCheckConfig
    cost_bound: ClassVar[tuple[int, int]] = (2, 2)

    def __init__(self, config: ContradictionCheckConfig | None = None) -> None:
        self._config = config if config is not None else ContradictionCheckConfig()

    async def run(self, payload: Passages, ctx: Context) -> Outcome[Answer]:
        """Critique, then answer under `origin` alone — never a derived query, the same
        obligation every plugin that closes the query path carries.
        """
        offered = payload.passages[: self._config.max_passages]
        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)

        critic_prompt = await lookup.build_capability(Prompt, self._config.critic_prompt)
        critiqued = await execute(
            llm=llm,
            prompt=critic_prompt,
            values=ContradictionCriticRequest(
                question=payload.origin.text, passages=_offer(offered)
            ),
            output=ContradictionCritique,
            role=self._config.critic_role,
            ctx=ctx,
        )
        # `on_critic_failure` has one member today (`FAIL`): a critic whose cascade could
        # not be parsed reports `UNDETERMINED` *in the returned model* rather than a
        # defaulted `AGREE` — see the module docstring. The run proceeds to the answer
        # call regardless, which is what `cost_bound`'s fixed floor of two states.
        critique = (
            critiqued.value.value
            if isinstance(critiqued, Produced)
            else ContradictionCritique(status=ConflictStatus.UNDETERMINED)
        )

        answer_prompt = await lookup.build_capability(Prompt, self._config.answer_prompt)
        rendered = await answer_prompt.render(
            ContradictionAnswerRequest(
                question=payload.origin.text,
                passages=_offer(offered),
                findings=_findings_text(critique),
            ),
            ctx,
        )
        if not isinstance(rendered, Produced):
            # A prompt with nothing to ask is relayed exactly as it answered — the same
            # rule `weft_prompts.cascade.execute` and every generator in this pack takes.
            return rendered

        completion = await llm.complete(rendered.value, role=self._config.answer_role, ctx=ctx)
        if not isinstance(completion, Produced):
            return completion
        text = completion.value.text

        citations = await _citations_for(offered, text=text, ctx=ctx)
        stance = (
            AnswerStance.UNDETERMINED
            if critique.status is ConflictStatus.UNDETERMINED
            else AnswerStance.ANSWERED
        )
        return Produced(
            value=Answer(
                origin=payload.origin,
                text=text,
                citations=citations,
                used=offered,
                stance=stance,
                answered_by=NAME,
                ext={
                    Agreement.__namespace__: Agreement(
                        status=critique.status,
                        agreed=critique.agreed,
                        conflicts=critique.conflicts,
                    )
                },
            )
        )


def _findings_text(critique: ContradictionCritique) -> str:
    """`critique` as the block `contradiction-answer`'s own prompt reads — see
    `weft_generate.prompts.ContradictionAnswerRequest.findings`.

    Rendered even for the failure fallback, so the final answer's own instruction ("tell
    the reader plainly") has something honest to work from rather than an empty string
    indistinguishable from a critic that looked and found nothing to say.
    """
    lines = [f"Status: {critique.status.value}"]
    if critique.agreed:
        lines.append("Points of agreement:")
        lines.extend(f"- {point}" for point in critique.agreed)
    if critique.conflicts:
        lines.append("Points of conflict:")
        lines.extend(f"- {point}" for point in critique.conflicts)
    if (
        critique.status is ConflictStatus.UNDETERMINED
        and not critique.agreed
        and not critique.conflicts
    ):
        lines.append("The critic could not determine whether the sources agree.")
    return "\n".join(lines)


def _offer(passages: tuple[Passage, ...]) -> str:
    """The offered evidence as one string, numbered by each passage's own `label` — the
    same shape `weft_generate.cited_answer._offer` builds, for the same prompts-cannot-
    iterate reason `weft_generate.prompts`'s own module docstring states.
    """
    if not passages:
        return ""
    return "\n\n".join(f"[{passage.label}] {passage.node.content}" for passage in passages)


async def _citations_for(
    offered: tuple[Passage, ...], *, text: str, ctx: Context
) -> tuple[Citation, ...]:
    """One `Citation` per offered passage whose own bracketed label appears in `text` — a
    literal substring search, the same one `weft_generate.cited_answer._citations_for`
    performs, restated here rather than imported for the reason the module docstring gives.
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
    """`node`'s one source, or `None` when it has none or more than one to choose from —
    the same rule `weft_generate.cited_answer._source_id` states, for the same reason.
    """
    sources = node.lineage.sources
    return next(iter(sources)) if len(sources) == 1 else None
