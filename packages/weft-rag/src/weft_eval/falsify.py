"""The falsification instrument: judging a difference between two runs.

The falsification instrument — ledger task **8.8**, `docs/09-release.md` §4.3 applied to a
*difference between two runs* rather than to a single value.

`09` §4.3 derives a reproduction tolerance without ever choosing a number: a baseline is
*repeated*, and the interval its own repetitions spanned per metric is that system's measured
variability — "a system that is deterministic records a zero-width interval and admits no drift
at all, which is correct and strict," and "the baseline was run once, in which case it records no
interval and no later run can be judged against it." This module applies the identical
derivation one step over: two persisted runs of two different pipelines each carry a mean per
metric, and their difference is what somebody claims as an improvement. The baseline pipeline,
run more than once against the same corpus, varied by some amount doing nothing at all — the
width of the interval its repetitions spanned. A difference no larger than that width is
indistinguishable from the baseline repeating itself, so it is not evidence of an improvement; a
difference larger than it is outside what the baseline's own noise produced.

**No threshold, no multiplier, no sigma, no tolerance constant lives here.** The only number ever
compared against a difference is `high - low` of the baseline's own repetition means —
`BaselineSpread.width`. `09` §4.4 forbids inventing a quality threshold; this module never reads
a config value, an environment variable or a literal fraction to widen or narrow that number.

**Three things are refused rather than answered**, because a plausible number would be worse than
a refusal: a baseline with fewer than two repetitions (`baseline_spreads` raises
`TooFewRepetitionsError`, V3's own failure clause, quoted above); a baseline that did not measure
a metric in *every* repetition (its interval would understate the baseline's own variability, so
no interval is taken for that metric at all — `NoSpread`, not a spread computed over whichever
repetitions happened to score); and a metric only one of the two compared runs scored (there is
no difference to judge, and the absent side is never treated as a zero). Each of those produces a
named `Verdict`/measurement carrying its own reason, never a silent omission and never a default
verdict.

`BaselineSpread`'s own validator mirrors `weft_eval.run_record`'s `MetricRunResult`-adjacent
style and `MetricAggregate`'s field-level `Field(ge=...)` guards: refusing at construction, so a
`BaselineSpread` that exists at all is already a fact a caller can trust, rather than a shape a
reader has to re-check by hand.

Registers nothing: folding a baseline's repetitions into a spread and judging a difference
against it are not capabilities any pack or third party needs to swap, the identical reasoning
`weft_eval.aggregate`/`weft_eval.run_record`'s own module docstrings already give for their own
unregistered functions.

Repair **R38.16**: `paired_differences`' own `PairedDifference` also states how many of its
paired questions actually differ, because `n` alone hides a mean carried by almost none of them.

Repair **R41.3**: `paired_differences` refuses two records whose pool manifests or question-set
digests disagree, `40.2`'s rule, rather than pairing them on question keys alone.

Task **44.9**, owner decision D7: `pooled_paired_differences` pools every repetition both a
baseline and an arm ran, pairing repetition *k* of one against repetition *k* of the other,
question by question. Two repetitions of the same question are not two independent
observations of it, so the bootstrap it runs resamples **question keys**, never the flat list
of (question, repetition) differences — a question asked twice must not narrow the interval
as if twice as many questions had been asked. With exactly one pair, it reads identically to
`paired_differences` on that pair, to the bit.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_eval.run_record import QuestionOutcome, RunRecord
from weft_kernel.errors import WeftError
from weft_kernel.payload import Produced

#: Ledger task 16.9. Enough resamples for a percentile interval to be stable to three
#: decimals — what `_render_eval_compare`'s own formatting prints — without the bootstrap
#: itself becoming the slow part of `weft eval compare`.
_RESAMPLES = 2000


class TooFewRepetitionsError(WeftError):
    """Stops any verdict from resting on a baseline measured only once.

    A baseline was handed fewer than 2 repetitions — V3's own failure clause: "the baseline
    was run once, in which case it records no interval and no later run can be judged against
    it." Refused where the spread would otherwise be built, so no caller downstream can ever
    reach a verdict computed from a single measurement.
    """

    def __init__(self, message: str, *, repetitions: int) -> None:
        super().__init__(message)
        self.repetitions = repetitions


class UnpairableRecordsError(WeftError):
    """Two records carry pool manifests or question-set digests that disagree — repair R41.3."""

    def __init__(self, message: str, *, reasons: tuple[str, ...]) -> None:
        super().__init__(message)
        self.reasons = reasons


class BaselineSpread(BaseModel):
    """The interval one metric's means spanned across a baseline's own repetitions.

    `low`/`high` are never a caller's own choice — the validator below refuses any value that is
    not exactly `min(means)`/`max(means)`, because a widened bound would be a chosen tolerance,
    which `09` §4.4 forbids and this whole module exists to not smuggle in.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = Field(min_length=1)
    #: One entry per baseline repetition that produced this metric, in the order those
    #: repetitions were given. At least 2 — see `_check_means`.
    means: tuple[float, ...]
    low: float
    high: float

    @property
    def width(self) -> float:
        """`high - low` — the only number this whole module ever compares a difference against."""
        return self.high - self.low

    @model_validator(mode="after")
    def _check_means(self) -> BaselineSpread:
        if len(self.means) < 2:
            raise ValueError(
                f"a baseline spread for '{self.metric}' needs at least 2 repetition means to "
                f"measure any variability at all; {len(self.means)} given — V3's own failure "
                "clause: 'the baseline was run once, in which case it records no interval and "
                "no later run can be judged against it.'"
            )
        if self.low != min(self.means) or self.high != max(self.means):
            raise ValueError(
                f"'{self.metric}' spread bounds must be exactly min/max of its own repetition "
                f"means ({min(self.means)!r}/{max(self.means)!r}), not {self.low!r}/"
                f"{self.high!r} — a widened bound would be a chosen tolerance, and '09' §4.4 "
                "forbids inventing one here."
            )
        return self


class NoSpread(BaseModel):
    """No interval could honestly be taken for this metric — `reason` says why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str


#: A closed, two-member union — the identical idiom `weft_eval.run_record.MetricRunResult`
#: already uses, unambiguous because `BaselineSpread` and `NoSpread` never share a field name.
type BaselineMeasurement = BaselineSpread | NoSpread


class Verdict(StrEnum):
    """What a difference between two rungs is, once judged against a baseline's own spread."""

    OUTSIDE_BASELINE_SPREAD = "outside-baseline-spread"
    WITHIN_BASELINE_SPREAD = "within-baseline-spread"
    UNJUDGEABLE = "unjudgeable"


class DifferenceJudgement(BaseModel):
    """Whether one metric's change beat the baseline's own noise, and why it was so judged.

    One metric's verdict — `reason` is always populated, for every verdict, never only for
    the refused ones.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    verdict: Verdict
    #: `b`'s mean minus `a`'s mean, signed. `None` only when `verdict` is `UNJUDGEABLE`.
    difference: float | None
    #: The baseline spread the difference was judged against. `None` only when `verdict` is
    #: `UNJUDGEABLE`.
    spread: BaselineSpread | None
    reason: str


def baseline_spreads(records: Sequence[RunRecord]) -> Mapping[str, BaselineMeasurement]:
    """Measure how much the baseline varies from itself, the bar a difference must clear.

    Every metric name any of `records` carries, folded into the interval its own means
    spanned — or `NoSpread`, naming why, for a metric that did not measure in every repetition.

    Raises `TooFewRepetitionsError` for fewer than 2 `records` — see that error's own docstring.
    """
    if len(records) < 2:
        raise TooFewRepetitionsError(
            f"a baseline needs at least 2 repetitions to measure its own variability; "
            f"{len(records)} given — V3's own failure clause: 'the baseline was run once, in "
            "which case it records no interval and no later run can be judged against it.'",
            repetitions=len(records),
        )

    names: set[str] = set()
    for record in records:
        names.update(record.metrics)

    result: dict[str, BaselineMeasurement] = {}
    for name in sorted(names):
        means: list[float] = []
        produced = 0
        for record in records:
            outcome = record.metrics.get(name)
            if isinstance(outcome, Produced):
                produced += 1
                means.append(outcome.value.mean)
        if produced == len(records):
            result[name] = BaselineSpread(
                metric=name, means=tuple(means), low=min(means), high=max(means)
            )
        else:
            result[name] = NoSpread(
                reason=(
                    f"'{name}' was produced by only {produced} of {len(records)} baseline "
                    "repetitions — an interval taken over the repetitions that happen to have "
                    "scored would understate the baseline's own variability, so no interval is "
                    "taken for this metric at all."
                )
            )
    return MappingProxyType(result)


def _unscored_sides(*, a_scored: bool, b_scored: bool) -> str:
    """Which side(s) of a compared pair did not score a metric — for a reason string."""
    sides: list[str] = []
    if not a_scored:
        sides.append("the first run")
    if not b_scored:
        sides.append("the second run")
    return " and ".join(sides)


def judge_differences(
    a: RunRecord, b: RunRecord, spreads: Mapping[str, BaselineMeasurement]
) -> Mapping[str, DifferenceJudgement]:
    """Judge whether each metric's difference between two runs exceeds the baseline spread.

    Judge, for every metric either `a` or `b` measured, whether their difference is
    distinguishable from the baseline's own spread — see the module docstring for the rule.

    A metric only the baseline measured (absent from both `a.metrics` and `b.metrics`) is not
    reported at all: there is nothing of `a`/`b`'s own to judge.
    """
    names = sorted(set(a.metrics) | set(b.metrics))
    result: dict[str, DifferenceJudgement] = {}
    for name in names:
        a_outcome = a.metrics.get(name)
        b_outcome = b.metrics.get(name)
        a_scored = isinstance(a_outcome, Produced)
        b_scored = isinstance(b_outcome, Produced)

        if not (a_scored and b_scored):
            unscored = _unscored_sides(a_scored=a_scored, b_scored=b_scored)
            result[name] = DifferenceJudgement(
                metric=name,
                verdict=Verdict.UNJUDGEABLE,
                difference=None,
                spread=None,
                reason=(
                    f"'{name}' was not scored by {unscored} — there "
                    "is no difference to judge, and the absent side is never treated as a zero."
                ),
            )
            continue

        measurement = spreads.get(name)
        if measurement is None:
            result[name] = DifferenceJudgement(
                metric=name,
                verdict=Verdict.UNJUDGEABLE,
                difference=None,
                spread=None,
                reason=(
                    f"the baseline never measured '{name}' — there is no interval to judge "
                    "this difference against."
                ),
            )
            continue

        if isinstance(measurement, NoSpread):
            result[name] = DifferenceJudgement(
                metric=name,
                verdict=Verdict.UNJUDGEABLE,
                difference=None,
                spread=None,
                reason=measurement.reason,
            )
            continue

        # Both `Produced` — `MetricAggregate.mean` is the value read from each side, per the
        # module docstring.
        difference: float = b_outcome.value.mean - a_outcome.value.mean
        width = measurement.width
        # Exactly equal to the width is WITHIN — the conservative reading: a difference has to
        # exceed what the baseline's own repetitions already produced to count as evidence.
        if abs(difference) > width:
            verdict = Verdict.OUTSIDE_BASELINE_SPREAD
            reason = (
                f"'{name}' difference {difference:+.4f} exceeds the baseline's own spread "
                f"width {width:.4f} ({measurement.low:.4f}-{measurement.high:.4f}) — larger "
                "than what the baseline produced by repeating itself."
            )
        else:
            verdict = Verdict.WITHIN_BASELINE_SPREAD
            reason = (
                f"'{name}' difference {difference:+.4f} is no larger than the baseline's own "
                f"spread width {width:.4f} ({measurement.low:.4f}-{measurement.high:.4f}) — "
                "indistinguishable from the baseline repeating itself."
            )
        result[name] = DifferenceJudgement(
            metric=name, verdict=verdict, difference=difference, spread=measurement, reason=reason
        )
    return MappingProxyType(result)


class PairedDifference(BaseModel):
    """`b` minus `a`, question by question — the second interval, over a different population.

    `BaselineSpread` above is the spread one rung produced by repeating itself, so it answers
    *is this difference bigger than this system's own noise*. This answers *does it hold across
    the questions*, and the two can disagree in both directions: a difference inside the
    baseline spread can be consistent across every question, and one far outside it can rest
    entirely on two.

    `low`/`high` are `None` for a single paired question, the identical rule `BaselineSpread`
    already states for a single repetition — one observation has no spread to report, and a
    zero-width interval reads as certainty.

    `differing` (repair R38.16) says how many of `n` actually moved, because `mean` and its
    interval can rest on a handful of questions while the rest agree exactly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    #: The mean of the per-question differences, `b` minus `a`, signed.
    mean: float
    #: The 2.5th and 97.5th percentiles of the bootstrap distribution of that mean.
    low: float | None
    high: float | None
    #: How many questions both records scored for this metric.
    n: int = Field(ge=1)
    #: How many of `n`'s own paired questions have a difference that is not exactly zero —
    #: repair R38.16: a mean and its interval can rest on a handful of questions while the rest
    #: agree exactly, and this is what tells a reader that apart from `n` alone.
    differing: int = Field(ge=0)


def pairing_reasons(a: RunRecord, b: RunRecord) -> tuple[str, ...]:
    """Why `a` and `b` cannot pair.

    A digest either side lacks, or two digests over different bases, is not a disagreement.
    """
    reasons: list[str] = []

    if (
        a.experiment is not None
        and b.experiment is not None
        and a.experiment.pool_manifest is not None
        and b.experiment.pool_manifest is not None
        and a.experiment.pool_manifest != b.experiment.pool_manifest
    ):
        reasons.append(
            f"pool manifest differs ({a.experiment.pool_manifest[:12]}… vs "
            f"{b.experiment.pool_manifest[:12]}…)"
        )

    if (
        a.question_set_digest_basis == b.question_set_digest_basis
        and a.question_set_digest is not None
        and b.question_set_digest is not None
        and a.question_set_digest != b.question_set_digest
    ):
        reasons.append(
            f"question set differs ({a.question_set_digest[:12]}… vs {b.question_set_digest[:12]}…)"
        )

    reasons.extend(_judge_prompt_reasons(a, b))
    return tuple(reasons)


def _judge_prompt_reasons(a: RunRecord, b: RunRecord) -> list[str]:
    """One reason per metric both records digested a judge prompt for, where the digests differ.

    A record without `judge_prompts` (written before 44.4), or one with no digest for a metric, is
    not a disagreement: only two digests over the same metric can be told apart.
    """
    if a.judge_prompts is None or b.judge_prompts is None:
        return []
    return [
        f"judge prompt for '{metric}' differs ({a.judge_prompts[metric][:12]}… vs "
        f"{b.judge_prompts[metric][:12]}…)"
        for metric in sorted(set(a.judge_prompts) & set(b.judge_prompts))
        if a.judge_prompts[metric] != b.judge_prompts[metric]
    ]


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    """The `pct`-th percentile of already sorted values, linearly interpolated.

    The `pct`-th percentile of `sorted_values`, already sorted, linearly interpolated
    between the two nearest ranks — the same interpolation `numpy.percentile`'s default uses,
    so the bootstrap interval this feeds is one a reader can cross-check.
    """
    index = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    fraction = index - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def paired_interval(
    keyed_diffs: Sequence[tuple[str, float]],
) -> tuple[float | None, float | None]:
    """The 95% bootstrap interval of the mean of `keyed_diffs`' differences.

    The 2.5th/97.5th percentile of the bootstrap distribution of the mean of `keyed_diffs`'
    own differences — `None`/`None` for a single observation, which has no spread to report.

    **The resampling indices are derived from the data by a hash, and there is no
    pseudo-random generator here at all.** Two readings of one pair of records have to give one
    interval — a verdict that changed between two readings of the same two files would be
    unciteable — and a seeded `random.Random` buys that only as long as CPython's Mersenne
    stream never changes, which is a promise about an implementation rather than about this
    function. A counter-mode digest over the data is reproducible by specification, needs no
    seed to be chosen, and is what `corpus_identity` and the question-set digest already do one
    artefact over. It also keeps this module free of `random`, which `ruff`'s `S311` refuses in
    shipped code (a pinned ratchet, `ignore = []`) — the refusal is about cryptographic
    suitability and does not apply here, but a waiver is a cost and this design does not need
    one.
    """
    if len(keyed_diffs) < 2:
        return None, None

    values = [diff for _, diff in keyed_diffs]
    n = len(values)
    seed_material = "|".join(f"{key}:{diff!r}" for key, diff in sorted(keyed_diffs))
    indices = _index_stream(seed_material, count=_RESAMPLES * n, modulus=n)

    means = sorted(
        sum(values[index] for index in indices[start : start + n]) / n
        for start in range(0, _RESAMPLES * n, n)
    )
    return _percentile(means, 2.5), _percentile(means, 97.5)


def _index_stream(seed_material: str, *, count: int, modulus: int) -> list[int]:
    """`count` indices uniform over `range(modulus)`, derived from `seed_material` alone.

    One `shake_256` stream per attempt, read as 8-byte big-endian integers, with rejection of any
    at or above the largest multiple of `modulus` below 2**64, so every kept index is exactly
    uniform. Repair R38.8: indices were once single bytes, so no index passed 255 whatever
    `modulus` was; hashing the seed once is what keeps 3,096,000 indices over 1,548 questions fast.
    """
    limit = (2**64 // modulus) * modulus
    indices: list[int] = []
    attempt = 0
    while len(indices) < count:
        needed = count - len(indices)
        stream = hashlib.shake_256(f"{seed_material}|{attempt}".encode()).digest(8 * needed)
        values = (int.from_bytes(stream[i : i + 8], "big") for i in range(0, len(stream), 8))
        indices.extend(value % modulus for value in values if value < limit)
        attempt += 1
    return indices[:count]


def _keyed_diffs(
    a_scores: Mapping[str, QuestionOutcome],
    b_scores: Mapping[str, QuestionOutcome],
    question_keys: frozenset[str] | None,
) -> list[tuple[str, float]]:
    """Each shared question's `b - a` difference, in key order, where both sides produced."""
    keys = set(a_scores) & set(b_scores)
    if question_keys is not None:
        keys &= question_keys
    keyed_diffs: list[tuple[str, float]] = []
    for key in sorted(keys):
        a_outcome = a_scores[key]
        b_outcome = b_scores[key]
        if isinstance(a_outcome, Produced) and isinstance(b_outcome, Produced):
            keyed_diffs.append((key, b_outcome.value - a_outcome.value))
    return keyed_diffs


def paired_differences(
    a: RunRecord, b: RunRecord, *, question_keys: frozenset[str] | None = None
) -> Mapping[str, PairedDifference]:
    """One `PairedDifference` per metric both records scored, keyed as `metrics` is.

    A record whose `question_scores` is `None` — every record written before task 16.4 —
    pairs nothing: there is no per-question observation to pair, so this returns an empty
    mapping rather than guessing at one. For each metric name present in both records'
    `question_scores`, only the question keys present in both are paired, and only where the
    outcome is `Produced` on **both** sides — `NotScored` is not a zero (`docs/09-release.md`
    :620, V4). A metric that pairs nothing produces no entry at all.

    `question_keys` — repair R38.1 — restricts the pairing to that set alone, on top of the
    "present in both" rule above: `None` (the default) is today's behaviour, pairing every
    question both records scored.

    Raises `UnpairableRecordsError` when the records' pool manifests or question-set digests
    disagree — repair R41.3.
    """
    _refuse_unpairable(a, b)

    if a.question_scores is None or b.question_scores is None:
        return MappingProxyType({})

    names = sorted(set(a.question_scores) & set(b.question_scores))
    result: dict[str, PairedDifference] = {}
    for name in names:
        keyed_diffs = _keyed_diffs(
            a.question_scores[name].scores, b.question_scores[name].scores, question_keys
        )
        if not keyed_diffs:
            continue
        mean = sum(diff for _, diff in keyed_diffs) / len(keyed_diffs)
        low, high = paired_interval(keyed_diffs)
        differing = sum(1 for _, diff in keyed_diffs if diff != 0.0)
        result[name] = PairedDifference(
            metric=name, mean=mean, low=low, high=high, n=len(keyed_diffs), differing=differing
        )
    return MappingProxyType(result)


def _refuse_unpairable(a: RunRecord, b: RunRecord) -> None:
    """Raise `UnpairableRecordsError` naming every reason `a` and `b` cannot pair."""
    reasons = pairing_reasons(a, b)
    if reasons:
        raise UnpairableRecordsError(
            f"these two records do not pair question by question: "
            f"{'; '.join(reasons)} — task 40.2: two arms compare only on the same pool "
            f"manifest and question-set digests",
            reasons=reasons,
        )


def _pooled_keyed_diffs(
    pairs: Sequence[tuple[RunRecord, RunRecord]], metric: str
) -> dict[str, list[float]]:
    """Every (repetition, question) difference for `metric`, grouped by question key."""
    by_key: dict[str, list[float]] = {}
    for a, b in pairs:
        if a.question_scores is None or b.question_scores is None:
            continue
        a_per = a.question_scores.get(metric)
        b_per = b.question_scores.get(metric)
        if a_per is None or b_per is None:
            continue
        for key, diff in _keyed_diffs(a_per.scores, b_per.scores, None):
            by_key.setdefault(key, []).append(diff)
    return by_key


def _pooled_interval(by_key: Mapping[str, list[float]]) -> tuple[float | None, float | None]:
    """The 95% bootstrap interval of the mean of `by_key`'s pooled differences.

    Resamples question keys, `paired_interval`'s own `_RESAMPLES`/`_index_stream`/`_percentile`
    unchanged — each resampled key contributes every repetition's difference it holds, so a
    key drawn twice counts its differences twice, and a key with two repetitions is still one
    draw. `None`/`None` for fewer than two distinct keys, `BaselineSpread`'s own rule for a
    single observation.
    """
    distinct_keys = sorted(by_key)
    n_keys = len(distinct_keys)
    if n_keys < 2:
        return None, None

    key_sums = [sum(by_key[key]) for key in distinct_keys]
    key_counts = [len(by_key[key]) for key in distinct_keys]
    seed_material = "|".join(
        f"{key}:{diff!r}"
        for key, diff in sorted((key, diff) for key in by_key for diff in by_key[key])
    )
    indices = _index_stream(seed_material, count=_RESAMPLES * n_keys, modulus=n_keys)

    means = sorted(
        # The unit resampled is the question, not the (question, repetition) pair — two
        # repetitions of one question are not two independent draws.
        sum(key_sums[index] for index in indices[start : start + n_keys])
        / sum(key_counts[index] for index in indices[start : start + n_keys])
        for start in range(0, _RESAMPLES * n_keys, n_keys)
    )
    return _percentile(means, 2.5), _percentile(means, 97.5)


def pooled_paired_differences(
    pairs: Sequence[tuple[RunRecord, RunRecord]],
) -> Mapping[str, PairedDifference]:
    """One `PairedDifference` per metric, pooled over every `(baseline, arm)` repetition pair.

    `pairs` is `(baseline record, arm record)` of one repetition each, in repetition order —
    repetition *k* of the arm is paired with repetition *k* of the baseline. For each metric
    both sides scored per question, in any pair, every pair's own question-by-question
    differences (the identical `Produced`-on-both-sides rule `_keyed_diffs`/`paired_differences`
    already apply — `NotScored` is never a zero) count toward `mean` and `n`; a metric with no
    differences in any pair produces no entry. `differing` counts every one of those
    (repetition, question) differences that is not exactly zero.

    `low`/`high` bootstrap over question keys rather than over the flat list of differences —
    see `_pooled_interval`. With exactly one pair, every value here is identical, to the bit, to
    `paired_differences(a, b)` on that pair: with one difference per question, the seed
    material, the resampling indices and every arithmetic step this function performs collapse
    to exactly the steps `paired_interval` performs.

    Raises `UnpairableRecordsError` for any pair whose two records cannot pair — see
    `pairing_reasons`, the identical refusal `paired_differences` itself raises.
    """
    for a, b in pairs:
        _refuse_unpairable(a, b)

    metrics: set[str] = set()
    for a, b in pairs:
        if a.question_scores is not None and b.question_scores is not None:
            metrics.update(set(a.question_scores) & set(b.question_scores))

    result: dict[str, PairedDifference] = {}
    for name in sorted(metrics):
        by_key = _pooled_keyed_diffs(pairs, name)
        if not by_key:
            continue
        all_diffs = [diff for key in sorted(by_key) for diff in by_key[key]]
        mean = sum(all_diffs) / len(all_diffs)
        differing = sum(1 for diff in all_diffs if diff != 0.0)
        low, high = _pooled_interval(by_key)
        result[name] = PairedDifference(
            metric=name, mean=mean, low=low, high=high, n=len(all_diffs), differing=differing
        )
    return MappingProxyType(result)


__all__ = [
    "BaselineMeasurement",
    "BaselineSpread",
    "DifferenceJudgement",
    "NoSpread",
    "PairedDifference",
    "TooFewRepetitionsError",
    "UnpairableRecordsError",
    "Verdict",
    "baseline_spreads",
    "judge_differences",
    "paired_differences",
    "paired_interval",
    "pairing_reasons",
    "pooled_paired_differences",
]
