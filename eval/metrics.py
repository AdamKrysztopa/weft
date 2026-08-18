"""Prerequisite **V3** (`docs/09-release.md` §4.3) — what a baseline number means.

V3 wants *"the numbers produced before any technique: single-vector top-k, no fusion, no rerank,
no enhancement"*, repeated, *"and each metric carries the interval its own repetitions produced"*.
This module is the arithmetic and the vocabulary; `eval/run_baseline.py` is the measurement and
`eval/check_baseline.py` is the comparison. Nothing here talks to a store, a model or a CLI, so
every rule below is checkable without a corpus — which matters, because the reference's evaluation
package failed on precisely these rules while its plumbing worked (`09` §4.2).

**Four things the reference got wrong are refused here rather than documented.**

* **A metric named for a depth it did not compute.** `ndcg_at_10` was reported over a list the
  retriever had already sliced to four. `measure` raises `DepthTooShallowError` when a requested
  `k` is deeper than the retrieval that fed it, naming both numbers.
* **A failure scored as zero.** A question that cannot be scored comes back as `Unscoreable` — a
  different type, which no caller can average by accident — and the reason travels with it.
* **A mean with no dispersion beside it.** `MetricRecord` cannot be built from one repetition,
  and its `low`/`high` are refused unless they are exactly the span its own values cover.
* **Ground truth accepted and never read.** A judgement is a literal span
  (`eval/check_questions.py`), and it is resolved against the text that came back — so a quote
  that no longer occurs anywhere scores zero visibly rather than being quietly dropped.

**Two granularities, reported side by side, neither a fallback for the other.** The reference scored
a retrieval as a hit when *any* chunk of the right paper came back, as a fallback when its
node-level resolution failed — precision pushed toward 1.0 and two tracks whose numbers meant
different things under one name. Here `quote-*` is the span the answer actually rests on being
inside a retrieved passage, `document-*` is the paper it came from being reached at all, both are
always computed, and the granularity is the first word of every metric name. Read together they
say something neither says alone: a low `quote-recall` with a high `document-recall` is a
chunking or ordering problem, and a low `document-recall` is a retrieval one.

**The known blind spot, stated because a reader of the numbers needs it.** A quote is resolved by
containment, so a span that falls across a chunk boundary cannot be found inside any single
retrieved passage and scores as a miss. That is a floor on `quote-*`, not a bug, and it is why
`document-*` is recorded next to it rather than replaced by it. Resolving spans by offset would
need the extracted text of every document, which is an `Extractor` call, which is `async` — and
`eval/` gets no second `asyncio.run` (fitness function 7(a)).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from math import fsum, isclose, log2
from typing import Final

from check_questions import Question
from pydantic import BaseModel, ConfigDict, Field, model_validator

#: How close a recorded `mean` must be to the mean of its own `values` to be believed. Floats
#: written to JSON and read back do not compare equal to the sum that produced them, and a
#: tolerance that had to be chosen for anything a *later run* is judged by would be the constant
#: `09` §4.3 forbids — this one is a float-repr allowance on a value that is recomputed, never a
#: reproduction tolerance.
_MEAN_TOLERANCE: Final[float] = 1e-9


class MetricsError(Exception):
    """Something the harness was asked to measure cannot be measured as asked.

    Not a `WeftError`: nothing under `eval/` is part of the engine, and importing the kernel's
    error base here would be the first thread of the subsystem `tests/architecture/
    test_eval_is_not_a_subsystem.py` exists to keep out.
    """


class DepthTooShallowError(MetricsError):
    """A metric was asked for at a `k` deeper than the retrieval that would feed it.

    The reference reported `ndcg_at_10` over four candidates. V4 states the rule — *"the `k` in a
    metric's name equals the `k` it computed"* — and this is where it refuses. The comparison is
    against the depth that was **requested**, not the number of results that came back: a store
    holding three nodes answers a request for ten with three, and that is a fact about the
    corpus rather than a mis-named metric.
    """


class Granularity(StrEnum):
    """The unit a judgement is resolved at, and the first word of every metric name."""

    #: The supporting span itself, found inside a retrieved passage. What the answer rests on.
    QUOTE = "quote"
    #: The document the span belongs to, reached by any retrieved passage drawn from it.
    DOCUMENT = "document"


class ExclusionKind(StrEnum):
    """Why a question contributed no value to a metric — never zero, always a reason."""

    #: The question carries no judgement at all: an unanswerable one, which V2 requires the set
    #: to contain and which no retrieval metric can score.
    NO_JUDGEMENT = "no-judgement"
    #: The measurement itself did not happen — the command failed, or answered something this
    #: harness could not read. V4's *"a failed metric is an error, never a zero"*.
    MEASUREMENT_FAILED = "measurement-failed"


class Hit(BaseModel):
    """One retrieved passage, as the thing being scored rather than as the store returned it.

    `documents` is already resolved to manifest ids by the caller: which corpus document a
    `SourceId` names is the harness's own staging decision (`eval/run_baseline.py`), and a
    metric that had to know about file paths would be a metric that stops working the day the
    corpus moves.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int = Field(ge=1)
    node_id: str = Field(min_length=1)
    score: float
    documents: tuple[str, ...] = ()
    content: str


class Judged(BaseModel):
    """One question's ground truth resolved against one ranking, at one granularity.

    Two views of the same resolution, because the metrics ask two different questions of it:
    `relevant` is per *rank* (did the passage at this position satisfy anything?) and
    `first_rank` is per *judgement* (how far down was this piece of ground truth found, if at
    all?). Deriving either from the other is possible and would be wrong — a rank can satisfy
    two judgements, and a judgement can be satisfied at several ranks.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    granularity: Granularity
    relevant: tuple[bool, ...] = ()
    first_rank: tuple[int | None, ...] = ()

    @property
    def scoreable(self) -> bool:
        """Whether there is any ground truth here to score against."""
        return bool(self.first_rank)


class Unscoreable(BaseModel):
    """A question that contributed nothing to any metric, and why.

    Returned instead of a set of scores, so that "could not be measured" and "measured zero"
    are different types rather than the same float. The reference's aggregators could not tell them
    apart, and two of its three never looked.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ExclusionKind
    detail: str = Field(min_length=1)


class Scores(BaseModel):
    """Every metric one question produced against one ranking, keyed by the metric's own name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: Mapping[str, float]


class Excluded(BaseModel):
    """One question, in one repetition, that a metric could not take a value from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str = Field(min_length=1)
    repetition: int = Field(ge=1)
    kind: ExclusionKind
    detail: str = Field(min_length=1)


class MetricRecord(BaseModel):
    """One metric across every repetition of a baseline — V3's artefact, one row of it.

    `low` and `high` are the **minimum and maximum the repetitions actually produced**, and that
    is the whole point of the file: *"a later run reproduces the baseline when every metric falls
    inside that recorded interval"*, so the tolerance is a measurement of this system's own
    variability rather than a number somebody liked. A deterministic system records a zero-width
    interval and admits no drift at all, which `09` §4.3 says is correct and strict.

    Every invariant below is refused at construction rather than checked by whoever reads the
    file, because the file is read by a later run deciding whether it reproduced — and a
    hand-widened bound would make every later run pass.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = Field(min_length=1)
    #: The `k` the name carries, and the retrieval depth it was computed over. Equal by
    #: construction (`measure` refuses otherwise); recorded so a reader of the file can check.
    depth: int = Field(ge=1)
    values: tuple[float, ...]
    mean: float
    low: float
    high: float
    n_scored: int = Field(ge=0)
    #: How many measurements this metric took no value from. The reasons live once on the run
    #: that holds this record (`eval/run_baseline.py`), which asserts the two agree — a count
    #: here and a list there is the shape that keeps a file of a hundred metrics readable
    #: without letting either become a number nothing backs.
    n_excluded: int = Field(ge=0)

    @model_validator(mode="after")
    def _the_interval_is_the_one_these_values_span(self) -> MetricRecord:
        if len(self.values) < 2:
            raise ValueError(
                f"{self.metric}: a baseline records an interval only if it was run more than "
                f"once — got {len(self.values)} repetition(s). `docs/09-release.md` §4.3: a "
                f"baseline that was run once 'records no interval and no later run can be "
                f"judged against it'"
            )
        if self.low != min(self.values) or self.high != max(self.values):
            raise ValueError(
                f"{self.metric}: low/high must be the interval these repetitions spanned — "
                f"values {self.values} span [{min(self.values)}, {max(self.values)}], file "
                f"says [{self.low}, {self.high}]. A widened bound is a chosen tolerance"
            )
        if not isclose(self.mean, mean_of(self.values), rel_tol=0.0, abs_tol=_MEAN_TOLERANCE):
            raise ValueError(
                f"{self.metric}: mean {self.mean} is not the mean of {self.values} "
                f"({mean_of(self.values)})"
            )
        if not self.low <= self.mean <= self.high:
            raise ValueError(
                f"{self.metric}: mean {self.mean} is outside [{self.low}, {self.high}], which "
                f"an arithmetic mean of those values cannot be — see `mean_of`"
            )
        return self

    def outside(self, value: float) -> bool:
        """Whether `value` falls outside the interval this baseline's repetitions spanned."""
        return not self.low <= value <= self.high


def mean_of(values: Sequence[float]) -> float:
    """The arithmetic mean, kept inside the range of its own values.

    The mean of a set is always between its minimum and its maximum. That this needs saying at
    all is float representation and not statistics: three identical values summed and divided
    come back one unit in the last place *below* the value itself, and a baseline whose recorded
    mean sits a hair outside its own zero-width interval would be a file that reads as corrupt
    to every check downstream — including the one that judges a later run. Clamping is exact
    here in the sense that matters: it moves the answer to the nearest representable number the
    true mean can be, never past it.
    """
    if not values:
        message = "the mean of no values is not a number; the caller must exclude instead"
        raise MetricsError(message)
    computed = fsum(values) / len(values)
    return min(max(computed, min(values)), max(values))


def recall_at_k(first_rank: Sequence[int | None], k: int) -> float:
    """The share of this question's judgements that were reached within the first `k` results.

    The denominator is the ground truth the question carries, which is known — unlike the number
    of units in the index that would satisfy it, which is not. That is why this is recall over
    judgements and says so.
    """
    if not first_rank:
        message = "recall over no judgements is not a number; the caller must exclude instead"
        raise MetricsError(message)
    found = sum(1 for rank in first_rank if rank is not None and rank <= k)
    return found / len(first_rank)


def reciprocal_rank_at_k(relevant: Sequence[bool], k: int) -> float:
    """One over the rank of the first relevant result, or zero if none is within `k`.

    A zero here is a measurement — nothing relevant came back — not a failure. The two are kept
    apart one level up, in `measure`, which never returns a number for a question it could not
    score at all.
    """
    for index, is_relevant in enumerate(relevant[:k], start=1):
        if is_relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(relevant: Sequence[bool], k: int) -> float:
    """Discounted gain over the first `k` results, against the best ordering of the same hits.

    **The normaliser is the ideal ordering of what was retrieved**, not of what exists: how many
    units in the index would satisfy the judgement is unknowable without enumerating the store,
    and inventing a denominator is how a number stops meaning anything. So this measures
    ordering — 1.0 says every relevant result came back above every irrelevant one — and it is
    reported next to recall, which measures how much was reached.
    """
    gains = [1.0 if is_relevant else 0.0 for is_relevant in relevant[:k]]
    found = int(fsum(gains))
    if not found:
        return 0.0
    discounted = fsum(gain / log2(position + 1) for position, gain in enumerate(gains, start=1))
    ideal = fsum(1.0 / log2(position + 1) for position in range(1, found + 1))
    return discounted / ideal


def judge(question: Question, hits: Sequence[Hit], granularity: Granularity) -> Judged:
    """Resolve this question's ground truth against a ranking, at one granularity."""
    if granularity is Granularity.QUOTE:
        judgements: tuple[str, ...] = tuple(quote.text for quote in question.quote)
        satisfies = _passage_carries_the_span
    else:
        judgements = tuple(dict.fromkeys(question.relevant_documents))
        satisfies = _passage_came_from_the_document
    relevant = tuple(
        any(satisfies(hit, judgement) for judgement in judgements) for hit in _by_rank(hits)
    )
    first_rank = tuple(
        next((hit.rank for hit in _by_rank(hits) if satisfies(hit, judgement)), None)
        for judgement in judgements
    )
    return Judged(granularity=granularity, relevant=relevant, first_rank=first_rank)


def measure(
    question: Question, hits: Sequence[Hit], *, depths: Iterable[int], retrieval_depth: int
) -> Scores | Unscoreable:
    """Every metric this question yields against this ranking, or why it yields none.

    `depths` are the `k`s to report at and `retrieval_depth` is what the run actually asked the
    store for; naming a `k` deeper than that is refused rather than reported, which is V4's rule
    and the reference's `ndcg_at_10`-over-four defect.
    """
    wanted = tuple(depths)
    too_deep = sorted(k for k in wanted if k > retrieval_depth)
    if too_deep:
        message = (
            f"metrics were asked for at depth(s) {too_deep} over a retrieval of "
            f"{retrieval_depth}. A metric's name must state the k it computed"
        )
        raise DepthTooShallowError(message)

    resolved = {member: judge(question, hits, member) for member in Granularity}
    if not any(judged.scoreable for judged in resolved.values()):
        return Unscoreable(
            kind=ExclusionKind.NO_JUDGEMENT,
            detail=(
                f"{question.id} is {question.kind.value} and carries no judgement: an "
                f"unanswerable question names no document and quotes no span, so a retrieval "
                f"metric has nothing to score it against"
            ),
        )
    values: dict[str, float] = {}
    for member, judged in resolved.items():
        for k in wanted:
            values[f"{member.value}-recall@{k}"] = recall_at_k(judged.first_rank, k)
            values[f"{member.value}-mrr@{k}"] = reciprocal_rank_at_k(judged.relevant, k)
            values[f"{member.value}-ndcg@{k}"] = ndcg_at_k(judged.relevant, k)
    return Scores(values=values)


def _by_rank(hits: Sequence[Hit]) -> tuple[Hit, ...]:
    """The ranking in rank order, whatever order the caller happened to hold it in."""
    return tuple(sorted(hits, key=lambda hit: hit.rank))


def _passage_carries_the_span(hit: Hit, span: str) -> bool:
    """Exact containment — the same rule that made the quote believable in the first place.

    `tests/docs/test_question_set.py` believes a quote only because it read it back out of the
    document, byte for byte, and deliberately refuses to normalise whitespace or match fuzzily:
    a span that stopped matching is the ground truth no longer describing what the pipeline
    reads. Scoring the same span by a looser rule than the one that verified it would measure a
    different claim from the one the question set makes.
    """
    return span in hit.content


def _passage_came_from_the_document(hit: Hit, document: str) -> bool:
    """Whether this passage traces to that corpus document, by the lineage the store returned."""
    return document in hit.documents
