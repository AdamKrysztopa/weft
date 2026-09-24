"""Run one experiment document with the checks a long measurement needs — ledger `R41.4`.

*(Cited `41.7` until 2026-09-20, and no such task line has ever existed in `build-ledger.md` —
`L19.9`'s shape, found by trying to update "the 41.4/41.7 entries" and looking for the second one.
This file was built and committed under `R41.4`, which is what owns it.)*

Phase 41 paid for the five things this does, in one night: a nine-hour replay stalled for three
hours behind a full disk while its log printed elapsed minutes (`L28.8`); a six-hour arm was refused
by its own consumer because a 7B model returns 49 judgements for 50 passages, which one call would
have shown (`L28.9`); a served model's dtype went unrecorded (`L28.5`); and a container started with
no memory cap was killed by the host (`L28.2`). None of that is visible from inside
`weft eval experiment`, and none of it should depend on somebody watching.

So this runs *around* the binary, never instead of it:

1. **Preflight** — free disk against a floor, the model endpoint answering, and its identity
   recorded with the run.
2. **A spend ceiling** — measured cost per execution times the plan's own count, refused before the
   run when it exceeds what is left of the cap.
3. **Progress** — records written since the last sample, into a file anyone can `tail`, with no
   session attached.
4. **A floor watched while it runs** — the run is stopped when free disk crosses it, rather than
   wedging the store.
5. **A verdict on the run itself** — a record whose `excluded` is not zero is reported as invalid
   rather than read as a null, which is exactly what a run that meets a rate limit looks like.

It is deliberately outside `weft_cli`: it orchestrates a process, reads the host and prices a run,
none of which the CLI should learn to do.

**Fixed argv, no shell, nothing user-controlled** — `scripts/check_isolated_installs.py`'s own
sentence for the same thing: the two `subprocess` calls below carry `# noqa: S603` because the
program is a path this script was given and every other element is a literal.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from weft_eval.run_record import RunRecord, load_run_record
from weft_kernel.payload import Failed, Produced

#: Free disk below this is what wedged the store on 2026-09-20. Swap is deliberately not a floor:
#: macOS keeps it nearly full by design, and the first version of this check stopped a healthy run.
DISK_FLOOR_MB = 3072


@dataclass(frozen=True)
class Plan:
    """What `weft eval plan` says this document will do."""

    executions: int
    arms: tuple[str, ...]


def free_disk_mb(path: str = "/System/Volumes/Data") -> int:
    """Free space on the volume the runs write to, in whole megabytes.

    Args:
        path: A path on the volume to measure.

    Returns:
        The free space in MB, rounded down.
    """
    return shutil.disk_usage(path).free // (1024 * 1024)


def plan_of(weft: Path, document: Path, cwd: Path) -> Plan:
    """`weft eval plan`, parsed — the executions it declares and the arms it names."""
    printed = subprocess.run(  # noqa: S603
        [str(weft), "eval", "plan", document.name],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    executions = 0
    arms: list[str] = []
    for line in printed.splitlines():
        if line.strip().startswith("total query executions:"):
            executions = int(line.split(":")[1])
        elif ":" in line and "→" in line:
            arms.append(line.split(":")[0].strip())
    return Plan(executions=executions, arms=tuple(arms))


def refuse(reason: str) -> None:
    """Stop the run before it starts, naming why on stderr.

    Args:
        reason: What precondition failed.

    Raises:
        SystemExit: Always, with exit code 2.
    """
    print(f"REFUSED: {reason}", file=sys.stderr, flush=True)
    raise SystemExit(2)


def preflight(args: argparse.Namespace, plan: Plan) -> dict[str, Any]:
    """Everything that must be true before a run starts, or it does not start."""
    disk = free_disk_mb()
    if disk < DISK_FLOOR_MB:
        refuse(f"{disk} MB of free disk, below the {DISK_FLOOR_MB} MB floor")

    identity: dict[str, Any] = {}
    if args.info_url:
        try:
            identity = httpx.get(args.info_url, timeout=10.0).json()
        except httpx.HTTPError as exc:
            refuse(f"the model endpoint {args.info_url} did not answer: {type(exc).__name__}")

    price = args.price_per_question * plan.executions
    if args.cap is not None and price > args.cap:
        refuse(
            f"the plan's {plan.executions} executions price at ${price:.2f}, "
            f"above the ${args.cap:.2f} left of the cap"
        )
    return {
        "free_disk_mb": disk,
        "plan_executions": plan.executions,
        "arms": list(plan.arms),
        "estimated_usd": round(price, 4),
        "model_identity": identity,
    }


def records(runs: Path) -> list[Path]:
    """The run records written so far, sorted by name.

    Args:
        runs: The directory `weft eval experiment` writes its records into.

    Returns:
        Every `*.json` under `runs`, or nothing when the directory does not exist yet.
    """
    return sorted(runs.glob("*.json")) if runs.exists() else []


def _reason_histogram(record: RunRecord, metric: str) -> list[str]:
    """Why each excluded question was excluded, counted by kind — `lessons.md` `L28.10`.

    A count of exclusions names no cause, and the missing cause is what gets guessed at. Phase 41
    read "823 of 830 excluded" as a 7B model's incapacity three times running, against two
    different real defects and finally a defect in this project's own prompt; the per-question
    `reason` field said which it was every time, and nothing printed it. So the verdict prints the
    kinds, not only the total — a run whose exclusions are all one kind and one whose exclusions
    are three kinds are different failures, and the summary that hides that is what `L28.10` cost.

    Kinds are read from the reason's own words rather than a taxonomy, because the reasons are
    written by the stages that refuse and no enum spans them.
    """
    keyed = (record.question_scores or {}).get(metric)
    if keyed is None:
        return []
    counted: dict[str, int] = {}
    for outcome in keyed.scores.values():
        if not isinstance(outcome, Failed):
            continue
        reason = outcome.reason
        kind = next(
            (
                phrase
                for phrase in (
                    "repeating span",
                    "could not parse",
                    "not judged at all",
                    "more than once",
                )
                if phrase in reason
            ),
            reason.split(":")[-1].strip()[:60],
        )
        counted[kind] = counted.get(kind, 0) + 1
    return [
        f"      {count:>5} × {kind}" for kind, count in sorted(counted.items(), key=lambda p: -p[1])
    ]


def verdict_on(runs: Path, metric: str = "mrr@5") -> list[str]:
    """What each written record says about itself — and whether it is readable at all.

    Read through `weft_eval.run_record`'s own model rather than as JSON, so a record this script
    cannot parse is a failure here rather than a silently absent line.
    """
    lines: list[str] = []
    for path in records(runs):
        record = load_run_record(path)
        outcome = record.metrics.get(metric)
        if not isinstance(outcome, Produced):
            lines.append(f"  {path.stem}: {metric} not aggregated — INVALID")
            continue
        aggregate = outcome.value
        state = "INVALID (questions excluded)" if aggregate.excluded else "ok"
        arm = record.experiment.arm if record.experiment is not None else "?"
        repetition = record.experiment.repetition if record.experiment is not None else "?"
        lines.append(
            f"  {arm} r{repetition}: {metric} {aggregate.mean:.4f} over n={aggregate.n}, "
            f"excluded={aggregate.excluded} — {state}"
        )
        if aggregate.excluded:
            lines.extend(_reason_histogram(record, metric))
    return lines


def main(argv: list[str] | None = None) -> int:
    """Preflight one experiment, run it under a disk watch, and log the verdict on its records.

    Args:
        argv: The command-line arguments; `None` reads `sys.argv`.

    Returns:
        The experiment's exit code; 3 when it was stopped for disk, 4 when a record is invalid.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path, help="the experiment document, inside --cwd")
    parser.add_argument("--cwd", type=Path, required=True, help="the project directory to run in")
    parser.add_argument("--weft", type=Path, required=True, help="the shipped binary to run")
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--price-per-question", type=float, default=0.0)
    parser.add_argument("--cap", type=float, default=None, help="dollars left of the spend cap")
    parser.add_argument(
        "--info-url", default=None, help="the served model's /info, when it has one"
    )
    parser.add_argument("--interval", type=float, default=300.0)
    args = parser.parse_args(argv)

    def say(text: str) -> None:
        with args.progress.open("a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%F %T')} {text}\n")

    runs = args.cwd / "runs"
    plan = plan_of(args.weft, args.document, args.cwd)
    say(f"preflight ok: {json.dumps(preflight(args, plan))}")

    started = time.time()
    with (args.cwd / f"{args.document.stem}.log").open("w", encoding="utf-8") as output:
        running = subprocess.Popen(  # noqa: S603
            [str(args.weft), "eval", "experiment", args.document.name, "--yes"],
            cwd=args.cwd,
            stdout=output,
            stderr=subprocess.STDOUT,
            env={**os.environ, "WEFT_MEASUREMENT_CHECKED": "1"},
        )
        seen = len(records(runs))
        while running.poll() is None:
            time.sleep(args.interval)
            now, disk = len(records(runs)), free_disk_mb()
            say(
                f"running {int((time.time() - started) / 60)} min: {now} record(s) "
                f"(+{now - seen} since last sample), {disk} MB free"
            )
            seen = now
            if disk < DISK_FLOOR_MB:
                running.terminate()
                say(f"STOPPED: {disk} MB of free disk, below the floor")
                return 3

    say(f"finished EXIT={running.returncode} after {int((time.time() - started) / 60)} min")
    read = verdict_on(runs)
    for line in read:
        say(line)
    if any("INVALID" in line for line in read):
        say("RUN INVALID: a record excluded questions — read it as a failure, never as a null")
        return 4
    return running.returncode


if __name__ == "__main__":
    raise SystemExit(main())
