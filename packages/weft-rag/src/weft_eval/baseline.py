"""Prerequisite **V3** (`docs/09-release.md` §4.3) — what a baseline number means.

V3 wants *"the numbers produced before any technique: single-vector top-k, no fusion, no rerank,
no enhancement"*, repeated, *"and each metric carries the interval its own repetitions
produced"*. This module is the arithmetic, the vocabulary and — since repair **R22.4a** — the
published run's own shape: `eval/run_baseline.py` is the measurement and `eval/check_baseline.py`
is the comparison, but what a baseline *is* now lives here, importable from the installed
`weft-rag` wheel with no checkout. Nothing here talks to a store, a model or a CLI, so every rule
below is checkable without a corpus — which matters, because an evaluation package can fail on
precisely these rules while its plumbing works (`09` §4.2).

**Four failure modes are refused here rather than documented.**

* **A metric named for a depth it did not compute.** `ndcg_at_10` was reported over a list the
  retriever had already sliced to four. `measure` raises `DepthTooShallowError` when a requested
  `k` is deeper than the retrieval that fed it, naming both numbers.
* **A failure scored as zero.** A question that cannot be scored comes back as `Unscoreable` — a
  different type, which no caller can average by accident — and the reason travels with it.
* **A mean with no dispersion beside it.** `MetricRecord` cannot be built from one repetition,
  and its `low`/`high` are refused unless they are exactly the span its own values cover.
* **Ground truth accepted and never read.** A judgement is a literal span
  (`weft_eval.question_set`), and it is resolved against the text that came back — so a quote
  that no longer occurs anywhere scores zero visibly rather than being quietly dropped.

**Two granularities, reported side by side, neither a fallback for the other.** Scoring a
retrieval as a hit when *any* chunk of the right paper came back, as a fallback for when
node-level resolution fails, pushes precision toward 1.0 and blends two tracks whose numbers mean
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

**`BaselineReport`, carried from `eval/run_baseline.py` at R22.4a.** One baseline: what was
measured, over what, how many times, and the persisted run it measured against. `record` is a
real `weft_eval.run_record.RunRecord` — the same type `weft eval run`, `weft eval compare` and
`weft trace` all read — so a later `weft eval compare` between this run and one taken through the
shipped CLI is comparing two instances of one type, not two shapes that happen to look similar.
Refuses fewer than two repetitions at construction, which is V3's own failure clause — *"or the
baseline was run once, in which case it records no interval and no later run can be judged
against it"* — enforced where the file is built, so the file cannot exist. `load_baseline_report`
is the reader, renamed from `eval/run_baseline.py`'s own `load_run` so its name says what it
reads now that it is a public entry point rather than a hand-run script's own helper.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from math import fsum, isclose, log2
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_eval.question_set import Question
from weft_eval.run_record import RunRecord
from weft_kernel.errors import WeftError
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage

#: How close a recorded `mean` must be to the mean of its own `values` to be believed. Floats
#: written to JSON and read back do not compare equal to the sum that produced them, and a
#: tolerance that had to be chosen for anything a *later run* is judged by would be the constant
#: `09` §4.3 forbids — this one is a float-repr allowance on a value that is recomputed, never a
#: reproduction tolerance.
_MEAN_TOLERANCE: Final[float] = 1e-9


class BaselineScoringError(WeftError):
    """Something the harness was asked to measure cannot be measured as asked.

    A `WeftError`, since R22.4a: this module is part of the installed `weft-rag` wheel, scored by
    any caller holding it — not only `eval/run_baseline.py`'s own subprocess — so a refusal here
    reaches a CLI able to render it the same way as any other engine failure, rather than an
    exception type a caller has to know to special-case.
    """


class DepthTooShallowError(BaselineScoringError):
    """A metric was asked for at a `k` deeper than the retrieval that would feed it.

    Reporting `ndcg_at_10` over four candidates is exactly this mistake. V4 states the rule —
    *"the `k` in a metric's name equals the `k` it computed"* — and this is where it refuses. The
    comparison is against the depth that was **requested**, not the number of results that came
    back: a store holding three nodes answers a request for ten with three, and that is a fact
    about the corpus rather than a mis-named metric.
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
    are different types rather than the same float — collapsing them into one lets an aggregator
    average over both without ever checking which is which.
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


class BaselineReport(BaseModel):
    """One baseline: what was measured, over what, how many times, and the persisted run it
    measured against.

    `record` is a real `weft_eval.run_record.RunRecord` — the same type `weft eval run`,
    `weft eval compare` and `weft trace` all read — so a later `weft eval compare` between this
    run and one taken through the shipped CLI is comparing two instances of one type, not two
    shapes that happen to look similar. Refuses fewer than two repetitions at construction, which
    is V3's own failure clause — *"or the baseline was run once, in which case it records no
    interval and no later run can be judged against it"* — enforced where the file is built, so
    the file cannot exist.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recorded_at: str = Field(min_length=1)
    #: The corpus name and manifest tiers this run selected — harness bookkeeping that sits
    #: beside `record.corpus` rather than duplicating it: `record.corpus.digest` is the one
    #: digest (`test_baseline_shape.py` recomputes it from `documents` below through the same
    #: `weft_eval.run_record.corpus_identity` this harness calls), and `tiers`/`documents` are
    #: what let a reader — and a gate test — say *which* manifest entries it is a digest of.
    corpus_name: str = Field(min_length=1)
    tiers: tuple[str, ...]
    #: The one `Extractor` this baseline's pipeline named — see `eval/run_baseline.py`'s
    #: `EXTRACTOR_SUFFIXES`.
    extractor: str = Field(min_length=1)
    documents: tuple[str, ...]
    #: Derived from the tiers, never declared: false the moment an `operator` document is in.
    reproducible: bool
    record: RunRecord
    questions: tuple[str, ...]
    repeats: int = Field(ge=2)
    #: What the store was asked for per question. Every `@k` metric's `k` is within it.
    retrieval_depth: int = Field(ge=1)
    wall_clock_seconds: float = Field(ge=0.0)
    metrics: tuple[MetricRecord, ...]
    #: Every measurement that produced no value, with the reason it produced none.
    excluded: tuple[Excluded, ...] = ()

    @model_validator(mode="after")
    def _every_metrics_exclusions_are_the_ones_this_run_gave_reasons_for(self) -> BaselineReport:
        """V4's *"aggregates... report how many were excluded"*, joined back to the reasons."""
        disagreeing = sorted(
            record.metric for record in self.metrics if record.n_excluded != len(self.excluded)
        )
        if disagreeing:
            raise ValueError(
                f"metrics whose n_excluded is not the {len(self.excluded)} exclusion(s) this run "
                f"recorded reasons for: {disagreeing}"
            )
        return self

    def metric(self, name: str) -> MetricRecord | None:
        """The record for `name`, or `None` when this run did not measure it."""
        return next((record for record in self.metrics if record.metric == name), None)


def load_baseline_report(path: Path) -> BaselineReport:
    """One written baseline, refused if anything in it disagrees with itself."""
    return BaselineReport.model_validate_json(path.read_text(encoding="utf-8"))


class IncomparableBaselinesError(BaselineScoringError):
    """Two runs did not measure the same thing, so a reproduction verdict would mean nothing.

    `reasons` carries every identity difference found — never only the first — because a
    reader deciding whether to re-run needs to know everything that changed, not just
    whichever field this module happened to check first.
    """

    def __init__(self, message: str, *, reasons: tuple[str, ...]) -> None:
        super().__init__(message)
        self.reasons = reasons


class ProvenanceField(StrEnum):
    """What an installation says about itself — never refused on, always reported."""

    DISTRIBUTION = "distribution"
    CONTRACT_VERSION = "contract_version"
    APPLIES_TO = "applies_to"


class ProvenanceDifference(BaseModel):
    """One stage's installation differing between two runs that otherwise measure the same thing.

    Reported beside the verdict rather than refused on: `09` §4.3's V3 judges reproduction by
    the metric intervals, and any behavioural effect a renamed distribution, a bumped contract
    version or a widened `applies_to` actually has is caught there, not here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str
    field: ProvenanceField
    published: str | None
    later: str | None


class MetricVerdict(BaseModel):
    """One published metric, judged against what the later run measured for the same name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    low: float
    high: float
    later: float | None
    inside: bool


class Reproduction(BaseModel):
    """What `judge_reproduction` found: a verdict per published metric, plus what moved beside it.

    `reproduced` requires at least one verdict — an empty `verdicts` is not vacuously a
    reproduction, it is a published baseline that recorded no metrics at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdicts: tuple[MetricVerdict, ...]
    provenance: tuple[ProvenanceDifference, ...]
    published_distributions: tuple[str, ...]
    later_distributions: tuple[str, ...]

    @property
    def reproduced(self) -> bool:
        """Whether every published metric fell inside the interval its repetitions spanned."""
        return bool(self.verdicts) and all(verdict.inside for verdict in self.verdicts)


#: Per-stage fields a pipeline document states, and a reproduction is refused if any differs.
#: `distribution`, `contract_version` and `applies_to` are deliberately absent — those are what
#: an installation says about itself, reported through `ProvenanceDifference` instead of refused
#: on, because any effect they have must still land inside the metric intervals V3 checks.
_IDENTITY_STAGE_FIELDS: Final[tuple[str, ...]] = (
    "contract",
    "use",
    "config",
    "fallback",
    "provenance",
)

_IDENTITY_PIPELINE_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "vars",
    "unapplied_operators",
    "unplaced_contributions",
)

_IDENTITY_RECORD_FIELDS: Final[tuple[str, ...]] = ("corpus", "model_versions")

_IDENTITY_REPORT_FIELDS: Final[tuple[str, ...]] = ("retrieval_depth", "questions")


def judge_reproduction(published: BaselineReport, later: BaselineReport) -> Reproduction:
    """Whether `later` reproduces `published` — `09` §4.3's V3, plus what installation moved.

    Refuses the comparison, naming every reason, when the two runs did not measure the same
    thing: a different corpus, stage, config, model, depth or question set. What the installed
    plugin says about itself is never a refusal reason — it is carried onto the returned
    `Reproduction` instead, because whatever behavioural effect it has is exactly what the
    metric intervals would catch.
    """
    published_pipeline = published.record.resolved_pipeline
    later_pipeline = later.record.resolved_pipeline
    reasons = (
        *_stage_identity_reasons(published_pipeline, later_pipeline),
        *_field_reasons(
            published_pipeline.model_dump(mode="json"),
            later_pipeline.model_dump(mode="json"),
            _IDENTITY_PIPELINE_FIELDS,
            prefix="pipeline ",
        ),
        *_field_reasons(
            published.record.model_dump(mode="json"),
            later.record.model_dump(mode="json"),
            _IDENTITY_RECORD_FIELDS,
        ),
        *_field_reasons(
            published.model_dump(mode="json"),
            later.model_dump(mode="json"),
            _IDENTITY_REPORT_FIELDS,
        ),
    )
    if reasons:
        message = (
            "these two baselines measure different things, so neither reproduces the other: "
            + "; ".join(reasons)
        )
        raise IncomparableBaselinesError(message, reasons=reasons)
    return Reproduction(
        verdicts=_metric_verdicts(published, later),
        provenance=_provenance_differences(published_pipeline, later_pipeline),
        published_distributions=tuple(published.record.active_distributions),
        later_distributions=tuple(later.record.active_distributions),
    )


def _field_reasons(
    published: Mapping[str, object],
    later: Mapping[str, object],
    fields: tuple[str, ...],
    *,
    prefix: str = "",
) -> tuple[str, ...]:
    """`f"{prefix}{field} differs (...)"` for every field of `fields` that disagrees."""
    return tuple(
        f"{prefix}{field} differs ({published[field]!r} vs {later[field]!r})"
        for field in fields
        if published[field] != later[field]
    )


def _stage_identity_reasons(
    published: ResolvedPipeline, later: ResolvedPipeline
) -> tuple[str, ...]:
    """Every stage-level identity reason: presence, order, and the fields a document states."""
    published_by_id = {stage.id: stage for stage in published.stages}
    later_by_id = {stage.id: stage for stage in later.stages}
    reasons = [
        f"stage '{stage_id}' is only in the published run"
        for stage_id in published_by_id
        if stage_id not in later_by_id
    ]
    reasons += [
        f"stage '{stage_id}' is only in the later run"
        for stage_id in later_by_id
        if stage_id not in published_by_id
    ]
    published_ids = tuple(stage.id for stage in published.stages)
    later_ids = tuple(stage.id for stage in later.stages)
    if set(published_ids) == set(later_ids) and published_ids != later_ids:
        reasons.append(f"stage order differs ({published_ids} vs {later_ids})")
    for stage_id, published_stage in published_by_id.items():
        later_stage = later_by_id.get(stage_id)
        if later_stage is None:
            continue
        reasons.extend(_stage_field_reasons(stage_id, published_stage, later_stage))
    return tuple(reasons)


def _stage_field_reasons(
    stage_id: str, published: ResolvedStage, later: ResolvedStage
) -> tuple[str, ...]:
    """Every identity field (never a provenance field) that differs between two matched stages."""
    published_dump = published.model_dump(mode="json")
    later_dump = later.model_dump(mode="json")
    return tuple(
        f"stage '{stage_id}' {field} differs ({published_dump[field]!r} vs {later_dump[field]!r})"
        for field in _IDENTITY_STAGE_FIELDS
        if published_dump[field] != later_dump[field]
    )


def _provenance_differences(
    published: ResolvedPipeline, later: ResolvedPipeline
) -> tuple[ProvenanceDifference, ...]:
    """Every reported (never refused-on) installation difference, in published stage order."""
    later_by_id = {stage.id: stage for stage in later.stages}
    differences: list[ProvenanceDifference] = []
    for stage in published.stages:
        counterpart = later_by_id.get(stage.id)
        if counterpart is not None:
            differences.extend(_stage_provenance_differences(stage, counterpart))
    return tuple(differences)


def _stage_provenance_differences(
    published: ResolvedStage, later: ResolvedStage
) -> tuple[ProvenanceDifference, ...]:
    """`DISTRIBUTION`, `CONTRACT_VERSION`, then `APPLIES_TO`, only where the two disagree."""
    published_applies = json.dumps(published.model_dump(mode="json")["applies_to"], sort_keys=True)
    later_applies = json.dumps(later.model_dump(mode="json")["applies_to"], sort_keys=True)
    candidates = (
        (ProvenanceField.DISTRIBUTION, published.distribution, later.distribution),
        (ProvenanceField.CONTRACT_VERSION, published.contract_version, later.contract_version),
        (ProvenanceField.APPLIES_TO, published_applies, later_applies),
    )
    return tuple(
        ProvenanceDifference(stage=published.id, field=field, published=before, later=after)
        for field, before, after in candidates
        if before != after
    )


def _metric_verdicts(published: BaselineReport, later: BaselineReport) -> tuple[MetricVerdict, ...]:
    """One `MetricVerdict` per metric `published` recorded, in the order it recorded them."""
    verdicts: list[MetricVerdict] = []
    for record in published.metrics:
        found = later.metric(record.metric)
        later_mean = found.mean if found is not None else None
        inside = later_mean is not None and not record.outside(later_mean)
        verdicts.append(
            MetricVerdict(
                metric=record.metric,
                low=record.low,
                high=record.high,
                later=later_mean,
                inside=inside,
            )
        )
    return tuple(verdicts)


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
        raise BaselineScoringError(message)
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
        raise BaselineScoringError(message)
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
    and exactly the `ndcg_at_10`-over-four defect described above.
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
