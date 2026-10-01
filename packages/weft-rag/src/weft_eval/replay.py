"""Offline replay: what any per-question choice among an experiment's arms would have scored.

Ledger task **44.6a**. Every arm of one experiment answers the same questions, and each
`RunRecord` keeps one score per question (`question_scores[metric].scores`, `Produced[float] |
NotScored`), so what a per-question choice among the arms would have scored is arithmetic over
those recorded scores, with **no model call**:

- `always <arm>` — that arm's own repetition-1 per-question scores, exactly.
- `oracle` — each question's best score among the arms that *scored* it. A `NotScored` or absent
  question is never a zero; an arm that did not score a question is simply not a candidate for it.
  The ceiling a router over these arms could reach.
- `self-oracle` — each question's better score between the best arm's repetition 1 and repetition
  2, when it ran one. What judge noise alone lets an oracle reach, and what an arm oracle is read
  against.

Each row is paired against the best arm's own repetition-1 scores, question by question, with the
bootstrap interval `weft_eval.falsify.paired_interval` already computes — never a second bootstrap
implementation.

Not a routing *policy* replayed — that is task 44.6 proper, once 44.7's `decide()` exists — nor
pooled repetitions (44.9) or verdicts (44.8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from weft_eval.evidence import select_invocation
from weft_eval.experiment import Direction, Experiment, ExperimentArm
from weft_eval.falsify import (
    PairedDifference,
    UnpairableRecordsError,
    paired_interval,
    pairing_reasons,
)
from weft_eval.run_record import RunRecord
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Produced


class UnscoredMetricError(WeftError, UnresolvedNameError):
    """No arm's repetition-1 record scored `metric` on any question of the chosen invocation.

    FF12's family: `valid_options` names every metric at least one repetition-1 record scored at
    least one question of — a metric whose every question is `NotScored` is not offered as an
    alternative.
    """

    def __init__(self, message: str, *, metric: str, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.metric = metric
        self.valid_options = valid_options


class ReplayRow(BaseModel):
    """One choice among the arms — a fixed arm, the oracle, or the self-oracle — and its Δ.

    `mean`/`n` are over the choice's own scored questions. `delta` pairs the choice against the
    best arm's repetition-1 scores, question by question; `None` when the two share no scored
    question.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    mean: float
    n: int = Field(ge=1)
    delta: PairedDifference | None


class ReplayTable(BaseModel):
    """Every arm, the oracle and the self-oracle, each paired against the best arm — task 44.6a."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment: str
    invocation: str
    metric: str
    best_arm: str
    rows: tuple[ReplayRow, ...]
    unscored: int = Field(ge=0)


def _produced_scores(record: RunRecord, metric: str) -> dict[str, float]:
    """`record`'s `Produced` per-question scores for `metric` — `{}` when it scored none."""
    per_question = (record.question_scores or {}).get(metric)
    if per_question is None:
        return {}
    return {
        key: outcome.value
        for key, outcome in per_question.scores.items()
        if isinstance(outcome, Produced)
    }


def _all_question_keys(record: RunRecord, metric: str) -> frozenset[str]:
    """Every question `metric` was asked of `record`, scored or not."""
    per_question = (record.question_scores or {}).get(metric)
    return frozenset(per_question.scores) if per_question is not None else frozenset()


def _pairing_check(records_by_arm: Mapping[str, RunRecord], arms: Sequence[ExperimentArm]) -> None:
    """Refuse arms whose repetition-1 records do not pair — `falsify`'s reasons plus corpus."""
    first = records_by_arm[arms[0].name]
    reasons: list[str] = []
    for arm in arms[1:]:
        other = records_by_arm[arm.name]
        reasons.extend(pairing_reasons(first, other))
        if first.corpus.digest != other.corpus.digest:
            reasons.append(
                f"corpus differs ({first.corpus.digest[:12]}… vs {other.corpus.digest[:12]}…)"
            )
    if reasons:
        raise UnpairableRecordsError(
            f"these arms do not pair question by question: {'; '.join(reasons)} — a replay "
            "chooses among arms that answered the same questions of the same corpus",
            reasons=tuple(reasons),
        )


def _valid_metrics(records_by_arm: Mapping[str, RunRecord]) -> tuple[str, ...]:
    """Every metric name at least one repetition-1 record scored at least one question of."""
    names: set[str] = set()
    for record in records_by_arm.values():
        for name, per_question in (record.question_scores or {}).items():
            if any(isinstance(outcome, Produced) for outcome in per_question.scores.values()):
                names.add(name)
    return tuple(sorted(names))


def _unscored_metric_message(
    experiment: Experiment, metric: str, invocation: str, valid_options: tuple[str, ...]
) -> str:
    tail = (
        f"scored per question: {', '.join(repr(name) for name in valid_options)}."
        if valid_options
        else "no metric was scored per question in these records."
    )
    return (
        f"no arm of experiment '{experiment.name}' scored '{metric}' on any question in "
        f"invocation '{invocation}'; {tail}"
    )


def _delta(
    metric: str, scores: Mapping[str, float], best_scores: Mapping[str, float]
) -> PairedDifference | None:
    """`scores` minus `best_scores`, question by question, over the questions both scored."""
    shared = sorted(set(scores) & set(best_scores))
    if not shared:
        return None
    diffs = [(key, scores[key] - best_scores[key]) for key in shared]
    mean = sum(diff for _, diff in diffs) / len(diffs)
    low, high = paired_interval(diffs)
    differing = sum(1 for _, diff in diffs if diff != 0.0)
    return PairedDifference(
        metric=metric, mean=mean, low=low, high=high, n=len(diffs), differing=differing
    )


def _row(
    label: str, scores: Mapping[str, float], metric: str, best_scores: Mapping[str, float]
) -> ReplayRow:
    mean = sum(scores.values()) / len(scores)
    return ReplayRow(
        label=label, mean=mean, n=len(scores), delta=_delta(metric, scores, best_scores)
    )


def _oracle_scores(
    produced_by_arm: Mapping[str, Mapping[str, float]], *, lower_is_better: bool
) -> dict[str, float]:
    """Each question's best score among the arms that scored it."""
    best = min if lower_is_better else max
    keys: set[str] = set()
    for scores in produced_by_arm.values():
        keys.update(scores)
    return {
        key: best(scores[key] for scores in produced_by_arm.values() if key in scores)
        for key in keys
    }


def _self_oracle_scores(
    rep1: Mapping[str, float], rep2: Mapping[str, float], *, lower_is_better: bool
) -> dict[str, float]:
    """Each question's better score between the best arm's repetition 1 and repetition 2."""
    best = min if lower_is_better else max
    result: dict[str, float] = {}
    for key in set(rep1) | set(rep2):
        candidates = [scores[key] for scores in (rep1, rep2) if key in scores]
        result[key] = best(candidates)
    return result


def _arm_rows(
    experiment: Experiment,
    produced_by_arm: Mapping[str, Mapping[str, float]],
    metric: str,
    best_scores: Mapping[str, float],
) -> list[ReplayRow]:
    return [
        _row(f"always {arm.name}", produced_by_arm[arm.name], metric, best_scores)
        for arm in experiment.arms
        if arm.name in produced_by_arm
    ]


def _lower_is_better(experiment: Experiment, metric: str) -> bool:
    """Whether the experiment's own decision on `metric` says a lower score is better (R44.19)."""
    decision = experiment.decision
    return (
        decision is not None
        and decision.metric == metric
        and decision.direction is Direction.LOWER_IS_BETTER
    )


def replay(
    experiment: Experiment,
    records: Sequence[RunRecord],
    *,
    metric: str,
    invocation: str | None = None,
) -> ReplayTable:
    """Compute what any per-question choice among `experiment`'s arms would have scored.

    See the module docstring. Raises `weft_eval.evidence.IncompleteExperimentError`/
    `AmbiguousInvocationError` exactly as `select_invocation` does, `UnpairableRecordsError`
    when the chosen invocation's arms did not answer the same questions of the same corpus, and
    `UnscoredMetricError` when no arm scored `metric` on any question.
    """
    chosen_invocation, by_key = select_invocation(experiment, records, invocation=invocation)
    records_by_arm = {arm.name: by_key[(arm.name, 1)] for arm in experiment.arms}

    _pairing_check(records_by_arm, experiment.arms)

    produced_by_arm: dict[str, dict[str, float]] = {}
    for arm in experiment.arms:
        scores = _produced_scores(records_by_arm[arm.name], metric)
        if scores:
            produced_by_arm[arm.name] = scores

    if not produced_by_arm:
        valid_options = _valid_metrics(records_by_arm)
        raise UnscoredMetricError(
            _unscored_metric_message(experiment, metric, chosen_invocation, valid_options),
            metric=metric,
            valid_options=valid_options,
        )

    lower = _lower_is_better(experiment, metric)
    best_arm_name = sorted(
        produced_by_arm,
        key=lambda name: sum(produced_by_arm[name].values()) / len(produced_by_arm[name]),
        reverse=not lower,
    )[0]
    best_scores = produced_by_arm[best_arm_name]

    rows = _arm_rows(experiment, produced_by_arm, metric, best_scores)
    rows.append(
        _row("oracle", _oracle_scores(produced_by_arm, lower_is_better=lower), metric, best_scores)
    )

    best_arm = next(arm for arm in experiment.arms if arm.name == best_arm_name)
    if experiment.repeats_for(best_arm) >= 2:
        rep2_scores = _produced_scores(by_key[(best_arm_name, 2)], metric)
        self_oracle_scores = _self_oracle_scores(best_scores, rep2_scores, lower_is_better=lower)
        if self_oracle_scores:
            rows.append(_row("self-oracle", self_oracle_scores, metric, best_scores))

    all_keys: set[str] = set()
    for arm in experiment.arms:
        all_keys.update(_all_question_keys(records_by_arm[arm.name], metric))
    scored_keys: set[str] = set()
    for scores in produced_by_arm.values():
        scored_keys.update(scores)

    return ReplayTable(
        experiment=experiment.name,
        invocation=chosen_invocation,
        metric=metric,
        best_arm=best_arm_name,
        rows=tuple(rows),
        unscored=len(all_keys - scored_keys),
    )


def _ci_cell(row: ReplayRow) -> str:
    if row.delta is None or row.delta.low is None or row.delta.high is None:
        return "—"
    return f"{row.delta.low:+.3f} to {row.delta.high:+.3f}"


def _render_row(row: ReplayRow) -> str:
    delta_cell = f"{row.delta.mean:+.3f}" if row.delta is not None else "—"
    return f"| {row.label} | {row.mean:.3f} | {row.n} | {_ci_cell(row)} | {delta_cell} |"


def render_replay_table(table: ReplayTable) -> str:
    r"""Render `table` as deterministic markdown. Ends in exactly one `\n`."""
    lines = [
        f"# Replay — {table.experiment}",
        "",
        f"invocation: {table.invocation} · metric: {table.metric} · best arm: "
        f"{table.best_arm} · unscored: {table.unscored}",
        "each row chooses per question among the arms, from repetition 1's recorded scores; "
        "no model is called",
        "oracle: each question's best arm — the ceiling a router over these arms could reach",
    ]
    if any(row.label == "self-oracle" for row in table.rows):
        lines.append(
            f"self-oracle: each question's better repetition of '{table.best_arm}' — what "
            "judge noise alone reaches"
        )
    lines.append(
        f"interval and paired Δ: the choice minus '{table.best_arm}', question by question, "
        "95% bootstrap interval over questions"
    )
    lines.extend(
        [
            "",
            "| choice | mean | n | 95% CI vs best | paired Δ |",
            "|---|---|---|---|---|",
        ]
    )
    lines.extend(_render_row(row) for row in table.rows)
    return "\n".join(lines) + "\n"


__all__ = [
    "ReplayRow",
    "ReplayTable",
    "UnscoredMetricError",
    "render_replay_table",
    "replay",
]
