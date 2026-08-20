"""Prerequisite **V3** — did a later run reproduce the baseline? Answered without choosing.

`docs/09-release.md` §4.3 states the rule in one sentence: *"a later run reproduces the baseline
when every metric falls inside that recorded interval, and fails when any metric falls outside
it."* That is the whole of this module. **There is no threshold here, no tolerance argument, and
no default anybody could tune** — the only numbers it compares against are the `low` and `high`
the baseline's own repetitions produced.

Three properties follow, and `09` names them: a deterministic system records a zero-width
interval and admits no drift at all, which is correct and strict; a noisy one records a wide
interval and says so honestly; and a baseline that skipped the repetition cannot be built at all
(`eval/metrics.py`'s `MetricRecord`), so it fails V3 rather than producing an unfalsifiable
criterion.

**A comparison against the wrong baseline is refused, not scored.** V3's failure clause is *"a
technique's improvement is reported against no baseline, or against a baseline from a different
corpus, pipeline or model version"* — so a run whose corpus, resolved pipeline, model versions or
retrieval depth differs is `IncomparableRunsError`, naming what differs. A near-miss comparison
that produced a plausible number would be the more dangerous outcome, because nothing about the
number would look wrong.

**Since task 4.8, "corpus", "pipeline" and "model versions" are read off `BaselineReport.record`
— a real `weft_eval.run_record.RunRecord` — rather than off a hand-rolled digest and a second
hand-rolled stage list.** `ResolvedPipeline`'s own docstring is explicit that two resolutions of
the same document are comparable by `==`, so the pipeline check here is a plain equality rather
than a digest this module used to compute a second way.

Hand-run, and a `main()` is honest here where `eval/check_questions.py` has none: nothing in this
file is `async`, so it needs no second bridge (fitness function 7(a)).

    uv run python eval/check_baseline.py eval/baselines/<baseline>.json <later-run>.json
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from run_baseline import BaselineReport, load_run


class IncomparableRunsError(Exception):
    """The two runs do not describe the same measurement, so comparing them means nothing."""


def comparable(baseline: BaselineReport, later: BaselineReport) -> None:
    """Refuse a comparison V3 says is not one, naming every field that differs.

    Every field checked here is one V3 names, and nothing else is: two runs may legitimately
    differ in when they were taken, how long they took, and which questions failed to measure.
    """
    differences: list[str] = []
    if baseline.record.corpus != later.record.corpus:
        differences.append(
            f"corpus {baseline.record.corpus.digest[:12]}… vs "
            f"{later.record.corpus.digest[:12]}… "
            f"({sorted(baseline.tiers)} vs {sorted(later.tiers)})"
        )
    if baseline.record.resolved_pipeline != later.record.resolved_pipeline:
        differences.append("pipeline differs (see 'weft eval compare' for the stage-by-stage diff)")
    if dict(baseline.record.model_versions) != dict(later.record.model_versions):
        differences.append(
            f"models {dict(baseline.record.model_versions)} vs {dict(later.record.model_versions)}"
        )
    if baseline.retrieval_depth != later.retrieval_depth:
        differences.append(f"retrieval depth {baseline.retrieval_depth} vs {later.retrieval_depth}")
    if differences:
        message = (
            "these two runs measure different things, so neither reproduces the other: "
            + "; ".join(differences)
        )
        raise IncomparableRunsError(message)


def regressions(baseline: BaselineReport, later: BaselineReport) -> tuple[str, ...]:
    """Every metric of `later` that falls outside the interval `baseline`'s repetitions spanned.

    A metric the baseline measured and the later run did not is a failure too, and deliberately
    the same kind: a run that stopped computing a number cannot be said to have reproduced it,
    and silently comparing what remains is how a suite shrinks to the metrics that still pass.
    """
    comparable(baseline, later)
    failures: list[str] = []
    for record in baseline.metrics:
        found = later.metric(record.metric)
        if found is None:
            failures.append(
                f"{record.metric}: the baseline records [{record.low}, {record.high}] and this "
                f"run did not measure it at all"
            )
            continue
        if record.outside(found.mean):
            failures.append(
                f"{record.metric}: {found.mean} is outside the interval the baseline's "
                f"{len(record.values)} repetitions spanned, [{record.low}, {record.high}]"
            )
    return tuple(failures)


def build_parser() -> argparse.ArgumentParser:
    """Two runs: the baseline that recorded the intervals, and the run being judged."""
    parser = argparse.ArgumentParser(description="judge a run against a recorded baseline")
    parser.add_argument("baseline", type=Path, help="the run whose intervals are the tolerance")
    parser.add_argument("later", type=Path, help="the run being judged")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print what fell outside, and exit non-zero if anything did."""
    args = build_parser().parse_args(argv)
    baseline = load_run(Path(args.baseline))
    later = load_run(Path(args.later))
    try:
        failures = regressions(baseline, later)
    except IncomparableRunsError as exc:
        print(f"check_baseline: {exc}", file=sys.stderr)
        return 2
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(
        f"{len(baseline.metrics)} metric(s) inside the interval "
        f"{baseline.repeats} repetitions of the baseline spanned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
