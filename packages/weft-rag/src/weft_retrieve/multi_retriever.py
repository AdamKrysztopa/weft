"""`multi-retriever` — one query, several *retrievers*, one `Candidates`.

**Why this is the third documented exception to `10` §2.1 rule 5, on `multi-arm`'s and
`hybrid`'s own footing, rather than a fourth composition trying to squeeze into a pipeline.**
A composition is normally a pipeline, but two retrievers cannot sit in sequence in one:
`Retriever` is `Stage[QuerySet, Candidates]`, so the second stage would be handed the first's
`Candidates` rather than the `QuerySet` it needs — they do not compose by type. `multi-arm`
fans out over *filters* on one store and `hybrid` over the *two arms* of one store; neither
reaches a second retrieval *strategy*. This plugin fans out over **retrievers** themselves,
each resolved by name — the same concession `weft_retrieve.iterative` and
`weft_retrieve.corrective` already take for a sibling reached at run time rather than placed
in a document, applied here to arity instead of to a loop or a decision.

**Two passes, not one loop — every arm is resolved before any arm is dispatched.** A plugin
that resolved and ran each arm in the same loop would have spent a real retrieval through a
good arm before discovering a bad name two arms later, returning nothing for the cost of
something. Resolving every `RetrieverArm.use` through `StageLookup` first means a document
naming one bad arm does no retrieval at all, and `UnknownPluginError` propagates untouched —
it already names the contract, the name and every valid option, and inventing a second error
for one mistake is exactly what this pack's own `run_services._entry_or_none` comment warns
against.

**Each arm is handed the incoming `QuerySet` unchanged.** Never a derived query, never
another arm's `Candidates` — the type is the entire reason this plugin has to exist rather
than being spelled as a pipeline.

**Every list an arm returns is labelled by that arm, not just the first one.** An arm's own
plugin may itself fan out — `hybrid` returns two lists per query, `multi-arm` one per
configured arm of its own — and all of them belong to the arm that produced them.
`RetrieverArm.name` becomes every one of those lists' `RankedList.channel`, so
`weft_retrieve.fusion.contributor_label` reads `multi-retriever:<arm name>` regardless of how
many lists the arm's own plugin drew. Weighting *within* an arm is that inner plugin's
business; an operator's `weights` mapping downstream addresses arms, not an arm's own
sub-channels.

**An arm that fails fails the whole retrieval.** Returning the lists the healthy arms
produced and dropping the failed one silently would be a plausible answer against incomplete
evidence — the silent fallback this project refuses. `Failed.reason` names both the arm and
the underlying reason, so a document author can tell which of several arms broke.

**`needs_store` is not declared** — `weft_retrieve.iterative`'s own module docstring is the
precedent and the reasoning is unchanged here: each arm is resolved by name at `run` time,
not at registration, so there is no store capability this class itself could state ahead of
time. Declaring `(VectorSearch,)` defensively would be a claim about plugins this class has
never seen; an arm need not touch a store at all (it could itself be `no-retrieval`, or
another `multi-retriever`).
"""

from collections.abc import Mapping
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced
from weft_kernel.runner import Stage
from weft_retrieve.contract import Retriever, StageLookup
from weft_retrieve.payload import Candidates, QuerySet, RankedList

#: The name this plugin is registered and selectable under — see `weft_retrieve.register`.
NAME = "multi-retriever"


class RetrieverArm(BaseModel):
    """One retrieval strategy: what to call it, which registered `Retriever` runs it, and
    that retriever's own `with:` block."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: What this arm contributes under. Becomes every `RankedList.channel` the arm's own
    #: plugin returns, and therefore the `multi-retriever:<name>` key a `Fuser`'s `weights`
    #: mapping is written against. Two arms sharing a name would be lists an operator has no
    #: way to weight apart, which is why `MultiRetrieverConfig` refuses duplicates below.
    name: str = Field(min_length=1)
    #: The registered `Retriever` name this arm resolves to, through `StageLookup`.
    use: str = Field(min_length=1)
    #: `use`'s own `with:` block — passed straight through as `StageLookup.build`'s third
    #: argument, the same lever `IterativeRetrievalConfig.leaf_config` and
    #: `CorrectiveConfig.primary_config` already give their resolved siblings. `None` reaches
    #: the arm exactly as an absent `with:` block would in a document — the arm's own
    #: defaults, not this plugin's opinion of them.
    config: Mapping[str, object] | None = None


class MultiRetrieverConfig(BaseModel):
    """`multi-retriever`'s `with:` config."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: At least two, carrying `multi-arm`'s own reasoning in spirit: a plugin whose whole
    #: purpose is arity, handed arity one, is a document mistake — the retriever spelled the
    #: long way — refused here by name rather than quietly tolerated.
    arms: tuple[RetrieverArm, ...] = Field(min_length=2)

    def model_post_init(self, context: object, /) -> None:
        del context
        names = [arm.name for arm in self.arms]
        if len(set(names)) != len(names):
            raise ValueError(
                f"'{NAME}' arms must have distinct names — a Fuser addresses an arm by its "
                f"'{NAME}:<name>' label, so duplicates leave an operator no key to weight "
                f"them apart. Got: {names}"
            )


class MultiRetriever:
    """Fans out over other `Retriever`s, resolved by name. Satisfies `contract.Retriever`
    structurally — see the module docstring.

    `cost_bound = (0, -1)`: a floor of zero, because every arm could itself be
    `no-retrieval`, and an unbounded ceiling, because an arm could be `iterative-retrieval`
    with its own model calls across its own rounds.
    """

    config_model: ClassVar[type[MultiRetrieverConfig]] = MultiRetrieverConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, -1)

    def __init__(self, config: MultiRetrieverConfig) -> None:
        self._config = config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        """Resolve every arm, then run every arm, then relabel every list each arm returned.

        `out.origin == in.origin` holds by construction — the `Candidates` returned below is
        always built with `payload.origin`, the same obligation every query-path plugin in
        this pack carries (`QuerySet.origin`'s own docstring).
        """
        lookup = ctx.require(StageLookup)
        # `Retriever` is a `Protocol` subclass of `Stage[QuerySet, Candidates]`, and pyright
        # cannot solve `StageLookup.build`'s `In`/`Out` from a `type[Protocol subclass]` —
        # confirmed against a minimal reproduction rather than assumed (see `iterative.py`);
        # the cast states the fact the contract already declares (`Retriever`'s own base
        # list), it does not invent one.
        retriever_contract = cast("type[Stage[QuerySet, Candidates]]", Retriever)

        # First pass: resolve every arm before dispatching any of them, so a document naming
        # one bad arm does no retrieval at all rather than half of it.
        resolved = [
            (arm, await lookup.build(retriever_contract, arm.use, arm.config))
            for arm in self._config.arms
        ]

        # Second pass: run every arm, unchanged `QuerySet`, and relabel every list it returns.
        lists: list[RankedList] = []
        for arm, retriever in resolved:
            outcome = await retriever(payload, ctx)
            if isinstance(outcome, Failed):
                return Failed(reason=f"arm '{arm.name}' ('{arm.use}') failed: {outcome.reason}")
            if isinstance(outcome, NothingToProduce):
                # An arm that declined contributes no lists, and the fan-out carries on. It is
                # not a failure — `NothingToProduce` is "a legitimate result" — and it must not
                # become this stage's own outcome either: `Candidates`' emptiness rule says
                # that type "means the stage declined to act and stops the pipeline, which on a
                # query path would mean no `Answer` at all", which `09` §4's V2 forbids. One
                # empty base must not silence every other one, nor the answer.
                continue
            lists.extend(
                ranked.model_copy(update={"retriever": NAME, "channel": arm.name})
                for ranked in outcome.value.lists
            )

        return Produced(
            value=Candidates(origin=payload.origin, lists=tuple(lists), ext=payload.ext)
        )
