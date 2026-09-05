"""`query-scorer` and three `RoutingPolicy` implementations — the router, in two contracts.

Task **2.25**, `docs/build-ledger.md`: "query scoring and routing policy are two plugins, so
a threshold ladder can be replaced by a trained classifier without touching the scorer."
`docs/10-technique-catalogue.md` §1.1's `query-scorer` + `routing-policy` row names the
defect this module exists to close: a router that scores seven independent dimensions on a
span (genuinely good, kept) and then decides via a long hand-written branch cascade over
constants nobody fit to anything can end up unable to select its own best-named strategy, and
a decision step wrapped in an overly broad exception catch can silently swap in a different
routing algorithm on a parse failure nobody sees. Both are the same shape: a decision buried
inside the same code that took the measurement, so retuning the decision meant editing the
measurement.

**Splitting the contract is the fix, not a bigger ladder.** `weft_retrieve.contract.
QueryScorer` (`Stage[Query, Scorecard]`) measures; `weft_retrieve.contract.RoutingPolicy`
(`Stage[Scorecard, Route]`) decides. Three `RoutingPolicy` implementations ship here —
`threshold-ladder`, an ordered rule table (a decision mechanism rewritten as data an operator
edits rather than a branch a developer edits); `nearest-description`, which
selects by embedding similarity and needs no rule written for a newcomer pipeline at all;
`always`, the ten-line trivial policy that exists only to prove the first two are genuinely
interchangeable. Swapping one for another — or a fourth, a trained classifier a third party
ships — is a `with:` edit to a `route.yaml` document's `decide:` stage. `query-scorer` never
imports any of the three, and none of the three imports `query-scorer`: nothing here is
wired together by an import a Python module could break by being deleted, only by a document
naming both under a shared `Scorecard`.

**`query-scorer` reads the catalogue too, and that is deliberate.** It renders every
routable pipeline's own `route.summary` and `route.cost` into its prompt alongside the
dimensions it scores, so a model's judgement of, say, how *specific* a question is stays
grounded in what a router could actually do about it rather than an abstract rubric with no
connection to a real deployment. **It never writes a pipeline name in its own source**, and
that is checkable directly: nothing in this module imports `weft_retrieve.payload.
RouteCandidate`'s callers or names a pipeline as a literal string anywhere below. The
*decision* stays entirely in the policy half; showing the model the options is scoring in
context, not choosing.

**The seven default dimensions are named fresh for Weft.** No text or specific wording is
copied from elsewhere (`04`'s own rule: ideas from the literature are fine and
cited, text never is), and their citations are the three papers `docs/10-technique-
catalogue.md`'s own row names for this pair of plugins — Adaptive-RAG's query-complexity
formulation, *When Not to Trust Language Models*' parametric-vs-retrieved distinction, and
*Self-Knowledge Guided Retrieval Augmentation*'s self-knowledge framing. They are **default
configuration, not a closed vocabulary**: `Scorecard.scores` is an open `Mapping[str,
float]` (that type's own docstring), so an operator retuning them, dropping one or adding an
eighth is a `with: {dimensions: [...]}` edit, never a code change — requirement 6's second
clause, applied to the router itself.
"""

import math
import operator as operator_module
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from weft_embed.contract import Embedder
from weft_kernel.context import Context
from weft_kernel.payload import Failed, MediaType, Node, NothingToProduce, Outcome, Produced, Vector
from weft_llm.contract import LLM
from weft_llm.payload import OnFailure
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt
from weft_retrieve.contract import RouteCatalogue, StageLookup
from weft_retrieve.payload import Query, Route, RouteCandidate, RuleOutcome, Scorecard
from weft_retrieve.prompts import ROUTE_QUERY_NAME, RouteQueryRequest, RouteQueryScores

#: The name `LlmQueryScorer` is registered and selectable under — see `weft_retrieve.register`.
QUERY_SCORER_NAME = "query-scorer"
#: The three `RoutingPolicy` names — see `weft_retrieve.register`.
THRESHOLD_LADDER_NAME = "threshold-ladder"
NEAREST_DESCRIPTION_NAME = "nearest-description"
ALWAYS_NAME = "always"


class Dimension(BaseModel):
    """One named axis a `QueryScorer` measures a query on — data, never code.

    `description` is what is actually rendered into the routing prompt (`_offer_dimensions`
    below); the *name* is what a `Rule`'s own `Condition.dimension` reads back out of the
    `Scorecard` a scorer produced. Two `Dimension`s sharing a name would make one shadow the
    other in `Scorecard.scores`' mapping, which is why `QueryScorerConfig` refuses that
    rather than silently keeping the last one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


#: The seven default dimensions — freshly worded for Weft, never copied text. See
#: the module docstring for the three papers they trace to. An operator's `with:
#: {dimensions: [...]}` replaces this list wholesale; it is not a fixed vocabulary anything
#: downstream depends on the members of.
_SEVEN: tuple[Dimension, ...] = (
    Dimension(
        name="complexity",
        description=(
            "How many distinct reasoning steps or sub-questions a complete answer would "
            "require, from a single fact (0.0) to several that must be combined (1.0)."
        ),
    ),
    Dimension(
        name="multi_hop",
        description=(
            "How much a correct answer likely depends on combining facts drawn from more "
            "than one distinct source, rather than one passage answering it outright."
        ),
    ),
    Dimension(
        name="ambiguity",
        description=(
            "How much the question could be read more than one way without further "
            "context — a name or term that could refer to more than one thing, say."
        ),
    ),
    Dimension(
        name="specificity",
        description=(
            "How narrowly the question names one particular fact, entity or detail (1.0) "
            "versus asking broadly about a topic with many possible good answers (0.0)."
        ),
    ),
    Dimension(
        name="temporal_sensitivity",
        description=(
            "How much the correct answer depends on when it is asked — a fact that "
            "changes over time (1.0) versus one that does not (0.0)."
        ),
    ),
    Dimension(
        name="parametric_confidence",
        description=(
            "How likely a well-trained model already knows the answer from its own "
            "training, with no source consulted at all."
        ),
    ),
    Dimension(
        name="verifiability_need",
        description=(
            "How much the answer needs to be grounded in and traceable to a specific, "
            "citable source, rather than reasoned or summarised freely."
        ),
    ),
)


class QueryScorerConfig(BaseModel):
    """`QueryScorer`'s `with:` config. Every field has a default, per this pack's own rule.

    `intent_markers` is a second, independent measurement this plugin makes — a keyword
    classifier over `Query.text`, costing no model call, the same shape `weft_retrieve.
    sufficiency.HedgePhrases` already gives an operator: a locale- or domain-keyed table of
    substrings, checked in `_keyword_intents` below, never a call site closing over a fixed
    list. Empty by default, which is an honest "this deployment names no intents" rather
    than a placeholder.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimensions: tuple[Dimension, ...] = _SEVEN
    prompt: str = Field(default=ROUTE_QUERY_NAME, min_length=1)
    role: str = Field(default="route", min_length=1)
    intent_markers: Mapping[str, tuple[str, ...]] = Field(default_factory=dict)
    on_score_failure: OnFailure = OnFailure.FAIL

    @field_validator("dimensions", mode="after")
    @classmethod
    def _distinct_names(cls, value: tuple[Dimension, ...]) -> tuple[Dimension, ...]:
        """A repeated `Dimension.name` would silently overwrite its own score in
        `Scorecard.scores`' mapping — caught here, at configuration time, rather than
        discovered downstream as one fewer score than a `RoutingPolicy` expected.
        """
        if not value:
            raise ValueError("QueryScorerConfig.dimensions must name at least one dimension")
        names = [dimension.name for dimension in value]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(
                f"every Dimension.name must be distinct; repeated here: {', '.join(repeated)}. "
                f"A repeated name would silently overwrite its own score in the mapping "
                f"a RoutingPolicy reads."
            )
        return value


class LlmQueryScorer:
    """Measures a query along named dimensions, informed by what a router could pick
    between. Satisfies `weft_retrieve.contract.QueryScorer` structurally.

    **Not named `QueryScorer`** — that name belongs to the contract this class satisfies
    (`weft_retrieve.contract.QueryScorer`), and `weft_retrieve.__init__` re-exports both;
    a plugin class shadowing its own contract's name at that module's top level would be
    exactly the kind of ambiguity `weft_cli.compile`'s "no plugin name registered under two
    contracts" rule exists to keep out of a *document*, applied here to keep it out of the
    package's own namespace. `LlmRerank` and `LlmSufficiency` already draw the same
    "asks a model" prefix; this class draws it for the same reason.

    `cost_bound = (1, 1)` — one cascade call, always, the same shape `weft_retrieve.
    sufficiency.LlmSufficiency` claims for the identical reason: this contract's whole job
    is to be asked, so there is no "nothing to measure" shortcut a reranker or a transform
    can take against an empty input.
    """

    config_model: ClassVar[type[QueryScorerConfig]] = QueryScorerConfig
    cost_bound: ClassVar[tuple[int, int]] = (1, 1)

    def __init__(self, config: QueryScorerConfig | None = None) -> None:
        self._config = config if config is not None else QueryScorerConfig()

    async def run(self, payload: Query, ctx: Context) -> Outcome[Scorecard]:
        """One cascade call, read straight into `Scorecard.scores`, plus one keyword pass.

        `intents` costs no model call and is computed independently of the cascade's own
        success — see `_keyword_intents`. A cascade failure is relayed exactly as it
        answered; `on_score_failure` has one member today (`FAIL`), so relaying it *is*
        failing loudly, the same shape every other cascade-backed plugin in this pack
        already takes.
        """
        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        catalogue = ctx.require(RouteCatalogue)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        candidates = tuple(sorted(catalogue.candidates(), key=lambda candidate: candidate.name))
        request = RouteQueryRequest(
            question=payload.text,
            dimensions=_offer_dimensions(self._config.dimensions),
            candidates=_offer_candidates(candidates),
        )
        judged = await execute(
            llm=llm,
            prompt=prompt,
            values=request,
            output=RouteQueryScores,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(judged, Produced):
            # `on_score_failure` has one member today (FAIL): relaying the cascade's own
            # outcome *is* failing loudly, refusing the silent-fallback shape where a parse
            # failure is caught broadly and a different routing algorithm is swapped in
            # silently instead of being reported.
            return judged

        wanted = frozenset(dimension.name for dimension in self._config.dimensions)
        scores = _score_mapping(judged.value.value, wanted=wanted)
        if isinstance(scores, Failed):
            return scores
        intents = _keyword_intents(payload.text, self._config.intent_markers)
        return Produced(
            value=Scorecard(query=payload, scores=scores, intents=intents, observed=True)
        )


def _offer_dimensions(dimensions: tuple[Dimension, ...]) -> str:
    """`dimensions`, one per line — the same split every other prompt in this pack draws
    between "what a plugin computed" and "what a template can substitute" (`string.
    Template` cannot iterate a tuple).
    """
    return "\n".join(f"- {dimension.name}: {dimension.description}" for dimension in dimensions)


def _offer_candidates(candidates: tuple[RouteCandidate, ...]) -> str:
    """`candidates`, already sorted by the caller, one per line — or an honest statement
    that none are installed, never a blank line a model would have to guess the meaning of.
    """
    if not candidates:
        return "(no routable pipeline is currently installed)"
    lines: list[str] = []
    for candidate in candidates:
        summary = candidate.summary or "(no description)"
        cost = f" — cost: {candidate.cost}" if candidate.cost else ""
        lines.append(f"- {candidate.name}: {summary}{cost}")
    return "\n".join(lines)


def _score_mapping(
    answer: RouteQueryScores, *, wanted: frozenset[str]
) -> dict[str, float] | Failed:
    """Every wanted dimension, scored exactly once — or a `Failed` naming exactly how the
    set was wrong. Mirrors `weft_retrieve.rerank._scores_by_index`'s own three-way refusal
    (unknown, repeated, missing), applied to a name instead of an offered index.
    """
    scores: dict[str, float] = {}
    unknown: list[str] = []
    repeated: list[str] = []
    for entry in answer.scores:
        if entry.name not in wanted:
            unknown.append(entry.name)
        elif entry.name in scores:
            repeated.append(entry.name)
        else:
            scores[entry.name] = entry.score
    missing = sorted(name for name in wanted if name not in scores)
    if unknown or repeated or missing:
        return Failed(
            reason=(
                f"'{QUERY_SCORER_NAME}' asked for exactly {sorted(wanted)} and the model did "
                f"not answer that: {sorted(unknown) or 'none'} were never asked, "
                f"{sorted(repeated) or 'none'} were scored more than once, and "
                f"{missing or 'none'} were not scored at all."
            )
        )
    return scores


def _keyword_intents(text: str, markers: Mapping[str, tuple[str, ...]]) -> frozenset[str]:
    """A keyword classifier over `text` — no model call, `weft_retrieve.sufficiency.
    HedgePhrases`'s own `str.__contains__` mechanism applied to intent labels instead of a
    hedge signal. `markers` is configuration an operator's `with:` block reaches; an empty
    table (the default) answers no intents at all, honestly.
    """
    lowered = text.lower()
    return frozenset(
        intent
        for intent, terms in markers.items()
        if any(term.lower() in lowered for term in terms)
    )


class Comparison(StrEnum):
    """One dimension-to-threshold comparison a `Rule`'s `Condition` tests."""

    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"


#: `Comparison`'s own meaning, the one place it is written — `weft_retrieve.prompts.
#: Grade`'s own `GRADE_ORDER` precedent: a single table rather than a chain of `if`s a
#: fourth member would have to be inserted into by hand.
_COMPARISONS: Mapping[Comparison, Callable[[float, float], bool]] = {
    Comparison.LT: operator_module.lt,
    Comparison.LTE: operator_module.le,
    Comparison.GT: operator_module.gt,
    Comparison.GTE: operator_module.ge,
}


class Condition(BaseModel):
    """One test a `Rule` makes against a `Scorecard`'s own `scores` mapping."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: str = Field(min_length=1)
    op: Comparison
    value: float


class Rule(BaseModel):
    """One row of a `threshold-ladder`: every `when` condition must hold for `then` to win."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    when: tuple[Condition, ...] = Field(min_length=1)
    then: str = Field(min_length=1)


#: Ten seed rules, in priority order — illustrative starting configuration for an operator
#: to retune against their own installed pipelines, never validated against a real
#: deployment. They route between the two pipelines this build ships (`no-retrieval`,
#: `retrieve-then-generate`) using the seven default dimensions above; an operator with a
#: richer catalogue writes their own.
_TEN_SEED_RULES: tuple[Rule, ...] = (
    Rule(
        name="confident-and-simple-answers-from-memory",
        when=(
            Condition(dimension="parametric_confidence", op=Comparison.GTE, value=0.8),
            Condition(dimension="complexity", op=Comparison.LTE, value=0.2),
            Condition(dimension="verifiability_need", op=Comparison.LTE, value=0.3),
        ),
        then="no-retrieval",
    ),
    Rule(
        name="trivial-and-unverifiable",
        when=(
            Condition(dimension="complexity", op=Comparison.LTE, value=0.3),
            Condition(dimension="verifiability_need", op=Comparison.LTE, value=0.2),
        ),
        then="no-retrieval",
    ),
    Rule(
        name="genuinely-multi-hop",
        when=(Condition(dimension="multi_hop", op=Comparison.GTE, value=0.7),),
        then="retrieve-then-generate",
    ),
    Rule(
        name="high-complexity",
        when=(Condition(dimension="complexity", op=Comparison.GTE, value=0.7),),
        then="retrieve-then-generate",
    ),
    Rule(
        name="high-ambiguity",
        when=(Condition(dimension="ambiguity", op=Comparison.GTE, value=0.7),),
        then="retrieve-then-generate",
    ),
    Rule(
        name="time-sensitive",
        when=(Condition(dimension="temporal_sensitivity", op=Comparison.GTE, value=0.6),),
        then="retrieve-then-generate",
    ),
    Rule(
        name="needs-a-citable-source",
        when=(Condition(dimension="verifiability_need", op=Comparison.GTE, value=0.6),),
        then="retrieve-then-generate",
    ),
    Rule(
        name="narrow-and-specific",
        when=(
            Condition(dimension="specificity", op=Comparison.GTE, value=0.7),
            Condition(dimension="complexity", op=Comparison.LTE, value=0.4),
        ),
        then="retrieve-then-generate",
    ),
    Rule(
        name="low-parametric-confidence",
        when=(Condition(dimension="parametric_confidence", op=Comparison.LTE, value=0.3),),
        then="retrieve-then-generate",
    ),
    Rule(
        name="moderate-everything",
        when=(
            Condition(dimension="complexity", op=Comparison.GTE, value=0.4),
            Condition(dimension="multi_hop", op=Comparison.GTE, value=0.3),
        ),
        then="retrieve-then-generate",
    ),
)


class ThresholdLadderConfig(BaseModel):
    """`ThresholdLadder`'s `with:` config. Every field has a default, per this pack's own
    rule — `rules` defaults to the ten illustrative seeds above, `default` to the same
    baseline pipeline the seeds already fall back to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: tuple[Rule, ...] = _TEN_SEED_RULES
    default: str = Field(default="retrieve-then-generate", min_length=1)

    @field_validator("rules", mode="after")
    @classmethod
    def _distinct_rule_names(cls, value: tuple[Rule, ...]) -> tuple[Rule, ...]:
        """A repeated `Rule.name` would leave `Route.rule` unable to say which of two rules
        actually matched — caught here rather than discovered from an ambiguous audit trail.
        """
        names = [rule.name for rule in value]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(
                f"every Rule.name must be distinct; repeated here: {', '.join(repeated)}"
            )
        return value


class ThresholdLadder:
    """An ordered, inspectable rule table — first match wins. Satisfies `weft_retrieve.
    contract.RoutingPolicy` structurally.

    `cost_bound = (0, 0)` — a pure function over a `Scorecard` a `QueryScorer` already
    produced; this plugin resolves no service at all, `ctx` included, and calls no model.
    Closed to newcomers by design: a third-party pipeline needs one `Rule` line from the
    operator before it can be selected — `weft_retrieve.routing`'s own module docstring
    names `nearest-description` as this policy's open counterpart.
    """

    config_model: ClassVar[type[ThresholdLadderConfig]] = ThresholdLadderConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: ThresholdLadderConfig | None = None) -> None:
        self._config = config if config is not None else ThresholdLadderConfig()

    async def run(self, payload: Scorecard, ctx: Context) -> Outcome[Route]:
        """First matching rule wins; no match falls through to `default`.

        A rule naming a dimension the handed `Scorecard` does not carry is refused by name
        before any rule is evaluated, rather than silently treated as non-matching — an
        operator's own typo in a `with:` block should be loud, not a rule that quietly never
        fires.
        """
        del ctx
        unknown = _unknown_dimension(self._config.rules, payload.scores)
        if unknown is not None:
            available = ", ".join(sorted(payload.scores)) or "(none)"
            return Failed(
                reason=(
                    f"'{THRESHOLD_LADDER_NAME}' has a rule testing dimension '{unknown}', "
                    f"which this scorecard does not carry. Scored dimensions: {available}."
                )
            )
        for rule in self._config.rules:
            if all(_holds(condition, payload.scores) for condition in rule.when):
                return Produced(
                    value=Route(
                        pipeline=rule.then,
                        outcome=RuleOutcome.MATCHED,
                        rule=rule.name,
                        scorecard=payload,
                    )
                )
        return Produced(
            value=Route(
                pipeline=self._config.default, outcome=RuleOutcome.FELL_THROUGH, scorecard=payload
            )
        )

    async def reachable(self, candidates: Sequence[RouteCandidate]) -> frozenset[str]:
        """Every pipeline this ladder could ever select — `weft plugins doctor`'s own
        unroutable-report input (task 2.8). Independent of `candidates`: a ladder's own
        reachable set is exactly what its rules and its default name, whether or not any of
        them is currently installed.
        """
        del candidates
        return frozenset(rule.then for rule in self._config.rules) | {self._config.default}


def _unknown_dimension(rules: Sequence[Rule], scores: Mapping[str, float]) -> str | None:
    for rule in rules:
        for condition in rule.when:
            if condition.dimension not in scores:
                return condition.dimension
    return None


def _holds(condition: Condition, scores: Mapping[str, float]) -> bool:
    return _COMPARISONS[condition.op](scores[condition.dimension], condition.value)


class NearestDescriptionConfig(BaseModel):
    """`NearestDescription`'s `with:` config. Every field has a default, per this pack's own
    rule — there is one knob, what happens when nothing can be embedded or compared.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    on_failure: OnFailure = OnFailure.FAIL


class NearestDescription:
    """Embeds every candidate's own `route.summary` beside the query and selects the
    nearest by cosine similarity. Satisfies `weft_retrieve.contract.RoutingPolicy`
    structurally.

    **Open to newcomers, by construction** — the property `.phase2-design.md` §5 names as
    what discharges task 2.8's exit demonstration: a brand-new third-party pipeline
    carrying `route.summary` is selectable the moment it is installed, with **no rule edit
    at all**, because this policy never enumerates pipeline names — only whatever the
    catalogue currently reports.

    `cost_bound = (0, 1)` — zero when the catalogue reports no candidates (there is nothing
    to embed), exactly one batched `Embedder` call otherwise: the query and every
    candidate's summary travel through `Embedder.run` together, never one call per
    candidate, which is what keeps the bound a fixed number rather than "one per installed
    pipeline".
    """

    config_model: ClassVar[type[NearestDescriptionConfig]] = NearestDescriptionConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 1)

    def __init__(self, config: NearestDescriptionConfig | None = None) -> None:
        self._config = config if config is not None else NearestDescriptionConfig()

    async def run(self, payload: Scorecard, ctx: Context) -> Outcome[Route]:
        """Embed the query and every candidate's summary in one batch; pick the argmax.

        `RouteCatalogue` is read here rather than passed in — `RoutingPolicy.run` takes only
        a `Scorecard` (`weft_retrieve.contract`'s own signature), so a policy that needs to
        know what it could select between reaches the same service `QueryScorer` already
        does, exactly the way `weft_retrieve.iterative`'s own `sufficiency`/`leaf` fields
        reach a sibling through `StageLookup` rather than through their own payload.
        """
        catalogue = ctx.require(RouteCatalogue)
        candidates = tuple(sorted(catalogue.candidates(), key=lambda candidate: candidate.name))
        if not candidates:
            # `on_failure` has one member today (FAIL): there is nothing to select between,
            # and reporting that loudly is what "cannot be a silent fallback" means here.
            return Failed(
                reason=(
                    f"'{NEAREST_DESCRIPTION_NAME}' has nothing to select between: the route "
                    f"catalogue advertises no routable pipeline."
                )
            )
        embedder = ctx.require(Embedder)
        nodes = [_synthetic(payload.query.text, "query text embedded for nearest-description")]
        nodes.extend(
            _synthetic(
                candidate.summary or candidate.name,
                f"route summary for candidate '{candidate.name}'",
            )
            for candidate in candidates
        )
        outcome = await embedder.run(nodes, ctx)
        if isinstance(outcome, Failed):
            return outcome
        if isinstance(outcome, NothingToProduce):
            return Failed(
                reason=(
                    f"the configured embedder produced nothing for a {len(nodes)}-node "
                    f"routing batch: {outcome.reason}"
                )
            )
        vectors: list[Vector] = []
        for node in outcome.value:
            if node.embedding is None:
                return Failed(
                    reason="the configured embedder ran and returned at least one node "
                    "carrying no embedding"
                )
            vectors.append(node.embedding)
        query_vector, *candidate_vectors = vectors
        best = max(
            zip(candidates, candidate_vectors, strict=True),
            key=lambda pair: _cosine(query_vector, pair[1]),
        )
        return Produced(
            value=Route(pipeline=best[0].name, outcome=RuleOutcome.NEAREST, scorecard=payload)
        )

    async def reachable(self, candidates: Sequence[RouteCandidate]) -> frozenset[str]:
        """Every currently installed candidate — this policy can select any of them."""
        return frozenset(candidate.name for candidate in candidates)


def _synthetic(text: str, reason: str) -> Node:
    return Node.synthetic(content=text, media_type=MediaType.TEXT, reason=reason)


def _cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity between two embeddings — no store, no index, just the two vectors
    an `Embedder` handed back in the same batch."""
    dot = sum(x * y for x, y in zip(a.values, b.values, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a.values))
    norm_b = math.sqrt(sum(y * y for y in b.values))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class AlwaysConfig(BaseModel):
    """`Always`'s `with:` config. Every field has a default, per this pack's own rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(default="retrieve-then-generate", min_length=1)


class Always:
    """Routes every query to one configured pipeline, no matter what the `Scorecard` says.
    Satisfies `weft_retrieve.contract.RoutingPolicy` structurally.

    Exists to prove the other two are genuinely interchangeable — the module docstring's own
    claim, made checkable rather than argued: swapping `decide:`'s `use:` line from
    `threshold-ladder` to `always` changes what a route document selects without touching
    `query-scorer`, at a cost of ten lines. `cost_bound = (0, 0)` — no service resolved, no
    model called, the `Scorecard` it is handed read for nothing but the audit trail carried
    onto `Route.scorecard`.
    """

    config_model: ClassVar[type[AlwaysConfig]] = AlwaysConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: AlwaysConfig | None = None) -> None:
        self._config = config if config is not None else AlwaysConfig()

    async def run(self, payload: Scorecard, ctx: Context) -> Outcome[Route]:
        del ctx
        return Produced(
            value=Route(
                pipeline=self._config.pipeline,
                outcome=RuleOutcome.MATCHED,
                rule=ALWAYS_NAME,
                scorecard=payload,
            )
        )

    async def reachable(self, candidates: Sequence[RouteCandidate]) -> frozenset[str]:
        del candidates
        return frozenset({self._config.pipeline})
