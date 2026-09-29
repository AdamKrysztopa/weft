"""Gold-referee calibration of the pairwise judge — task 44.43b, owner's choice 2026-09-29.

On a question set with gold answers, two arms' answers whose gold-based `answer_correctness`
differ clearly have a known better answer. The pairwise judge's verdict on those pairs is scored
against it: agreement over the pairs the judge decided, with a Wilson interval, and ties counted
apart. The selection and the arithmetic are pure; only judging calls a model, and that call goes
through the shipped `weft` binary — `main` never imports `weft_llm` or opens an event loop itself
(fitness function 7(a): `asyncio.run` may appear only at `weft_cli.cli`, plus its own named
waivers).
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from weft_eval.run_record import load_run_record
from weft_kernel.payload import Produced


class CalibrationRow(BaseModel):
    """A single judged pair and its correctness against gold."""

    model_config = {"frozen": True}

    question: str
    gold: str
    judge: str
    arm_a: str = ""
    arm_b: str = ""
    delta: float = 0.0


class Agreement(BaseModel):
    """Summary statistics over decided pairs."""

    model_config = {"frozen": True}

    agree: int
    decided: int
    ties: int
    rate: float | None
    low: float | None
    high: float | None


def clear_pairs(
    scores: Mapping[str, Mapping[str, float]], *, threshold: float
) -> list[tuple[str, str, str]]:
    """Find arm pairs whose gold-based scores differ by >= threshold on each question.

    Args:
        scores: Mapping from arm name to mapping from question id to score.
        threshold: Minimum score difference to include a pair.

    Returns:
        List of (arm_a, arm_b, question) tuples, ordered by arm pair then question id.
        Both arm names appear in sorted order as they were presented to combinations.
    """
    pairs: list[tuple[str, str, str]] = []
    for arm_a, arm_b in itertools.combinations(sorted(scores), 2):
        for q in sorted(scores[arm_a]):
            if q in scores[arm_b] and abs(scores[arm_a][q] - scores[arm_b][q]) >= threshold:
                pairs.append((arm_a, arm_b, q))
    return pairs


def agreement(rows: Sequence[CalibrationRow]) -> Agreement:
    """Compute agreement statistics and Wilson interval.

    Args:
        rows: Judged pairs with gold verdicts.

    Returns:
        Agreement with rate and Wilson 95% CI (None when no decided pairs).
    """
    ties = sum(1 for r in rows if r.judge == "tie")
    decided = len(rows) - ties
    agree = sum(1 for r in rows if r.judge == r.gold and r.judge != "tie")

    rate: float | None = None
    low: float | None = None
    high: float | None = None

    if decided > 0:
        rate = agree / decided
        z = 1.96
        p = rate
        n = decided
        den = 1 + z * z / n
        numerator = p + z * z / (2 * n)
        margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        low = (numerator - margin) / den
        high = (numerator + margin) / den

    return Agreement(agree=agree, decided=decided, ties=ties, rate=rate, low=low, high=high)


def rows_from_record(
    record: Mapping[str, object], scores: Mapping[str, Mapping[str, float]]
) -> list[CalibrationRow]:
    """Score one `weft eval pairwise` record's verdicts against `answer_correctness` gold.

    `record["baseline"]`/`record["arm"]` are `arm_a`/`arm_b`; each verdict's own `gold` is
    `"a"` when the baseline scored higher on `scores`, `"b"` otherwise — a tie in `scores`
    (`delta == 0`) also reads as `"b"`, since `clear_pairs` never selects a pair this close and a
    caller that judges one anyway gets a definite answer rather than a third gold value nothing
    else in this module knows how to score. `judge` is the verdict's own reconciled `outcome`,
    kept as the caller wrote it — `agreement` only ever compares it against `gold` as strings.

    Args:
        record: One parsed `weft_eval.pairwise.PairwiseRecord`, as `json.loads` returns it.
        scores: Every arm's `answer_correctness` score, by question id.

    Returns:
        One `CalibrationRow` per verdict, in the record's own order.
    """
    arm_a = cast(str, record["baseline"])
    arm_b = cast(str, record["arm"])
    verdicts = cast(Sequence[Mapping[str, object]], record["verdicts"])
    rows: list[CalibrationRow] = []
    for verdict in verdicts:
        question = cast(str, verdict["question_id"])
        delta = scores[arm_a][question] - scores[arm_b][question]
        rows.append(
            CalibrationRow(
                question=question,
                gold="a" if delta > 0 else "b",
                judge=cast(str, verdict["outcome"]),
                arm_a=arm_a,
                arm_b=arm_b,
                delta=round(delta, 6),
            )
        )
    return rows


def _scores_by_arm(runs: Path) -> dict[str, dict[str, float]]:
    """`answer_correctness`'s own per-question `Produced` value, by arm.

    Repetition 1 only — `weft_eval.pairwise.compare_arms`'s own `(arm, 1)` key, so a calibration
    run scores the identical record the judge itself will read.
    """
    scores: dict[str, dict[str, float]] = {}
    for path in sorted(runs.glob("*.json")):
        record = load_run_record(path)
        if record.experiment is None or record.experiment.repetition != 1:
            continue
        if record.question_scores is None:
            continue
        per_question = record.question_scores.get("answer_correctness")
        if per_question is None:
            continue
        scores[record.experiment.arm] = {
            question: outcome.value
            for question, outcome in per_question.scores.items()
            if isinstance(outcome, Produced)
        }
    return scores


def _group_pairs(pairs: Sequence[tuple[str, str, str]]) -> dict[tuple[str, str], list[str]]:
    """`clear_pairs`' own flat list, grouped by arm pair — one `--only` file per group."""
    groups: dict[tuple[str, str], list[str]] = {}
    for arm_a, arm_b, question in pairs:
        groups.setdefault((arm_a, arm_b), []).append(question)
    return groups


def _record_path_from_stdout(stdout: str, *, cwd: Path) -> Path:
    """The path `weft eval pairwise`'s own `pairwise record: <path>` line names.

    Relative to `cwd`, the directory the binary itself was run in — `EvalPairwiseCommandResult.
    record_path` is written relative to wherever `--experiment` resolved, never as an absolute
    path.
    """
    for line in stdout.splitlines():
        if line.startswith("pairwise record: "):
            printed = Path(line.removeprefix("pairwise record: ").strip())
            return printed if printed.is_absolute() else cwd / printed
    raise ValueError(f"no 'pairwise record: <path>' line in the judge's own stdout:\n{stdout}")


def _judge_group(
    *,
    weft: Path,
    cwd: Path,
    experiment: str,
    runs: Path,
    arm_a: str,
    arm_b: str,
    questions: Sequence[str],
) -> Path:
    """Judge `arm_a` against `arm_b` over `questions` alone, through `weft eval pairwise --only`.

    Fixed argv, no shell, nothing user-controlled but the caller-given `weft` path and the
    temporary `--only` file this writes — `scripts/check_isolated_installs.py`'s own sentence
    for the same shape.
    """
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as only_file:
        only_file.write("\n".join(questions) + "\n")
        only_path = Path(only_file.name)
    try:
        result = subprocess.run(  # noqa: S603
            [
                str(weft),
                "eval",
                "pairwise",
                experiment,
                arm_a,
                arm_b,
                "--criterion",
                "comprehensiveness",
                "--runs",
                str(runs),
                "--only",
                str(only_path),
            ],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        only_path.unlink(missing_ok=True)
    return _record_path_from_stdout(result.stdout, cwd=cwd)


def _summary_line(pairs: Sequence[tuple[str, str, str]], result: Agreement) -> str:
    if result.rate is None or result.low is None or result.high is None:
        return (
            f"pairs {len(pairs)}, judged {result.decided}, ties {result.ties}, "
            "agreement — no decided pairs"
        )
    return (
        f"pairs {len(pairs)}, judged {result.decided}, ties {result.ties}, "
        f"agreement {result.agree}/{result.decided} = {result.rate:.3f} "
        f"(Wilson 95% {result.low:.3f} to {result.high:.3f})"
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True, help="the experiment document, inside --cwd")
    parser.add_argument("--weft", type=Path, required=True, help="the shipped binary to run")
    parser.add_argument(
        "--cwd", type=Path, required=True, help="the run directory holding weft.toml and pipelines"
    )
    parser.add_argument("--runs", type=Path, required=True, help="the run records directory")
    parser.add_argument("--threshold", type=float, default=0.3)
    parser.add_argument(
        "--out", type=Path, required=True, help="where to write the calibration JSON"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Judge every clear pair through `weft eval pairwise --only`, and score it against gold.

    Reads `answer_correctness`'s own per-question scores from `--runs`, selects the pairs
    `clear_pairs` calls clear at `--threshold`, judges each arm pair's own clear questions in one
    `weft eval pairwise --only` call, scores every verdict against gold (`rows_from_record`), and
    writes `--out` — `{threshold, pairs, rows, agreement}` — plus one printed summary line.

    Args:
        argv: The command-line arguments; `None` reads `sys.argv`.

    Returns:
        0 — a calibration run's own verdict is `--out` and the printed summary, never an exit
        code a caller would branch on.
    """
    args = _parse_args(argv)
    scores = _scores_by_arm(args.runs)
    pairs = clear_pairs(scores, threshold=args.threshold)
    groups = _group_pairs(pairs)

    rows: list[CalibrationRow] = []
    for (arm_a, arm_b), questions in groups.items():
        record_path = _judge_group(
            weft=args.weft,
            cwd=args.cwd,
            experiment=args.experiment,
            runs=args.runs,
            arm_a=arm_a,
            arm_b=arm_b,
            questions=questions,
        )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        rows.extend(rows_from_record(record, scores))

    result = agreement(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "threshold": args.threshold,
                "pairs": len(pairs),
                "rows": [row.model_dump() for row in rows],
                "agreement": result.model_dump(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(_summary_line(pairs, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
