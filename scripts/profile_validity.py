"""E5, offline: which `profile_query` features identify the regimes the experiments measure.

Task **44.52**. A routing rule may test a feature only if the feature says something reliable
about the question it is asked of. Over a question set whose axes carry a gold label — MuSiQue's
`control`, QASPER's `answer-type` — each **boolean** feature of
`weft_retrieve.profile.profile_query` is scored against each value that label takes: precision is
how often the label holds when the feature fires, recall is how often the feature fires when the
label holds. A feature is
**routable** for a label only when the 95% Wilson lower bound of its precision reaches
`ROUTABLE_PRECISION` on the train split and again, independently, on held-out, so a perfect
precision over a handful of firings does not count; a feature that misses either bar stays
descriptive — it may
still be reported on, but no routing rule may pivot on it. No model is called anywhere in this
module: `profile_query` is pure, and scoring against `axes` needs nothing but the question set
already on disk.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from weft_eval.question_set import Question, read_question_set
from weft_retrieve.profile import profile_query

#: A feature is routable for a label only once both splits' precision lower bound reaches this bar.
ROUTABLE_PRECISION: Final[float] = 0.80
#: The normal quantile for a two-sided 95% Wilson interval.
_Z: Final[float] = 1.96

type BooleanFeatures = Mapping[str, bool]
type ScoredQuestion = tuple[BooleanFeatures, str]


class SplitScore(BaseModel):
    """One feature's precision and recall against one label value, over one split.

    `support` is how many questions in the split carry the label value at all; `fired` is how
    many the feature fired on. `precision`/`recall` are `None` rather than `0.0` when their
    denominator (`fired`/`support`) is zero — a feature that never fires has said nothing, which
    is not the same claim as having said something wrong every time.
    """

    model_config = ConfigDict(frozen=True)

    support: int
    fired: int
    precision: float | None
    #: The 95% Wilson lower bound of `precision`; `None` when the feature never fired.
    precision_lower: float | None
    recall: float | None


class FeatureValidity(BaseModel):
    """One boolean feature's validity for one label value of one axis."""

    model_config = ConfigDict(frozen=True)

    feature: str
    axis: str
    label_value: str
    train: SplitScore
    held_out: SplitScore
    routable: bool


def _boolean_features(question: Question) -> BooleanFeatures:
    profile = profile_query(question.text, locale=question.language)
    return {name: value for name, value in profile.features().items() if isinstance(value, bool)}


def _grouped_by_split(
    questions: Sequence[Question], *, axis: str, split_axis: str, splits: tuple[str, str]
) -> dict[str, list[ScoredQuestion]]:
    """Every question's boolean features and `axis` label, bucketed by `split_axis`.

    A question missing `axis` or `split_axis` is refused naming the question id and the missing
    axis, before its split is even looked at — a question this check would have silently ignored
    is not a question whose axes are allowed to be wrong. A question whose split is neither
    member of `splits` is then dropped without complaint.
    """
    by_split: dict[str, list[ScoredQuestion]] = {split: [] for split in splits}
    for question in questions:
        if axis not in question.axes:
            raise ValueError(f"{question.id}: carries no '{axis}' axis")
        if split_axis not in question.axes:
            raise ValueError(f"{question.id}: carries no '{split_axis}' axis")
        split = question.axes[split_axis]
        if split not in by_split:
            continue
        by_split[split].append((_boolean_features(question), question.axes[axis]))
    return by_split


def _split_score(rows: Sequence[ScoredQuestion], *, feature: str, label_value: str) -> SplitScore:
    support = sum(1 for _, label in rows if label == label_value)
    fired = sum(1 for features, _ in rows if features[feature])
    hits = sum(1 for features, label in rows if features[feature] and label == label_value)
    return SplitScore(
        support=support,
        fired=fired,
        precision=hits / fired if fired else None,
        precision_lower=_wilson_lower(hits, fired),
        recall=hits / support if support else None,
    )


def _wilson_lower(hits: int, trials: int) -> float | None:
    if trials == 0:
        return None
    rate = hits / trials
    denominator = 1 + _Z**2 / trials
    centre = rate + _Z**2 / (2 * trials)
    spread = _Z * ((rate * (1 - rate) / trials + _Z**2 / (4 * trials**2)) ** 0.5)
    return (centre - spread) / denominator


def _routable(train: SplitScore, held_out: SplitScore) -> bool:
    return (
        train.precision_lower is not None
        and held_out.precision_lower is not None
        and train.precision_lower >= ROUTABLE_PRECISION
        and held_out.precision_lower >= ROUTABLE_PRECISION
    )


def validity(
    questions: Sequence[Question],
    *,
    axis: str,
    split_axis: str = "split",
    train: str = "dev",
    held_out: str = "test",
) -> list[FeatureValidity]:
    """Every boolean `profile_query` feature scored against every value `axis` takes.

    One row per (feature, distinct label value of `axis`), ordered by feature then label value.
    Non-boolean features — `query.word_count` and the three anchor counts — are skipped, because
    a routing rule tests presence, not a magnitude this function was not asked to threshold.
    """
    by_split = _grouped_by_split(
        questions, axis=axis, split_axis=split_axis, splits=(train, held_out)
    )
    pool = [*by_split[train], *by_split[held_out]]
    features = sorted({name for row, _ in pool for name in row})
    label_values = sorted({label for _, label in pool})

    rows: list[FeatureValidity] = []
    for feature in features:
        for label_value in label_values:
            train_score = _split_score(by_split[train], feature=feature, label_value=label_value)
            held_out_score = _split_score(
                by_split[held_out], feature=feature, label_value=label_value
            )
            rows.append(
                FeatureValidity(
                    feature=feature,
                    axis=axis,
                    label_value=label_value,
                    train=train_score,
                    held_out=held_out_score,
                    routable=_routable(train_score, held_out_score),
                )
            )
    return rows


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _precision(score: SplitScore) -> str:
    if score.precision is None or score.precision_lower is None:
        return "—"
    return f"{score.precision:.3f} (≥ {score.precision_lower:.3f})"


def render(rows: Sequence[FeatureValidity], *, title: str) -> str:
    """A markdown section over `rows`, one table row per feature/label pair."""
    header = (
        "| feature | label | train precision | train recall | held-out precision "
        "| held-out recall | routable |"
    )
    separator = "| --- | --- | --- | --- | --- | --- | --- |"
    lines = [f"## {title}", "", header, separator]
    for row in rows:
        label_cell = (
            f"{row.label_value} ({row.train.support} train / {row.held_out.support} held-out)"
        )
        cells = (
            row.feature,
            label_cell,
            _precision(row.train),
            _fmt(row.train.recall),
            _precision(row.held_out),
            _fmt(row.held_out.recall),
            "yes" if row.routable else "no",
        )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _parse_set(text: str) -> tuple[str, Path, str]:
    """`NAME=PATH:AXIS` — a question file's title, where it lives, and the axis to score against."""
    name, _, rest = text.partition("=")
    path_text, _, axis = rest.rpartition(":")
    return name, Path(path_text), axis


def main(argv: Sequence[str] | None = None) -> int:
    """Print E5's validity table for every `--set` named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--set",
        dest="sets",
        type=_parse_set,
        action="append",
        required=True,
        metavar="NAME=PATH:AXIS",
        help="a question file and the axis to score its boolean profile features against",
    )
    args = parser.parse_args(argv)

    print("# E5 — profile feature validity", flush=True)
    for name, path, axis in args.sets:
        rows = validity(read_question_set(path).questions, axis=axis)
        print(render(rows, title=name), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
