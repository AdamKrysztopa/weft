"""`corrective` — grades a primary retrieval, and reaches a *distinct* retriever when what
survives grading is thin. `Retriever`, owning its own decision the way `weft_retrieve.
iterative.IterativeRetrieval` owns its own loop.

Task **2.21b**, `docs/build-ledger.md`'s 2.21 line: "a knowledge action that reaches a second
retriever is what earns the name `corrective`." `docs/10-technique-catalogue.md` §1.1 states
the condition this module exists to satisfy, verbatim: "`corrective` is only honest if the
plugin gains a *distinct knowledge action* — a second `Retriever` resolved by contract, not
the same index re-queried. If Weft ships the reference's behaviour unchanged, the name is
`graded-retrieval` and the word `corrective` stays free for a plugin that earns it." `weft_
retrieve.graded.GradedRetrieval` is that unchanged behaviour; this module is what is built on
top of it, and `knowledge_action`'s own field below — required, with no default — is what
makes a same-index `corrective` unconstructable rather than merely undocumented.

Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling, *Corrective Retrieval Augmented Generation*,
arXiv:2401.15884, 2024. **The reference's own divergence, named in `10` §1.1's row, is exactly
what this module refuses to repeat**: "the reference's correction is 'rewrite the query broader
and re-ask the same index' ... Nothing is corrected." The paper's own Incorrect action reaches
*outside* the corpus entirely (web search); this plugin does not assume a web search plugin
exists, so it generalises the paper's shape one notch rather than copying its specific action
— `knowledge_action` is any registered `Retriever` a document names, which could be a web
search pack, a second store, or anything else a third party publishes under this contract.
What is preserved, and checked, is the paper's own load-bearing property: the corrective step
is a **different** source of evidence from the one that was graded thin, never the same index
asked again with a broader query. `CorrectiveConfig`'s own validator below refuses
`knowledge_action == primary` for exactly that reason.

**What this module is not.** It does not implement the paper's own three-way action
(Correct / Incorrect / Ambiguous) or its knowledge-strip refinement — `graded-retrieval`
already collapsed "graded well" into "kept" and "graded poorly" into "discarded", so by the
time this module sees the result there are only two states left to act on: enough evidence
survived, or not enough did. `trigger_kept_below` is that one threshold, named as
configuration rather than folded into an unstated `if`.

**A looping technique reaching a sibling through `StageLookup`, the same concession `weft_
retrieve.iterative`'s own module docstring names and this module does not re-argue**:
`.phase2-design.md` §4, "a resolved pipeline is a finite ordered list ... `corrective`
[needs] 'do it again, differently, if X'. No control flow is added to the grammar ... the
concession: a looping technique is one plugin that owns its loop and reaches a sibling
through `StageLookup`." Here the "loop" runs at most once — `primary`, then `grader`, then
optionally `knowledge_action` — but the shape (resolve a sibling by name, call it, act on
what it says) is the same concession, applied to a branch rather than to a `for`.
"""

from collections.abc import Mapping
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Outcome, Produced
from weft_kernel.runner import Stage
from weft_retrieve.contract import Reranker, Retriever, StageLookup
from weft_retrieve.fusion import contributor_label
from weft_retrieve.payload import Candidates, Passage, QuerySet, RankedList, Ranking

#: The name this retriever is registered and selectable under — see `weft_retrieve.register`.
NAME = "corrective"


class CorrectiveConfig(BaseModel):
    """`Corrective`'s `with:` config. Every field but one has a default — `knowledge_action`
    does not, deliberately (module docstring: "what makes a same-index `corrective`
    unconstructable"). `primary_config`, `grader_config` and `knowledge_action_config` are
    each sub-plugin's own `with:` block, the same lever `weft_retrieve.iterative.
    IterativeRetrievalConfig.leaf_config` gives its own resolved sibling — without them, the
    only thing this document could retune about `primary`, `grader` or `knowledge_action`
    would be *which plugin* fills the role, never how the chosen one runs, which is
    `.phase2-findings.md` finding 9's own "a knob that exists in the library and not in the
    config model is a knob a third party cannot reach" repeated a task apart.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The `Retriever` graded — defaults to the single-pass baseline, never to this plugin's
    #: own name (which would construct a corrective of correctives by accident).
    primary: str = Field(default="vector-top-k", min_length=1)
    primary_config: Mapping[str, object] | None = None
    #: The `Reranker` that grades and filters `primary`'s own hits.
    grader: str = Field(default="graded-retrieval", min_length=1)
    grader_config: Mapping[str, object] | None = None
    #: The distinct second `Retriever`, resolved by name through `StageLookup`. No default —
    #: see the module docstring and `_the_action_is_not_the_primary` below.
    knowledge_action: str = Field(min_length=1)
    knowledge_action_config: Mapping[str, object] | None = None
    #: Fewer kept hits than this triggers `knowledge_action`. `3`, this build's own smallest
    #: defensible default — `.phase2-design.md` names the field but not a number, and the
    #: paper's own trigger ("the highest-scoring document was graded Incorrect") has no
    #: analogue once grading is per-document rather than per-query, so a count is what is
    #: configurable here instead. Recorded rather than left silent.
    trigger_kept_below: int = Field(default=3, ge=0)

    @model_validator(mode="after")
    def _the_action_is_not_the_primary(self) -> "CorrectiveConfig":
        """Refuses the one configuration `10` §1.1's own condition names by name: the same
        plugin resolved twice is the same index re-queried, whatever query text it is handed
        the second time — the reference's own "rewrite the query broader and re-ask the same
        index", which the paper's own row states plainly corrects nothing. Checked here,
        at construction, rather than discovered as an honest-looking `Candidates` that
        turns out to hold the same retriever's opinion twice.
        """
        if self.knowledge_action == self.primary:
            raise ValueError(
                f"knowledge_action ('{self.knowledge_action}') must name a Retriever "
                f"distinct from primary ('{self.primary}') — the same plugin re-queried on "
                f"the same corpus is not a corrective action, it is the reference's own "
                f"'rewrite the query broader and re-ask the same index' (`10` §1.1), and "
                f"the whole point of this plugin's name is that it is not that. Register a "
                f"second Retriever under a different name, or use 'graded-retrieval' alone "
                f"if grading is all this document needs."
            )
        return self


class CorrectiveTrace(ExtModel):
    """Whether `knowledge_action` ran, and how much survived grading — attached to the
    returned `Candidates.ext` since, per `weft_retrieve.iterative`'s own stated rule, no span
    is written inside a plugin.
    """

    __namespace__ = "weft-retrieve"

    triggered: bool
    kept: int


class Corrective:
    """Grades `primary`'s own hits and, when too few survive, adds `knowledge_action`'s.
    Satisfies `weft_retrieve.contract.Retriever` structurally.

    `cost_bound = (1, -1)`: a floor of one (`grader`'s own floor, resolved by name and
    therefore assumed no cheaper than `graded-retrieval`'s own declared one), unbounded
    because both `primary` and `knowledge_action` are resolved by name and could be anything
    registered under `Retriever` — the same reasoning `IterativeRetrieval.cost_bound`'s own
    docstring gives for `leaf`.
    """

    config_model: ClassVar[type[CorrectiveConfig]] = CorrectiveConfig
    cost_bound: ClassVar[tuple[int, int]] = (1, -1)

    def __init__(self, config: CorrectiveConfig | None = None) -> None:
        """`config`, or a named refusal — never a zero-argument `CorrectiveConfig()`.

        Every other plugin in this pack falls back to its own config model's defaults here;
        this one cannot, because `CorrectiveConfig.knowledge_action` has none — that absence
        is the module docstring's own claim made real. A resolved pipeline never reaches this
        branch (`weft_kernel.resolution._validate_stage_config` already refused a `with:`
        block missing `knowledge_action` before any factory runs); the one caller that can —
        `weft_kernel.runner._build`'s `candidate.factory(None)`, used only to construct a
        `fallback:` candidate, which carries no `with:` block by definition — gets a plugin
        name and a reason instead of a `pydantic.ValidationError` about a field it never
        named, which `weft_kernel.runner._build` reports as *this* stage failing to build
        rather than a bare traceback.
        """
        if config is None:
            raise ValueError(
                f"'{NAME}' has no usable default configuration — `knowledge_action` names "
                f"the second Retriever this plugin's whole point rests on, and it has no "
                f"default (see CorrectiveConfig's own docstring). Configure it with a "
                f"'with:' block naming knowledge_action; 'corrective' cannot be used as a "
                f"fallback: candidate, which carries none."
            )
        self._config = config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        """`primary`, graded by `grader`; `knowledge_action` added only when grading leaves
        fewer than `trigger_kept_below` hits.

        `out.origin == in.origin` holds by construction: every `Candidates` returned below is
        built with `payload.origin`, never a query either sub-plugin might have derived — the
        obligation every query-path plugin in this pack carries.
        """
        lookup = ctx.require(StageLookup)
        retriever_contract = cast("type[Stage[QuerySet, Candidates]]", Retriever)
        reranker_contract = cast("type[Stage[Ranking, Ranking]]", Reranker)

        primary = await lookup.build(
            retriever_contract, self._config.primary, self._config.primary_config
        )
        retrieved = await primary(payload, ctx)
        if not isinstance(retrieved, Produced):
            # A primary that declined or failed is relayed exactly as it answered — the same
            # rule `IterativeRetrieval` follows for its own `leaf`.
            return retrieved

        flattened = _flatten(retrieved.value)
        grader = await lookup.build(
            reranker_contract, self._config.grader, self._config.grader_config
        )
        graded = await grader(flattened, ctx)
        if not isinstance(graded, Produced):
            return graded
        kept = graded.value

        if len(kept.hits) >= self._config.trigger_kept_below:
            return Produced(
                value=Candidates(
                    origin=payload.origin,
                    lists=(RankedList(query=payload.origin, retriever=NAME, hits=kept.hits),),
                    ext={
                        CorrectiveTrace.__namespace__: CorrectiveTrace(
                            triggered=False, kept=len(kept.hits)
                        )
                    },
                )
            )

        action = await lookup.build(
            retriever_contract, self._config.knowledge_action, self._config.knowledge_action_config
        )
        corrected = await action(payload, ctx)
        if not isinstance(corrected, Produced):
            # `knowledge_action`'s own failure is relayed rather than papered over with the
            # graded hits alone — a caller told "corrective ran" must not silently receive
            # fewer sources than the trigger it crossed asked for.
            return corrected

        combined = (
            RankedList(query=payload.origin, retriever=NAME, hits=kept.hits),
            *corrected.value.lists,
        )
        return Produced(
            value=Candidates(
                origin=payload.origin,
                lists=combined,
                ext={
                    CorrectiveTrace.__namespace__: CorrectiveTrace(
                        triggered=True, kept=len(kept.hits)
                    )
                },
            )
        )


def _flatten(candidates: Candidates) -> Ranking:
    """`candidates`' own lists, concatenated into one `Ranking` for `grader` to judge.

    Not a fusion — `weft_retrieve.fusion.SingleList` refuses more than one list precisely
    because *reranking* two disagreeing lists needs a real fusion policy, and reusing RRF
    here for a step that only needs a flat list to hand a grader would be `04`:421-426's own
    defect (a fusion formula reached from a second call site) landing on a task that never
    needed to fuse at all. `contributor_label` — the same key `ReciprocalRankFusion.weights`
    is written against — is what `Ranking.contributors` is populated with, one entry per
    distinct list, deduplicated in the order the lists arrived in.
    """
    hits: list[Passage] = []
    contributors: list[str] = []
    for ranked in candidates.lists:
        label = contributor_label(ranked)
        if label not in contributors:
            contributors.append(label)
        hits.extend(ranked.hits)
    reranked = tuple(
        Passage(scored=hit.scored, rank=rank, retrieved_by=hit.retrieved_by, label=hit.label)
        for rank, hit in enumerate(hits)
    )
    return Ranking(
        origin=candidates.origin,
        hits=reranked,
        contributors=tuple(contributors),
        ext=candidates.ext,
    )
