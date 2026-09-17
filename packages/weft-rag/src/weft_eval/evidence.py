"""The evidence table — ledger task **38.1**: an experiment's whole claim, recomputed from its
own records rather than typed by hand.

Task 38.0 runs an experiment document's arms and repetitions and persists one `RunRecord` per
cell (`weft_eval.run_record.ExperimentRun`). This module is the other half: fold whichever
records one complete invocation of a given document wrote back into the two questions `09` §4.3
and its own extension already answer, per arm compared against the first (`Experiment.arms[0]`)
and per metric the document lists —

- **the paired difference over questions, with its bootstrap interval** (`weft_eval.falsify.
  paired_differences`) — does the difference generalise across the questions it was measured on;
- **the verdict against the baseline's own between-repetition spread** (`weft_eval.falsify.
  baseline_spreads`/`judge_differences`) — is it bigger than what the system does by repeating
  itself —

beside latency and tokens-per-query, so a reader is never handed one number without being told
which of those two very different claims it is answering. **Neither bootstrap nor percentile is
re-derived here**: this module is arithmetic over what `weft_eval.falsify`/`weft_eval.latency`
already compute, never a second implementation of either.

**A table is never typed, because a typed one has already gone eleven tasks and 1,801 tests
unnoticed once** (`docs/internal/lessons.md` `L5.32`) — the only way a published number can be
trusted is for the function that renders it to be the same function `tests/docs/
test_evidence_tables.py` reruns against the committed records, byte for byte.

**One invocation, chosen honestly.** `weft eval experiment` may be run more than once against an
identical document — a re-run to check reproducibility, a stale invocation left over from a
scoring change — so `evidence_table` never averages across invocations or guesses which one an
author meant: it takes a named one, or refuses when more than one is complete, or when none is.
Records are matched to *this* document by digest (`ExperimentRun.digest == Experiment.digest`),
never by name alone — two documents can share a name the way two corpora can share one, and a
name match would silently compare a table against records a later edit invalidated.

Registers nothing: turning an invocation's records into a table is not a capability any pack or
third party needs to swap, the identical reasoning `weft_eval.falsify`'s own module docstring
already gives for its own unregistered functions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from weft_eval.experiment import Experiment, ExperimentArm, load_experiment
from weft_eval.falsify import (
    DifferenceJudgement,
    PairedDifference,
    Verdict,
    baseline_spreads,
    judge_differences,
    paired_differences,
)
from weft_eval.latency import LatencySummary, nearest_rank
from weft_eval.run_record import ExperimentRun, RunRecord, load_run_record
from weft_kernel.errors import WeftError
from weft_kernel.payload import Produced

#: One record's `ExperimentRun`, kept beside it once narrowed away from `RunRecord.experiment`'s
#: own `| None` — every helper below takes this shape rather than re-narrowing it, since a fresh
#: `assert` at each call site is the one thing `ruff`'s `S101` refuses in shipped code (a pinned
#: ratchet, `ignore = []`): an `assert` is stripped under `-O` and is not a check there.
type _MatchedRecord = tuple[RunRecord, ExperimentRun]


class IncompleteExperimentError(WeftError):
    """The chosen invocation does not hold exactly one record for every `(arm, repetition)` this
    document names — see the module docstring's *"One invocation, chosen honestly"* paragraph.

    The message names every missing `arm`/repetition pair when one invocation was named, or was
    the only one on record; with no record of this document at all, it names the experiment and
    its digest's first 12 characters instead, since there is nothing to enumerate.
    """


class AmbiguousInvocationError(WeftError):
    """More than one invocation of this document is complete, and none was named — see the
    module docstring's *"One invocation, chosen honestly"* paragraph. The message lists every
    complete invocation's id, so an author can pass `--invocation` and re-run.
    """


class ArmComparison(BaseModel):
    """One arm, one metric — its repetition-1 means, the paired difference over questions and
    its bootstrap interval, and the verdict against the baseline's own between-repetition
    spread. See the module docstring for what each of the two intervals actually asks.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: str
    metric: str
    baseline_mean: float | None
    arm_mean: float | None
    paired: PairedDifference | None
    judgement: DifferenceJudgement
    #: `True` exactly when `judgement.spread` is a `BaselineSpread` whose `width` is `0.0` —
    #: repair R38.10. Carried on the row rather than recomputed by the renderer, the same
    #: reason `judgement` itself is carried rather than re-derived: one place computes the
    #: fact, and `_comparison_row`/the header block only read it.
    zero_width_spread: bool


class ArmCost(BaseModel):
    """One arm's latency and tokens-per-query, folded across every repetition it ran."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: str
    latency: LatencySummary
    tokens_per_query: Mapping[str, float]


class EvidenceTable(BaseModel):
    """One experiment document's whole claim, over one complete invocation of it — see the
    module docstring. `render_evidence_table` is this table's only reader that matters: the
    committed markdown is this model rendered, and nothing renders it by hand.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    digest: str
    invocation: str
    minimum_detectable_effect: float
    baseline_arm: str
    repeats: int
    comparisons: tuple[ArmComparison, ...]
    costs: tuple[ArmCost, ...]


def _missing_pairs(experiment: Experiment, matched: Sequence[_MatchedRecord]) -> list[str]:
    """Every `(arm, repetition)` this document names that `matched` does not hold exactly once,
    in document order — an empty `matched` names every pair, which is exactly right for an
    invocation with no records at all.
    """
    counts: dict[tuple[str, int], int] = {}
    for _, run in matched:
        key = (run.arm, run.repetition)
        counts[key] = counts.get(key, 0) + 1
    missing: list[str] = []
    for arm in experiment.arms:
        for repetition in range(1, experiment.repeats + 1):
            if counts.get((arm.name, repetition), 0) != 1:
                missing.append(f"arm '{arm.name}' repetition {repetition}")
    return missing


def _incomplete_message(experiment: Experiment, invocation: str, missing: Sequence[str]) -> str:
    return (
        f"invocation '{invocation}' of experiment '{experiment.name}' "
        f"({experiment.digest[:12]}…) is missing " + "; ".join(missing) + "."
    )


def _by_key(matched: Sequence[_MatchedRecord]) -> dict[tuple[str, int], RunRecord]:
    return {(run.arm, run.repetition): record for record, run in matched}


def _choose_invocation(
    experiment: Experiment, matching: Sequence[_MatchedRecord], *, invocation: str | None
) -> tuple[str, dict[tuple[str, int], RunRecord]]:
    by_invocation: dict[str, list[_MatchedRecord]] = {}
    for record, run in matching:
        by_invocation.setdefault(run.invocation, []).append((record, run))

    if invocation is not None:
        chosen = by_invocation.get(invocation, [])
        missing = _missing_pairs(experiment, chosen)
        if missing:
            raise IncompleteExperimentError(_incomplete_message(experiment, invocation, missing))
        return invocation, _by_key(chosen)

    complete = sorted(
        inv for inv, matched in by_invocation.items() if not _missing_pairs(experiment, matched)
    )
    if len(complete) == 1:
        return complete[0], _by_key(by_invocation[complete[0]])
    if len(complete) > 1:
        raise AmbiguousInvocationError(
            f"more than one complete invocation of experiment '{experiment.name}' "
            f"({experiment.digest[:12]}…) exists: {', '.join(f'{c!r}' for c in complete)} — "
            "name one with --invocation."
        )
    if not by_invocation:
        raise IncompleteExperimentError(
            f"no records of experiment '{experiment.name}' ({experiment.digest[:12]}…) were found."
        )
    if len(by_invocation) == 1:
        ((only_invocation, only_matched),) = by_invocation.items()
        missing = _missing_pairs(experiment, only_matched)
        raise IncompleteExperimentError(_incomplete_message(experiment, only_invocation, missing))
    raise IncompleteExperimentError(
        " ".join(
            _incomplete_message(experiment, inv, _missing_pairs(experiment, matched))
            for inv, matched in sorted(by_invocation.items())
        )
    )


def _arm_records(
    experiment: Experiment, by_key: Mapping[tuple[str, int], RunRecord], arm: ExperimentArm
) -> list[RunRecord]:
    return [by_key[(arm.name, repetition)] for repetition in range(1, experiment.repeats + 1)]


def _metric_mean(record: RunRecord, metric: str) -> float | None:
    outcome = record.metrics.get(metric)
    return outcome.value.mean if isinstance(outcome, Produced) else None


def _unjudged(baseline_arm: ExperimentArm, arm: ExperimentArm, metric: str) -> DifferenceJudgement:
    return DifferenceJudgement(
        metric=metric,
        verdict=Verdict.UNJUDGEABLE,
        difference=None,
        spread=None,
        reason=(
            f"neither '{baseline_arm.name}' nor '{arm.name}' measured '{metric}' in repetition "
            "1 — there is nothing to judge for this metric."
        ),
    )


def _build_comparisons(
    experiment: Experiment,
    baseline_arm: ExperimentArm,
    baseline_records: Sequence[RunRecord],
    by_key: Mapping[tuple[str, int], RunRecord],
) -> list[ArmComparison]:
    spreads = baseline_spreads(baseline_records)
    baseline_first = baseline_records[0]
    comparisons: list[ArmComparison] = []
    for arm in experiment.arms[1:]:
        arm_first = _arm_records(experiment, by_key, arm)[0]
        paired_map = paired_differences(baseline_first, arm_first)
        judgement_map = judge_differences(baseline_first, arm_first, spreads)
        for metric in experiment.metrics:
            judgement = judgement_map.get(metric)
            if judgement is None:
                judgement = _unjudged(baseline_arm, arm, metric)
            comparisons.append(
                ArmComparison(
                    arm=arm.name,
                    metric=metric,
                    baseline_mean=_metric_mean(baseline_first, metric),
                    arm_mean=_metric_mean(arm_first, metric),
                    paired=paired_map.get(metric),
                    judgement=judgement,
                    zero_width_spread=(
                        judgement.spread is not None and judgement.spread.width == 0.0
                    ),
                )
            )
    return comparisons


def _tokens_per_query(
    experiment: Experiment, arm_records: Sequence[RunRecord], question_count: int
) -> dict[str, float]:
    roles: set[str] = set()
    for record in arm_records:
        if record.token_usage is not None:
            roles.update(record.token_usage)
    denominator = experiment.repeats * question_count
    tokens_per_query: dict[str, float] = {}
    if not denominator:
        return tokens_per_query
    for role in sorted(roles):
        total = 0
        for record in arm_records:
            if record.token_usage is not None and role in record.token_usage:
                role_tokens = record.token_usage[role]
                total += role_tokens.prompt_tokens + role_tokens.completion_tokens
        tokens_per_query[role] = total / denominator
    return tokens_per_query


def _question_count(record: RunRecord) -> int:
    """How many questions `record` asked: every id any metric scored or the run timed. `0` means
    the record says nothing about its questions, and tokens per query is then left unstated."""
    ids: set[str] = set()
    for per_metric in (record.question_scores or {}).values():
        ids.update(per_metric.scores)
    if record.question_seconds is not None:
        ids.update(record.question_seconds.seconds)
    return len(ids)


def _arm_cost(
    experiment: Experiment,
    by_key: Mapping[tuple[str, int], RunRecord],
    arm: ExperimentArm,
) -> ArmCost:
    arm_records = _arm_records(experiment, by_key, arm)
    seconds: list[float] = []
    for record in arm_records:
        if record.question_seconds is not None:
            seconds.extend(record.question_seconds.seconds.values())
    latency = LatencySummary(
        samples=len(seconds),
        p50=nearest_rank(seconds, 0.5),
        p95=nearest_rank(seconds, 0.95),
        p99=nearest_rank(seconds, 0.99),
    )
    tokens_per_query = _tokens_per_query(experiment, arm_records, _question_count(arm_records[0]))
    return ArmCost(arm=arm.name, latency=latency, tokens_per_query=tokens_per_query)


def _build_costs(
    experiment: Experiment, by_key: Mapping[tuple[str, int], RunRecord]
) -> list[ArmCost]:
    return [_arm_cost(experiment, by_key, arm) for arm in experiment.arms]


def evidence_table(
    experiment: Experiment, records: Sequence[RunRecord], *, invocation: str | None = None
) -> EvidenceTable:
    """`records` folded into one `EvidenceTable` for `experiment` — see the module docstring.

    Raises `IncompleteExperimentError`/`AmbiguousInvocationError` — see each error's own
    docstring for exactly when.
    """
    matching: list[_MatchedRecord] = []
    for record in records:
        run = record.experiment
        if run is not None and run.digest == experiment.digest:
            matching.append((record, run))

    chosen_invocation, by_key = _choose_invocation(experiment, matching, invocation=invocation)

    baseline_arm = experiment.arms[0]
    baseline_records = _arm_records(experiment, by_key, baseline_arm)

    return EvidenceTable(
        name=experiment.name,
        digest=experiment.digest,
        invocation=chosen_invocation,
        minimum_detectable_effect=experiment.minimum_detectable_effect,
        baseline_arm=baseline_arm.name,
        repeats=experiment.repeats,
        comparisons=tuple(_build_comparisons(experiment, baseline_arm, baseline_records, by_key)),
        costs=tuple(_build_costs(experiment, by_key)),
    )


def render_evidence_table(table: EvidenceTable) -> str:
    """`table`, rendered as deterministic markdown — see the module docstring for why nothing
    here is ever typed by hand instead. Ends in exactly one `\\n`.
    """
    lines = [
        f"# Evidence — {table.name}",
        "",
        f"experiment digest: {table.digest[:12]}… · invocation: {table.invocation} · "
        f"repetitions: {table.repeats}",
        f"minimum detectable effect: {table.minimum_detectable_effect:g}",
        f"paired Δ and its interval: arm minus '{table.baseline_arm}' on repetition 1, 95% "
        "bootstrap interval over questions",
        "spread verdict: that Δ against the between-repetition spread of arm "
        f"'{table.baseline_arm}'",
        "the minimum detectable effect is not applied to either verdict above: the paired "
        "difference's bootstrap interval and the spread verdict each read only the record's "
        "own numbers, never a chosen threshold.",
    ]
    if any(comparison.zero_width_spread for comparison in table.comparisons):
        lines.append(
            "at least one spread verdict below was judged against a zero-width baseline "
            "spread: these repetitions did not vary at all, which is a claim about them, not "
            "proof the system is deterministic."
        )
    lines.extend(
        [
            "",
            f"| arm | metric | {table.baseline_arm} | arm | paired Δ | 95% CI | n | "
            "spread verdict |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for comparison in table.comparisons:
        lines.append(_comparison_row(comparison))
    lines.extend(
        [
            "",
            "| arm | latency p50 (s) | latency p95 (s) | tokens per query |",
            "|---|---|---|---|",
        ]
    )
    for cost in table.costs:
        lines.append(_cost_row(cost))
    return "\n".join(lines) + "\n"


def _comparison_row(comparison: ArmComparison) -> str:
    baseline_mean = (
        f"{comparison.baseline_mean:.3f}" if comparison.baseline_mean is not None else "—"
    )
    arm_mean = f"{comparison.arm_mean:.3f}" if comparison.arm_mean is not None else "—"
    if comparison.paired is not None:
        paired_mean = f"{comparison.paired.mean:+.3f}"
        n = str(comparison.paired.n)
        if comparison.paired.low is not None and comparison.paired.high is not None:
            ci = f"{comparison.paired.low:+.3f} to {comparison.paired.high:+.3f}"
        else:
            ci = "—"
    else:
        paired_mean = "—"
        ci = "—"
        n = "—"
    verdict = comparison.judgement.verdict.value
    if comparison.zero_width_spread:
        verdict = f"{verdict} (zero-width)"
    return (
        f"| {comparison.arm} | {comparison.metric} | {baseline_mean} | {arm_mean} | "
        f"{paired_mean} | {ci} | {n} | {verdict} |"
    )


def _cost_row(cost: ArmCost) -> str:
    p50 = (
        f"{cost.latency.p50.value:.3f}"
        if isinstance(cost.latency.p50, Produced)
        else "not aggregated"
    )
    p95 = (
        f"{cost.latency.p95.value:.3f}"
        if isinstance(cost.latency.p95, Produced)
        else "not aggregated"
    )
    tokens = (
        ", ".join(f"{role}: {value:.1f}" for role, value in sorted(cost.tokens_per_query.items()))
        or "—"
    )
    return f"| {cost.arm} | {p50} | {p95} | {tokens} |"


def regenerate(experiment_path: Path, runs: Path) -> str:
    """`render_evidence_table(evidence_table(...))` over `experiment_path`'s own document and
    every `*.json` record under `runs`, sorted by filename — a missing `runs` directory is no
    records at all, not a refusal, since `evidence_table` already says clearly why it cannot
    build a table from none.
    """
    experiment = load_experiment(experiment_path)
    records = (
        [load_run_record(path) for path in sorted(runs.glob("*.json"))] if runs.is_dir() else []
    )
    return render_evidence_table(evidence_table(experiment, records))


__all__ = [
    "AmbiguousInvocationError",
    "ArmComparison",
    "ArmCost",
    "EvidenceTable",
    "IncompleteExperimentError",
    "evidence_table",
    "regenerate",
    "render_evidence_table",
]
