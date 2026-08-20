"""Aggregating many observations of one metric — task 4.3, the aggregate half of V4.

`docs/09-release.md` §4 V4: *"aggregates exclude errored metrics and report how many were
excluded; every reported number carries the dispersion it was measured with, not only a mean;
and the `k` in a metric's name equals the `k` it computed."* Task 4.1 carried V4's *result* shape
(`GenerationMetric.evaluate`/`RetrievalMetric.evaluate` return `Outcome[MetricScore]`, so a failed
metric cannot carry a score). This module carries the *aggregate* shape — what happens when many
of those outcomes, from many samples, are folded into one number a human reads.

**Exclusion, counted rather than merely honoured.** The reference has exactly one aggregator in its
whole tree that reads `error` before averaging at all (`open_rag_evaluator.py:263,271`,
`.phase4-reference-recon.md` §5) — and even that one reports a *success* count, never an *exclusion*
count, so a reader who wants to know how many observations were thrown away has to subtract it
from the total by hand. `MetricAggregate.excluded` below is that count, on the type, not left to
be reconstructed.

**No bare mean, by construction.** `aggregate()` has exactly one success path, and its only
output is `Produced[MetricAggregate]` — there is no function anywhere in this module, or in the
public surface it exports, that hands back a bare `float`. `MetricAggregate.mean` and
`MetricAggregate.stdev`/`.n` are fields on the same frozen model; a caller who wants the mean
receives the dispersion it was measured with in the same object, not a sibling value it could
forget to read — the identical move 4.1 made for `MetricScore`/`error` (`docs/build-ledger.md`
4.1: "there is no `float` field sitting beside an `error` string a caller could forget to check").

**Dispersion, the choice and why.** Sample standard deviation, alongside `n`. Not an interval:
`09` §4's own interval language belongs to V3 (a baseline's *repeat count* spans a range across
repeated *runs* of the same pipeline — task 4.8's concern, over runs, not samples). V4's dispersion
is over *samples within one run* — how spread out one metric's per-sample scores were — and
standard deviation is the textbook measure of spread for a set of real-valued observations: it
uses every observation, not just the two extremes a min/max range would keep, and it composes
with `n` the way a reader needs to judge how much to trust it (`n=2` and `n=200` at the identical
`stdev` are not equally trustworthy, and `n` travels on the same object). A single observation has
no real spread to report — `docs/build-ledger.md` 4.1 already states this ("a standard deviation
of one observation is not a real quantity, so this task carries none") for a single `MetricScore`;
the aggregate honours the identical rule at `n == 1`, where `stdev` is `None` rather than `0.0` —
`0.0` would silently claim measured, zero spread, which is a different, stronger and unearned
claim for one data point.

**The `k`-in-the-name check runs on the reported name, not the plugin's own property — R5.** The
reference's `PrecisionAtK`/`RecallAtK`/`NDCG` already build `metric_name` correctly from their own
`k` (`.phase4-reference-recon.md` §6: `retrieval/ir_metrics.py:29-30,91-92,230-231`). The defect was
one layer up: `open_rag_fast_track.py:359-364`/`open_rag_ultimate_track.py:514-519` hardcode the
literal report key `'precision_at_k'`/`'recall_at_k'` while the real `k` is a caller-supplied
`similarity_top_k` (`open_rag_fast_track.py:299-301`) — a check against `PrecisionAtK.metric_name`
in isolation would have passed on that exact tree, because that property was never wrong.
`aggregate()` does not accept a caller-supplied name at all — `MetricAggregate.reported_name` is
read off the observations' own `MetricScore.metric_name`, so there is no literal to get stale.
`aggregate_report()` goes one step further, for the shape a run report actually has (many metrics,
each under its own key): it takes the key the caller is *about to publish* an aggregate under and
refuses, via `ReportedNameMismatchError`, the moment that key disagrees with what the metric
itself computed — precisely the shape that would catch the reference's report keyed `'precision_at_k'`
sitting beside a metric that actually computed `'precision@7'`.
"""

import statistics
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from weft_eval.contract import MetricScore
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced


class MismatchedMetricNameError(WeftError):
    """Two `Produced` observations passed to one `aggregate()` call disagree about their own name.

    Not a name-*resolution* failure — there is no alternative name to offer, only a fact that two
    observations describe two different computations (say, `k=3` and `k=7` of the same registered
    plugin) and were handed to the same aggregate by mistake. `tests/architecture/test_ff12_
    unresolvable_name_carries_options.py`'s own module docstring draws this line explicitly: "a
    class reporting a collision, a malformed shape, or a type mismatch is a different failure mode
    this function does not reach" — this is that different failure mode, so it carries no
    `valid_options` and is not a member of `NAME_RESOLUTION_FAMILY`.
    """

    def __init__(self, *, expected: str, found: str) -> None:
        super().__init__(
            f"cannot aggregate: one observation reports metric_name={found!r}, but an earlier "
            f"observation in the same aggregate reported {expected!r} — every `Produced` "
            "observation folded into one aggregate must report the identical name the metric "
            "itself computed; mixing two configurations (e.g. two different `k`) into one "
            "aggregate is a caller error, not something to average over"
        )
        self.expected = expected
        self.found = found


class ReportedNameMismatchError(WeftError):
    """A report's key for a metric's aggregate does not match the name that metric computed.

    This is R5's exact defect (`.phase4-reference-recon.md` §6): `open_rag_fast_track.py` published
    its retrieval aggregates under the literal report key `'precision_at_k'` while the metric it
    ran actually computed `f'precision@{k}'` for a caller-supplied `k` — the key and the
    computation silently diverged the moment `k` was anything but the value baked into the
    literal, and nothing in that tree noticed. `aggregate_report()` raises this the moment a
    caller's chosen key and the metric's own computed name disagree, rather than letting a stale
    or hand-typed key stand next to a computation it no longer describes.
    """

    def __init__(self, *, report_key: str, computed_name: str) -> None:
        super().__init__(
            f"report key {report_key!r} does not match the name this metric computed, "
            f"{computed_name!r} — a report's key must be the name the metric itself reports "
            "for what it measured, never a caller-chosen label maintained by hand"
        )
        self.report_key = report_key
        self.computed_name = computed_name


class MetricAggregate(BaseModel):
    """One metric's aggregate result over many observations — mean, `n` and `stdev` travel together.

    `reported_name` is never caller-supplied: it is read off the observations' own `MetricScore.
    metric_name`, the name the metric computed from its own configuration. `excluded` counts the
    `Failed` observations this aggregate excluded from `mean`; `nothing_to_produce` counts the
    `NothingToProduce` observations, kept distinct from `excluded` because an absence and an error
    are not the same claim — conflating them is exactly what the reference's zero-vs-error accident
    did one level down, at the per-sample result (`docs/build-ledger.md` 4.1).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reported_name: str
    mean: float
    #: How many observations `mean`/`stdev` were computed from. Always at least 1 — with zero
    #: scored observations there is nothing to average, and `aggregate()` returns `Failed` or
    #: `NothingToProduce` instead of a `MetricAggregate` with no observations behind it.
    n: int = Field(ge=1)
    #: Sample standard deviation across the `n` scored observations. `None` only when `n == 1`,
    #: where a standard deviation is not a real quantity — never `0.0`, which would claim a
    #: measured, zero spread that one observation cannot support.
    stdev: float | None
    #: How many `Failed` observations this aggregate excluded from `mean`/`stdev` — V4's own
    #: requirement, stated as a count a reader can see, not a fact left to be reconstructed by
    #: subtracting a success count from a total the way the reference's one error-aware aggregator did.
    excluded: int = Field(ge=0)
    #: How many `NothingToProduce` observations this aggregate excluded — a legitimate absence,
    #: counted separately from `excluded` because it is not an error.
    nothing_to_produce: int = Field(ge=0)


def aggregate(outcomes: Sequence[Outcome[MetricScore]]) -> Outcome[MetricAggregate]:
    """Fold many observations of *one* metric into `Produced[MetricAggregate]`, or say why not.

    `Failed` observations are excluded from `mean`/`stdev` and counted in `excluded`.
    `NothingToProduce` observations are excluded and counted in `nothing_to_produce`, kept apart
    from `excluded` because a legitimate absence is not an error. If every observation is excluded
    — including the empty-sequence case — there is no mean to report: this returns `Failed` when
    at least one observation actually failed, `NothingToProduce` when every observation had
    nothing to score and none failed, and `Failed` for the empty sequence, on the same reasoning
    `weft_eval.contract`'s own module docstring gives for treating "nothing to compare against" as
    a legitimate but distinct outcome from a genuine failure.

    Raises `MismatchedMetricNameError` if two `Produced` observations report different
    `metric_name`s — mixing two metric configurations into one aggregate is a caller error this
    function refuses rather than silently averaging together.
    """
    scored: list[float] = []
    reported_name: str | None = None
    excluded = 0
    nothing_to_produce = 0

    for outcome in outcomes:
        match outcome:
            case Produced(value=score):
                if reported_name is None:
                    reported_name = score.metric_name
                elif score.metric_name != reported_name:
                    raise MismatchedMetricNameError(expected=reported_name, found=score.metric_name)
                scored.append(score.value)
            case Failed():
                excluded += 1
            case NothingToProduce():
                nothing_to_produce += 1

    if reported_name is None:
        if excluded:
            return Failed(
                reason=(
                    f"all {excluded + nothing_to_produce} observation(s) excluded "
                    f"({excluded} failed, {nothing_to_produce} had nothing to score); "
                    "nothing to aggregate"
                )
            )
        if nothing_to_produce:
            return NothingToProduce(
                reason=f"all {nothing_to_produce} observation(s) had nothing to score"
            )
        return Failed(reason="no observations to aggregate")

    mean = statistics.fmean(scored)
    stdev = statistics.stdev(scored) if len(scored) >= 2 else None
    return Produced(
        value=MetricAggregate(
            reported_name=reported_name,
            mean=mean,
            n=len(scored),
            stdev=stdev,
            excluded=excluded,
            nothing_to_produce=nothing_to_produce,
        )
    )


def aggregate_report(
    groups: Mapping[str, Sequence[Outcome[MetricScore]]],
) -> Mapping[str, Outcome[MetricAggregate]]:
    """Aggregate several metrics' observations into the report a human actually reads.

    Each key in `groups` is the label the caller is about to publish that metric's aggregate
    under — a run record's field name, a CLI table row, a comparison column. This function does
    not trust that label: whenever a group produces a score, the resulting `MetricAggregate.
    reported_name` — read off the data, per `aggregate()` — is compared against the caller's own
    key, and a disagreement raises `ReportedNameMismatchError` rather than publishing a key that no
    longer describes what was actually computed. This is the check R5 asks for: run on the name
    that ends up in the report, not only on a metric's own `metric_name` property in isolation,
    which the reference already got right per-instance while its report keys drifted from it anyway.
    """
    report: dict[str, Outcome[MetricAggregate]] = {}
    for key, outcomes in groups.items():
        outcome = aggregate(outcomes)
        if isinstance(outcome, Produced) and outcome.value.reported_name != key:
            raise ReportedNameMismatchError(
                report_key=key, computed_name=outcome.value.reported_name
            )
        report[key] = outcome
    return report
