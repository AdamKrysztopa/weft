"""The query vocabulary — the domain types every query-path stage signature names.

Task **2.4**, `docs/02-extension-model.md` §1 → *Composition is typed and checked at
load*: "the ingest path is `Stage[Seq[Node], Seq[Node]]` throughout **while the query
path is not** … the resolver checks that consecutive stages compose and fails naming both
types." That sentence is the whole reason this module exists. The ingest path can get
away with one payload type because every stage there means the same thing by it; the
query path cannot, and the types below are what the difference is made of.

**Multiplicity lives here, in the payload type, and nowhere else.** A `QuerySet` means
"n queries", a `Candidates` means "k ranked lists", a `Ranking` means "one". That is not
a stylistic choice: `weft_kernel.runner._stage_signature` reads a contract's `In`/`Out`
off `__orig_bases__` exactly once, at class creation, so no stage can have types that
depend on its configuration and a generic `for-each` lifting `Stage[A, B]` to
`Stage[Seq[A], Seq[B]]` is structurally impossible to declare. Fan-out and fan-in
therefore have to be expressed as *types* if they are to be checked at all — and once
they are, `weft_kernel.runner._check_composition` catches a reranker placed before a
fuser at resolution, with no inspector living in this pack and nothing for a pipeline
author to remember.

**Every carrier takes `ext: ExtMap`.** `01` → Phase 2's gate line says to re-open **G5**
only if a strategy cannot express what it needs to pass along; reusing G5's settled
namespaced-typed-extension mechanism on the carriers is the answer to it, so a technique
that wants to hand something downstream attaches a namespaced `ExtModel` instead of
growing a field on a type eleven other techniques share. **Known gap, stated rather than
discovered:** `weft_kernel.seam._strip_transient` only walks `Node`s, so a
`__transient__` ext on one of these carriers is *not* stripped at the seam — the pack
that lets a carrier leave the query path is the one that must drop it, and a carrier
`ExtModel` that must survive a store round trip is registered with
`weft_store.register_ext_model` by whoever ships it.

**What this module deliberately does not carry, named so it is not rediscovered.**
`Ranking` records which retriever and which channel fed the fusion (`contributors`,
`Passage.retrieved_by`) but **not which query found which hit** — fusion collapses k
lists into one and per-query attribution does not survive it. That is a real narrowing,
argued rather than overlooked: a `Ranking` still carrying k queries' worth of attribution
*is* `Candidates` under another name, and the whole point of the arity reduction is that
the stages after it cannot see the arity. A technique that genuinely cannot express what
it needs to pass along because of it is the trigger `01` → Phase 2's *Gate* line
describes, and the response is to stop and re-open G5, never to widen these models inside
a commit.

`Scored[Node]` is `weft_store`'s and is reused, never restated: `docs/02-extension-model.
md` §1, "the score lives on `Scored[Node]`, not on `Node` — it is a property of one
retrieval, not of the node."
"""

from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from weft_kernel.payload import ExtMap, Node
from weft_store.contract import Filter, Scored


class QueryOrigin(StrEnum):
    """Where a `Query`'s text came from. `Enum` per the project's string-constant rule."""

    USER = "user"
    DERIVED = "derived"


class Channel(StrEnum):
    """The two arms first-party code names — a vocabulary, deliberately **not** a field type.

    Two members, because `docs/02-extension-model.md` §1 → *The store contract family*
    publishes exactly two searches that return a ranking: `VectorSearch.search_vector`
    and `TextSearch.search_text`. "Hybrid is not a third method — it is a store
    satisfying both search protocols," so there is no `HYBRID` member here either.

    **But `Query.channels` and `RankedList.channel` are `str`, not this enum**, and that is
    the deliberate half. The same section of `02` opens by naming the ways backends
    genuinely differ — "hybrid search, filtering, full text, **graph traversal**" — and `01`
    requirement 2's worked example is an add-on registering "an enhancer, a retriever, a
    store and CLI commands from a single install". A Python enum that already has members
    cannot be extended, so typing the field as one would leave that pack's `RankedList`
    with no honest way to say which arm produced it: `Channel.VECTOR` would be a lie and
    an absence would say nothing a fuser could weight. That is a closed key space on the
    one axis the store family is explicitly open on, which is what fitness function 4
    exists to forbid — the same argument `Scorecard.scores` makes one type below, applied
    here because the axis is the same shape.

    Nothing is lost by writing it this way: a `StrEnum` member *is* a `str`, so
    `channel=Channel.VECTOR` and `channels=(Channel.VECTOR,)` are written verbatim and
    compare equal to `"vector"`. What a first-party plugin's *config model* declares is a
    separate question and stays typed — an operator's `channels = ["vectr"]` in a `with:`
    block is refused there, where a typo is made.
    """

    VECTOR = "vector"
    TEXT = "text"


class TurnRole(StrEnum):
    """Who spoke, in a conversation a query arrives inside of."""

    USER = "user"
    ASSISTANT = "assistant"


class Turn(BaseModel):
    """One exchange in the history a follow-up question needs to be understood against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: TurnRole
    text: str


class Query(BaseModel):
    """One thing that will actually be searched for — the user's own words, or a derivation.

    `produced_by` names the plugin that derived it and is `""` for what the user typed,
    which is what lets a fan-out transform expand only the original question rather than
    multiplying whatever an earlier transform already produced.

    `channels` is the fix for the reference's HyDE inversion, made structural: a hypothetical
    *document* is a good dense-retrieval probe and a bad lexical one, so the transform
    that invents it says so here, once, and every retriever downstream honours it without
    knowing what HyDE is. Empty means "every channel this retriever offers" — an absence,
    never a sentinel value a caller has to know to compare against. Each name is a `str`
    rather than a `Channel`, so a transform can aim a derived query at an arm nobody here
    anticipated — see `Channel`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    origin: QueryOrigin = QueryOrigin.USER
    produced_by: str = ""
    #: BCP-47. A fact about the ask, never a pipeline var — `weft_kernel.context.Context`
    #: already carries the *run*'s locale, and a question asked in Polish against an
    #: English corpus is a different thing from a run configured for Polish.
    locale: str | None = None
    channels: tuple[str, ...] = ()
    filter: Filter | None = None

    @field_validator("channels", mode="after")
    @classmethod
    def _no_arm_is_nameless(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """A blank arm name is refused, for `Passage.retrieved_by`'s reason one type down.

        The tuple's own emptiness already says "every channel this retriever offers", so a
        `""` inside it is not a second way to say that — it is an arm no retriever can
        match, no fuser can weight and no diagnostic can group, and accepting one would
        make every consumer test for it.
        """
        if any(not name for name in value):
            raise ValueError(
                "every entry in Query.channels names one arm of a store; a blank name "
                "matches no arm. Leave the tuple empty to mean 'every channel this "
                "retriever offers'."
            )
        return value


class QuerySet(BaseModel):
    """The query path's entry payload: what the user asked, and what will be retrieved for.

    **`origin` is a contract term every query-path stage honours, and nothing checks it.**
    The reference fed a hallucinated HyDE passage to its cross-encoder *as the query*, so the
    reranker scored every candidate against a document the engine had made up. This field
    is where the user's own words live so that a reranker has something other than the last
    transform's output to rescore against: `Reranker` is `Stage[Ranking, Ranking]` and a
    `Ranking` carries `origin`, so there is a right answer for it to read.

    Said as the obligation it is rather than as the guarantee it is not. `frozen=True`
    stops a stage mutating a payload it was handed; it does not stop one *constructing* the
    next payload with a substitute in this field, and every stage on this path constructs
    its output wholesale. `weft_retrieve.contract.QueryTransform` states the same rule in
    its own words. The teeth are owed by the plugins: each first-party query-path plugin of
    ledger 2.13–2.26 carries an `out.origin == in.origin` assertion in its own tests,
    because the registration seam knows nothing of these types and so cannot carry it for
    them. Until those land, this is a rule an author must remember — recorded here rather
    than left to be discovered by whoever reads "structurally" and looks elsewhere.

    `queries` is never empty. A transform that decides it has nothing to add returns the
    set it was given, and a stage that genuinely declines to act answers
    `NothingToProduce` — the two are different facts and the type refuses to let one be
    reported as the other.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: Query
    queries: tuple[Query, ...] = Field(min_length=1)
    #: Empty in a one-shot `weft ask`; filled by Phase 3's REPL (ledger 3.4).
    history: tuple[Turn, ...] = ()
    ext: ExtMap = Field(default_factory=dict, validate_default=True)


class Passage(BaseModel):
    """One retrieved node, with where it came from and where it sat in the list it arrived in.

    Wraps `weft_store.Scored[Node]` and restates neither `node` nor `score`: the two
    properties below read through it. Duplicating them would give this pack a second
    copy of a type `weft-store` already publishes, and the first divergence between the
    two would be invisible.

    `retrieved_by` refuses `""`. A passage whose provenance is a blank string is a
    passage no diagnostic can group, no citation can attribute and no fusion can weight,
    and accepting one would make every downstream consumer test for it — the "a silent
    fallback is worse than a failure" rule applied to a field rather than to a code path.
    `label` is genuinely optional and stays empty until a `ContextPacker` assigns the
    citation markers, because nothing before the packer knows how many passages there
    will be.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scored: Scored[Node]
    rank: int = Field(ge=0)
    retrieved_by: str = Field(min_length=1)
    label: str = ""

    @property
    def node(self) -> Node:
        """The node itself — read through `scored`, never stored twice."""
        return self.scored.value

    @property
    def score(self) -> float:
        """This passage's score in the one retrieval that produced it."""
        return self.scored.score


class RankedList(BaseModel):
    """One retrieval's result: one query, down one channel, from one retriever.

    `hits` being empty is a legitimate result and a *different* fact from this list not
    existing — see `Candidates`. `note` is where a retriever states something about the
    list that its emptiness alone would not say, such as a boolean parser reporting a
    conjunction with no satisfying document.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: Query
    retriever: str = Field(min_length=1)
    #: Which arm produced this list — `Channel.VECTOR`, `Channel.TEXT`, or a name only the
    #: pack shipping that arm knows. Empty when the retriever draws no distinction, which
    #: is an absence and not a third arm. A `Fuser` never produces a `RankedList` (it
    #: produces a `Ranking`, whose `contributors` is what survives the fan-out), so
    #: "unstated" is the only thing emptiness can honestly mean here.
    channel: str = ""
    hits: tuple[Passage, ...] = ()
    note: str = ""


class Candidates(BaseModel):
    """k ranked lists, un-fused — what every `Retriever` produces and every `Fuser` consumes.

    **The emptiness rule, stated here because this is the type it is about.**
    `Candidates(lists=(RankedList(hits=()),))` says a retriever looked and found nothing;
    `Candidates(lists=())` says nothing was ever asked, which is what the null-retrieval
    strategy of ledger 2.13 legitimately produces. The two are distinguishable by
    inspection with no flag on either, and neither is `NothingToProduce` — that one means
    the stage declined to act and stops the pipeline, which on a query path would mean no
    `Answer` at all, and `09` §4's V2 requires the engine to be able to answer "not in
    this corpus."
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: Query
    lists: tuple[RankedList, ...] = ()
    ext: ExtMap = Field(default_factory=dict, validate_default=True)


class Ranking(BaseModel):
    """One list, fused — the arity reduction that lets a reranker and a packer exist at all.

    A `Fuser` is `Stage[Candidates, Ranking]` rather than `Stage[Candidates, Candidates]`
    precisely so this type can mean "one": every stage after it is spared the question of
    how many lists there were, and `weft_kernel.runner._check_composition` refuses a
    pipeline that reaches a reranker, a packer or a generator without having reduced.

    `contributors` is what survives of the fan-out — the retriever and channel labels
    that fed the fusion. See the module docstring for what deliberately does not.

    `note` is `RankedList.note`'s own mechanism, one type up: that field's own docstring
    names "a boolean parser reporting a conjunction with no satisfying document" as its
    worked example, and `weft_retrieve.fusion.BooleanCombine` (ledger 2.23) is the fuser
    that needs it — `hits=()` alone says *that* an AND matched nothing, never *which*
    operands were disjoint, and the reference's own defect was silently substituting the union
    for exactly that missing explanation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: Query
    hits: tuple[Passage, ...] = ()
    contributors: tuple[str, ...] = ()
    note: str = ""
    ext: ExtMap = Field(default_factory=dict, validate_default=True)


class Passages(BaseModel):
    """Ordered, labelled evidence, ready to enter a prompt — what a `ContextPacker` produces.

    Distinct from `Ranking` because packing is a real decision with a measured answer
    (`10` §1.1's `repack` row) and because the label a citation resolves against is
    assigned here: `weft_generate.payload.Answer` refuses a citation whose marker is not
    one of these passages' labels, and that check needs a type at which the labels are
    known to be final. Final is checked below rather than asserted in this paragraph.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: Query
    passages: tuple[Passage, ...] = ()
    ext: ExtMap = Field(default_factory=dict, validate_default=True)

    @model_validator(mode="after")
    def _every_label_is_present_and_its_own(self) -> "Passages":
        """The labels are final here, so the two ways a packer can get them wrong stop here.

        `ContextPacker` is an open extension point — ledger 2.19's `repack` and any third
        party's packer — and both of its label mistakes are silent everywhere downstream.
        A packer that forgets to label leaves every `Passage.label` empty; `Citation.marker`
        is `min_length=1`, so no citation can ever match one, and the generator's only valid
        output becomes `citations=()` — an uncited answer from a pipeline that asked for
        citations, reported by nothing. A packer that labels by source document rather than
        by passage repeats a label, and `[1]` then resolves to two different passages, which
        is a citation nobody can follow back to *a* passage. Both are "a silent fallback is
        worse than a failure" landing on the one property task 2.9 exists for, and both
        surface in front of a reader rather than at the seam where they were made.

        `Passage.label` keeps its `""` default because a passage genuinely has no label
        before a packer runs. This is the type at which that stops being true.
        """
        blank = tuple(passage.rank for passage in self.passages if not passage.label)
        assigned = [passage.label for passage in self.passages if passage.label]
        repeated = sorted({label for label in assigned if assigned.count(label) > 1})
        if blank or repeated:
            raise ValueError(
                f"a ContextPacker assigns every passage a label of its own, and this set "
                f"does not hold that: passage(s) at rank {list(blank) or 'none'} carry no "
                f"label, and label(s) {repeated or 'none'} are carried by more than one "
                f"passage. A blank label can match no Citation.marker, and a repeated one "
                f"resolves to two passages — both are citations a reader cannot follow."
            )
        return self


class Assessment(BaseModel):
    """What a `Sufficiency` returns: whether the evidence is enough, and whether it could look.

    `observed` is not redundant with `sufficient`. A critic that could not reach a model,
    or was handed no evidence to judge, has learned nothing — and reporting that as
    "not sufficient" is the reference's `has_consensus=True`-on-failure defect with the
    boolean flipped. Two fields, because there are two facts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sufficient: bool
    confidence: float = Field(ge=0.0, le=1.0)
    #: What a follow-up query should go after. Empty when nothing is missing, or when
    #: `observed` is False and the critic has no opinion to offer.
    missing: tuple[str, ...] = ()
    observed: bool


class Scorecard(BaseModel):
    """What a `QueryScorer` measures about a query, before any policy reads it.

    Two plugins, two contracts (ledger 2.25): the scorer measures and the policy decides,
    so a threshold ladder can be replaced by a trained classifier without touching the
    scorer. `scores` is an open mapping rather than a closed set of fields because the
    dimensions a scorer measures are its own — a closed key space here is exactly what
    fitness function 4 exists to forbid.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: Query
    scores: Mapping[str, float]
    #: From a keyword classifier, never a model call — `10` §1.1's `query-scorer` row.
    intents: frozenset[str] = frozenset()
    observed: bool = True

    @field_validator("scores", mode="after")
    @classmethod
    def _every_score_is_a_fraction(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        """Every dimension is 0.0–1.0, so a policy can compare two scorers' output at all.

        Checked here rather than left to each policy: a scorer that answered 0–100 on one
        dimension and 0–1 on another would make every threshold in every policy silently
        wrong, and the failure would look like a tuning problem rather than a bug.
        """
        out_of_range = sorted(name for name, score in value.items() if not 0.0 <= score <= 1.0)
        if out_of_range:
            raise ValueError(
                f"every dimension of a Scorecard is a fraction between 0.0 and 1.0; "
                f"{', '.join(out_of_range)} is not. A policy compares dimensions across "
                f"scorers, so a scorer using its own range makes every threshold wrong."
            )
        return value


class RouteCandidate(BaseModel):
    """One pipeline a router may choose, described in that pipeline's own words.

    `summary` and `cost` come from the candidate pipeline's own `vars:` block, never from
    a table here — which is what makes a third party's pipeline routable on install with
    zero edits under `packages/`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    summary: str = ""
    cost: str = ""


class RuleOutcome(StrEnum):
    """How a `RoutingPolicy` arrived at its choice. A typed value, never an empty string."""

    MATCHED = "matched"
    FELL_THROUGH = "fell-through"
    NEAREST = "nearest"


class Route(BaseModel):
    """A routing decision as data: which pipeline, how it was reached, and what it was told.

    `scorecard` is carried rather than discarded so the decision is auditable from the
    span alone — a router whose output says only "hyde-fanout-rrf" leaves an operator
    asking why, and the answer would live nowhere.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1)
    outcome: RuleOutcome
    #: The matching rule's name when `outcome` is MATCHED; empty otherwise, because there
    #: was no rule to name rather than because one was forgotten.
    rule: str = ""
    scorecard: Scorecard
