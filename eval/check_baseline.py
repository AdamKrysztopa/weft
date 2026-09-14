"""Prerequisite **V3** — did a later run reproduce the baseline? Answered without choosing.

`docs/09-release.md` §4.3 states the rule in one sentence: *"a later run reproduces the baseline
when every metric falls inside that recorded interval, and fails when any metric falls outside
it."* That is the whole of this module. **There is no threshold here, no tolerance argument, and
no default anybody could tune** — the only numbers it compares against are the `low` and `high`
the baseline's own repetitions produced.

**Since repair R22.4b, this file decides nothing itself.** `weft_eval.baseline.judge_reproduction`
is the judge, importable from the installed `weft-rag` wheel with no checkout: it refuses a
comparison against a baseline the pipeline document itself states differently — a different
corpus, stage, config, model, depth or question set — and reports, rather than refuses on, what
an installation says about itself (`distribution`, `contract_version`, `applies_to`), because any
behavioural effect that has is caught by the metric intervals, not by a field comparison. This
file is the hand-run wrapper: it loads two files, calls the judge, and prints what it found.

Hand-run, and a `main()` is honest here where `eval/check_questions.py` has none: nothing in this
file is `async`, so it needs no second bridge (fitness function 7(a)).

    uv run python eval/check_baseline.py eval/baselines/<baseline>.json <later-run>.json
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from weft_eval.baseline import IncomparableBaselinesError, judge_reproduction, load_baseline_report


def build_parser() -> argparse.ArgumentParser:
    """Two runs: the baseline that recorded the intervals, and the run being judged."""
    parser = argparse.ArgumentParser(description="judge a run against a recorded baseline")
    parser.add_argument("baseline", type=Path, help="the run whose intervals are the tolerance")
    parser.add_argument("later", type=Path, help="the run being judged")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print what fell outside, and what installation moved, and exit non-zero if it did not."""
    args = build_parser().parse_args(argv)
    published = load_baseline_report(Path(args.baseline))
    later = load_baseline_report(Path(args.later))
    try:
        reproduction = judge_reproduction(published, later)
    except IncomparableBaselinesError as exc:
        print(f"check_baseline: {exc}", file=sys.stderr)
        return 2
    for difference in reproduction.provenance:
        print(
            f"installation differs at stage '{difference.stage}': "
            f"{difference.field.value} {difference.published} -> {difference.later}"
        )
    if not reproduction.reproduced:
        for verdict in reproduction.verdicts:
            if verdict.inside:
                continue
            if verdict.later is None:
                print(
                    f"{verdict.metric}: the baseline records [{verdict.low}, {verdict.high}] "
                    f"and this run did not measure it at all",
                    file=sys.stderr,
                )
            else:
                print(
                    f"{verdict.metric}: {verdict.later} is outside the interval the baseline's "
                    f"{published.repeats} repetitions spanned, [{verdict.low}, {verdict.high}]",
                    file=sys.stderr,
                )
        return 1
    print(
        f"{len(reproduction.verdicts)} metric(s) inside the interval "
        f"{published.repeats} repetitions of the baseline spanned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
