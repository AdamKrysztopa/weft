"""The `Metric` contracts — published here, never by the kernel. Two of them, not one.

Task **4.1** shipped a single `Metric`/`Sample` pair and left the split open on purpose: `Sample`
was "deliberately narrow, and provisional," carrying only what the one demonstration metric
needed, with a retrieval/generation evaluator split flagged as the question 4.2 would settle
"once 21 real implementations say which shape they actually need — not
pre-decided here by guessing." Task **4.2** is that task, and the 21 implementations say the shape
plainly: the four IR metrics (`weft_eval.ir_metrics`) need a ranked list of retrieved passage ids
and a set of relevant ids, and never touch a prediction or reference string at all; the eleven
traditional generation metrics and three of the six LLM judges need `prediction`/`reference` text;
the other three LLM judges (`context-recall`, `context-relevance`) need retrieved passage *text*
and a query, and the traditional metrics never touch it. A `Sample` wide enough for all of that —
ranked ids, a relevance set, prediction, reference, retrieved passage text — is exactly the
grab-bag `docs/02-extension-model.md` section 1 already forbids: "when a caller needs only half an
interface, that is two contracts."

**So: two contracts, not a widened one.** `GenerationMetric`/`GenerationSample` for anything that
scores a `prediction` against a `reference`, `RetrievalMetric`/`RetrievalSample` for anything that
scores a ranked list against a relevance judgement. Both still return `Outcome[MetricScore]` — the
result shape is not what needed splitting, the input was — and both still carry `config_model`,
`evaluate` as `async def` unconditionally (G6), and the identical mutual-exclusivity guarantee 4.1
built: `MetricScore` appears only on `Produced`, so there is no `score` sitting beside an unread
`error`. Everything task 4.1's docstring said about *why* that shape is right stays true here
unchanged; only the input type it scores has a second member now.

**`GenerationSample` grew one field since 4.1: `contexts`.** `faithfulness` — a generation-side
judge — needs the retrieved passages the answer is checked against, alongside the
`prediction`/`reference` every other generation metric already uses; `contexts` defaults to `()`
so every metric task 4.1 shipped and every one of 4.2's eleven traditional/three self-contained
judges that never reads it is unaffected. Widening by one optional field used by a minority is the
allowed case `02` §1's rule doesn't forbid — a genuinely narrow addition, not the wholesale
grab-bag the retrieval/generation split exists to avoid.

**`RetrievalSample` is new.** `query`, `retrieved` (an ordered tuple of `RetrievedPassage`, rank
implied by position — index 0 is rank 1), `relevant_ids` (the ground-truth relevance set the four
IR metrics score against) and an optional `reference` (`context-recall`'s own need: it judges
retrieved passages against a reference *answer*, not against the query). `RetrievedPassage.text`
defaults to `""` because the four IR metrics never read it — they score ids and rank positions
only — while `context-recall`/`context-relevance` require it and construct their own `Failed` when
it is missing, the same "the type stays honest about what is optional, the metric enforces what it
needs" split `weft_retrieve.rerank.LlmRerank` already makes for `payload.origin`.

**Q6 — how a metric declares that it needs credentials or a model download, task 4.7.** The
house rule is G4's: a capability is derived at registration, never declared in a hand-maintained
table — a derived boolean, the same shape `weft_eval.embedding_metrics.BERT_SCORE_AVAILABLE`'s
own `importlib.util.find_spec` check uses, though no comparably derivable check for "needs an
LLM" exists to reuse, so this contract states it explicitly instead. `GenerationMetric`/
`RetrievalMetric` extend the identical
mechanism task 3.1 already generalised for `Command.permission_class`, rather than inventing a
second one: `required_declarations = ("runs_in_gate",)`, read by `weft_kernel.registry`'s own
`_require_declarations_present` — unchanged, zero new kernel lines — so a metric that never
states whether it runs offline fails to *register* at all, built-in or a stranger's alike,
exactly as a `Command` that never states its `permission_class` does today. `runs_in_gate` is a
`ClassVar[bool]` every implementation must write (`True`/`False`, never inherited-by-silence);
the optional `gate_unsafe_reason: ClassVar[str]` a `False` metric may also state is read
defensively (`getattr(..., "gate_unsafe_reason", "")`), the same convention-not-seam status
`intact` already has, because *why* is a message-quality concern the registry itself has no
business enforcing. `weft_eval.offline.gate_subset` is the reading half: given a `Registry`, it
derives which registered metric names actually declared `True`, never a second, hand-maintained
list of "the offline ones" to keep in sync by hand.

**Every metric's own `evaluate` decides `NothingToProduce` vs `Failed` for its own missing input,
consistently applied across the suite** — the one place 4.2 makes a rule of what could otherwise
drift metric by metric: an empty reference (or an empty relevant-id set, its retrieval-side
analogue) is `NothingToProduce` *unconditionally*, regardless of what the prediction/retrieval
carries, never a computed number. Two functionally identical checks can disagree with each other
here in exactly the way that goes unnoticed until compared side by side — one always returning
`1.0` on an empty reference, another returning `1.0` only when the prediction was *also* empty,
with nothing recording that the two "trailing" edge cases were shaped differently. Weft flattens
the two into one rule rather than carrying the inconsistency forward: nothing to compare
against is nothing to compare against, independent of what the other side of the comparison
happens to hold. A caller who wants "1.0 because both sides are the empty string" is asking a
different, legitimate question — `exact-match` already answers it, honestly, as an exact match.
"""

from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.payload import Outcome

#: Fitness function 6's subject for this contract. A fresh `1.0.0` for both halves of the split
#: rather than carrying task 4.1's `METRIC_CONTRACT_VERSION` forward onto one arm of it — `Metric`
#: does not survive the split as a distinguished "the real one", so neither successor inherits its
#: version number.
GENERATION_METRIC_CONTRACT_VERSION = "1.0.0"
RETRIEVAL_METRIC_CONTRACT_VERSION = "1.0.0"


class GenerationSample(BaseModel):
    """One (query, prediction, reference[, contexts]) tuple a `GenerationMetric` scores.

    `prediction` is `None` when nothing was generated for this sample yet — distinct from an
    empty string, which is a real (if unhelpful) prediction. `contexts` is the retrieved passage
    text a groundedness judge (`faithfulness`) checks the prediction against; every metric that
    does not need it leaves it at `()`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    prediction: str | None = None
    reference: str
    contexts: tuple[str, ...] = ()


class RetrievedPassage(BaseModel):
    """One retrieved item, in the rank position `RetrievalSample.retrieved` places it at.

    `text` defaults to `""` because the four IR metrics score `id` and rank alone; a judge metric
    that needs the passage's own content refuses a `RetrievedPassage` that never carries it, rather
    than this type carrying a required field three-quarters of its consumers ignore.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    text: str = ""


class RetrievalSample(BaseModel):
    """A ranked retrieval result, and what it should have retrieved, a `RetrievalMetric` scores.

    `retrieved` is rank-ordered by tuple position, matching the ordering `weft_retrieve.payload.
    Ranking.hits` already carries — index 0 is the top result. `relevant_ids` is the ground-truth
    relevance judgement the four IR metrics score against; `reference` is `context-recall`'s own
    need, a reference *answer* to check retrieved passages against, distinct from `relevant_ids`
    and left unset by every metric that does not use it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    retrieved: tuple[RetrievedPassage, ...] = ()
    relevant_ids: frozenset[str] = frozenset()
    reference: str | None = None


class MetricScore(BaseModel):
    """A metric's answer for one sample — the `Produced` payload, never seen on a `Failed`.

    `metric_name` is the name a human reads, computed by the plugin from its own configuration —
    not the registered plugin name. Shared by both `GenerationMetric` and `RetrievalMetric`: the
    result shape never needed splitting, only the input did.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_name: str
    value: float


@runtime_checkable
class GenerationMetric(Protocol):
    """Scores one `GenerationSample` — a prediction against a reference (and, sometimes, context).

    `evaluate` is `async def` unconditionally (G6) and returns `Outcome[MetricScore]`: a score
    (`Produced`), a legitimate absence of anything to score (`NothingToProduce`), or a failure
    (`Failed`) — see `weft_eval.contract`'s module docstring for the full reasoning.
    """

    if TYPE_CHECKING:
        #: See `weft_extract.contract`'s module docstring for the `if TYPE_CHECKING:` /
        #: assign-after-the-class-body split this repeats: declaring this in the body would make
        #: it a required `isinstance` member for no capability reason.
        version: ClassVar[str]
        #: See the module docstring's Q6 paragraph — names the `ClassVar` every implementation
        #: must carry (`runs_in_gate`); it does not carry the value itself.
        required_declarations: ClassVar[tuple[str, ...]]

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]: ...


GenerationMetric.version = GENERATION_METRIC_CONTRACT_VERSION
GenerationMetric.required_declarations = ("runs_in_gate",)


@runtime_checkable
class RetrievalMetric(Protocol):
    """Scores one `RetrievalSample` — a ranked result against a relevance judgement.

    Identical shape to `GenerationMetric` in every respect but the payload type it accepts — see
    the module docstring for why the input, and only the input, needed two contracts rather than
    one wide `Sample`.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]
        #: See `GenerationMetric`'s identical declaration, and the module docstring's Q6
        #: paragraph.
        required_declarations: ClassVar[tuple[str, ...]]

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]: ...


RetrievalMetric.version = RETRIEVAL_METRIC_CONTRACT_VERSION
RetrievalMetric.required_declarations = ("runs_in_gate",)
