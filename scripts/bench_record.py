"""Session-record harness for Phase 29 task **29.12**.

G22's widened *Bring* is one JSON record per run, naming the machine, the image digests, every
extension version, the row counts before and after each arm, and each arm's numbers
(`fix-plans/07` → task 29.12). Six harnesses already write their own run model as JSON via
`--record` — `bench_latency.LatencyRun` (29.1), `bench_filtered.FilteredRun` (29.7),
`bench_quantised.QuantisedRun` (29.8), `bench_diskann.DiskannRun` (29.9),
`bench_widths.WidthsRun` (29.10) and `bench_qdrant.QdrantRun` (29.11). This module turns those run
models into one record of *arms*, each naming the ledger task it came from, which of G22's five
positions it informs, the row counts taken immediately before and after it, and its numbers. The
table the session reads is generated from that record and never typed.

A converter reads a run model's own fields; it never re-derives or invents a number. An arm whose
before and after row counts differ is refused, never recorded — `ArmRecord.checked` is the one
door every converter builds an arm through.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import bench_diskann
import bench_filtered
import bench_latency
import bench_qdrant
import bench_quantised
import bench_settings
import bench_widths
from pydantic import BaseModel, ConfigDict, ValidationError

from weft_store.contract import VectorPrecision


class G22Position(StrEnum):
    COMMIT_AT_FIRST_WRITE = "1 commit at first write"
    CONFIGURED_WIDTH = "2 configured width"
    EXPRESSION_INDEXES = "3 expression indexes per width"
    UNINDEXED_CEILING = "4 unindexed, ceiling documented"
    LABEL_COLUMN = "5 typed column plus label column"


class Measure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    value: float
    unit: str


def _format_measure(measure: Measure) -> str:
    n = f"{int(measure.value):,}" if measure.value.is_integer() else f"{measure.value:g}"
    return f"{measure.label} {n} {measure.unit}".rstrip()


def _numbers(measures: Iterable[Measure]) -> str:
    return "; ".join(_format_measure(measure) for measure in measures)


class ArmRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task: str
    name: str
    positions: tuple[G22Position, ...]
    rows_before: int
    rows_after: int
    measures: tuple[Measure, ...]

    @classmethod
    def checked(
        cls,
        *,
        task: str,
        name: str,
        positions: tuple[G22Position, ...],
        rows_before: int,
        rows_after: int,
        measures: tuple[Measure, ...],
    ) -> ArmRecord:
        bench_latency.assert_rows(label=f"{task} {name}", expected=rows_before, found=rows_after)
        return cls(
            task=task,
            name=name,
            positions=positions,
            rows_before=rows_before,
            rows_after=rows_after,
            measures=measures,
        )


class VersionFact(BaseModel):
    """A finding that was not taken between two row counts — `facts_from_diskann`'s expression
    probe runs after the diskann harness's last result, with no row count around it
    (`bench_diskann.py:582 "probe = _expression_probe(conn)"`). A row count is never invented for
    it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: str
    positions: tuple[G22Position, ...]
    statement: str
    measures: tuple[Measure, ...]


class ImageDigest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    image: str
    digest: str


class ExtensionVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str


class BenchRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: bench_latency.Machine
    images: tuple[ImageDigest, ...]
    extensions: tuple[ExtensionVersion, ...]
    arms: tuple[ArmRecord, ...]
    facts: tuple[VersionFact, ...] = ()
    taken_at: datetime


class MachineMismatchError(ValueError):
    """The runs being folded into one record did not all measure on the same machine."""


class ImageDigestError(RuntimeError):
    """`docker image inspect` could not resolve a digest for a named image."""


def arms_from_latency(run: bench_latency.LatencyRun) -> tuple[ArmRecord, ...]:
    return tuple(
        ArmRecord.checked(
            task="29.1",
            name=f"{result.arm} at {result.chunks:,} x {result.width}",
            positions=(G22Position.UNINDEXED_CEILING,),
            rows_before=result.rows_before,
            rows_after=result.rows_after,
            measures=(
                Measure(label="p50", value=result.p50_ms, unit="ms"),
                Measure(label="p95", value=result.p95_ms, unit="ms"),
            ),
        )
        for result in run.results
    )


def arms_from_filtered(run: bench_filtered.FilteredRun) -> tuple[ArmRecord, ...]:
    arms: list[ArmRecord] = []
    for result in run.results:
        sel = result.selectivity.value if result.selectivity is not None else "unfiltered"
        arms.append(
            ArmRecord.checked(
                task="29.7",
                name=f"hnsw {sel} iterative_scan={result.iterative_scan} plan {result.plan}",
                positions=(G22Position.COMMIT_AT_FIRST_WRITE, G22Position.CONFIGURED_WIDTH),
                rows_before=result.rows_before,
                rows_after=result.rows_after,
                measures=(
                    Measure(label="recall@10", value=result.recall_at_10, unit=""),
                    Measure(
                        label="rows returned, minimum", value=float(result.returned_min), unit=""
                    ),
                    Measure(label="rows returned, mean", value=result.returned_mean, unit=""),
                    Measure(label="p50", value=result.p50_ms, unit="ms"),
                    Measure(label="p95", value=result.p95_ms, unit="ms"),
                ),
            )
        )
    return tuple(arms)


def arms_from_quantised(run: bench_quantised.QuantisedRun) -> tuple[ArmRecord, ...]:
    builds_by_quantisation = {build.quantisation: build for build in run.builds}
    arms: list[ArmRecord] = []
    for result in run.results:
        sel = result.selectivity.value if result.selectivity is not None else "unfiltered"
        build = builds_by_quantisation[result.quantisation]
        arms.append(
            ArmRecord.checked(
                task="29.8",
                name=(
                    f"{result.quantisation} hnsw oversampling {result.oversampling} "
                    f"{sel} plan {result.plan}"
                ),
                positions=(
                    G22Position.COMMIT_AT_FIRST_WRITE,
                    G22Position.CONFIGURED_WIDTH,
                    G22Position.EXPRESSION_INDEXES,
                ),
                rows_before=result.rows_before,
                rows_after=result.rows_after,
                measures=(
                    Measure(label="recall@10", value=result.recall_at_10, unit=""),
                    Measure(
                        label="rows returned, minimum", value=float(result.returned_min), unit=""
                    ),
                    Measure(label="p50", value=result.p50_ms, unit="ms"),
                    Measure(label="p95", value=result.p95_ms, unit="ms"),
                    Measure(label="index build", value=build.build_seconds, unit="s"),
                    Measure(label="index size", value=float(build.index_bytes), unit="bytes"),
                ),
            )
        )
    return tuple(arms)


def arms_from_diskann(run: bench_diskann.DiskannRun) -> tuple[ArmRecord, ...]:
    arms: list[ArmRecord] = []
    for result in run.results:
        sel = result.selectivity.value if result.selectivity is not None else "unfiltered"
        if result.arm is bench_diskann.DiskannArm.JSONB_POST_FILTER:
            positions = (G22Position.COMMIT_AT_FIRST_WRITE, G22Position.CONFIGURED_WIDTH)
            build = run.plain_build
        else:
            positions = (G22Position.LABEL_COLUMN,)
            build = run.labelled_build
        arms.append(
            ArmRecord.checked(
                task="29.9",
                name=f"diskann {result.arm} {sel} plan {result.plan}",
                positions=positions,
                rows_before=result.rows_before,
                rows_after=result.rows_after,
                measures=(
                    Measure(label="recall@10", value=result.recall_at_10, unit=""),
                    Measure(
                        label="rows returned, minimum", value=float(result.returned_min), unit=""
                    ),
                    Measure(label="p50", value=result.p50_ms, unit="ms"),
                    Measure(label="p95", value=result.p95_ms, unit="ms"),
                    Measure(label="index build", value=build.build_seconds, unit="s"),
                    Measure(label="index size", value=float(build.index_bytes), unit="bytes"),
                ),
            )
        )
    return tuple(arms)


def facts_from_diskann(run: bench_diskann.DiskannRun) -> tuple[VersionFact, ...]:
    probe = run.expression_probe
    built = "yes" if probe.built else "no"
    queryable = "yes" if probe.queryable else "no"
    suffix = f" ({probe.error})" if probe.error is not None else ""
    statement = (
        f"expression diskann index over a bare column on vectorscale {run.vectorscale_version}: "
        f"built {built}, queryable {queryable}{suffix}"
    )
    return (
        VersionFact(
            task="29.9",
            positions=(G22Position.EXPRESSION_INDEXES,),
            statement=statement,
            measures=(
                Measure(label="built", value=1.0 if probe.built else 0.0, unit=""),
                Measure(label="queryable", value=1.0 if probe.queryable else 0.0, unit=""),
            ),
        ),
    )


def arms_from_widths(run: bench_widths.WidthsRun) -> tuple[ArmRecord, ...]:
    api_by_width = {comparison.width: comparison for comparison in run.api}
    arms: list[ArmRecord] = []
    for result in run.results:
        measures = [
            Measure(
                label="exact recall@10 vs native", value=result.exact_recall_vs_native, unit=""
            ),
            Measure(label="hnsw recall@10 vs native", value=result.hnsw_recall_vs_native, unit=""),
            Measure(label="hnsw recall@10 vs exact", value=result.hnsw_recall_vs_exact, unit=""),
            Measure(label="exact p95", value=result.exact_p95_ms, unit="ms"),
            Measure(label="hnsw p95", value=result.hnsw_p95_ms, unit="ms"),
            Measure(label="index build", value=result.index_build_seconds, unit="s"),
            Measure(label="index size", value=float(result.index_bytes), unit="bytes"),
        ]
        comparison = api_by_width.get(result.width)
        if comparison is not None:
            measures.append(Measure(label="api min cosine", value=comparison.min_cosine, unit=""))
            measures.append(Measure(label="api samples", value=float(comparison.samples), unit=""))
        arms.append(
            ArmRecord.checked(
                task="29.10",
                name=f"width {result.width} of native {run.native_width}",
                positions=(G22Position.COMMIT_AT_FIRST_WRITE, G22Position.CONFIGURED_WIDTH),
                rows_before=result.rows_before,
                rows_after=result.rows_after,
                measures=tuple(measures),
            )
        )
    return tuple(arms)


def arms_from_qdrant(run: bench_qdrant.QdrantRun) -> tuple[ArmRecord, ...]:
    ingest_by_indexing = {entry.indexing: entry for entry in run.ingest_seconds}
    arms: list[ArmRecord] = []
    for result in run.results:
        sel = result.selectivity.value if result.selectivity is not None else "unfiltered"
        ingest = ingest_by_indexing[result.indexing]
        arms.append(
            ArmRecord.checked(
                task="29.11",
                name=f"qdrant {result.indexing} {sel}",
                positions=(G22Position.UNINDEXED_CEILING,),
                rows_before=result.points_before,
                rows_after=result.points_after,
                measures=(
                    Measure(label="recall@10", value=result.recall_at_10, unit=""),
                    Measure(
                        label="rows returned, minimum", value=float(result.returned_min), unit=""
                    ),
                    Measure(label="p50", value=result.p50_ms, unit="ms"),
                    Measure(label="p95", value=result.p95_ms, unit="ms"),
                    Measure(label="ingest", value=ingest.seconds, unit="s"),
                ),
            )
        )
    return tuple(arms)


def _positions_for_settings_arm(arm: bench_settings.Arm) -> tuple[G22Position, ...]:
    """Mirrors what the Phase 29 adapter gives the arm of the same configuration
    (`arms_from_filtered:165`, `arms_from_quantised:196-200`, `arms_from_qdrant:315`), so a
    comparison against Phase 29's arm of the same name is meaningful.
    """
    if arm.backend is bench_settings.Backend.QDRANT:
        return (G22Position.UNINDEXED_CEILING,)
    positions = [G22Position.COMMIT_AT_FIRST_WRITE, G22Position.CONFIGURED_WIDTH]
    if arm.precision in (VectorPrecision.FLOAT16, VectorPrecision.BINARY):
        positions.append(G22Position.EXPRESSION_INDEXES)
    return tuple(positions)


def arms_from_settings(run: bench_settings.SettingsRun) -> tuple[ArmRecord, ...]:
    arms: list[ArmRecord] = []
    for result in run.results:
        arm = result.arm
        sel = arm.selectivity.value if arm.selectivity is not None else "unfiltered"
        scan = (
            f" iterative_scan={arm.iterative_scan.value}" if arm.iterative_scan is not None else ""
        )
        name = f"{arm.backend.value} {arm.index.value} {arm.precision.value}{scan} {sel}"
        arms.append(
            ArmRecord.checked(
                task="31.6",
                name=name,
                positions=_positions_for_settings_arm(arm),
                rows_before=result.rows_before,
                rows_after=result.rows_after,
                measures=(
                    Measure(label="recall@10", value=result.recall_at_10, unit=""),
                    Measure(label="queries", value=float(result.queries), unit=""),
                    Measure(
                        label="rows returned, minimum", value=float(result.returned_min), unit=""
                    ),
                    Measure(label="p50", value=result.p50_ms, unit="ms"),
                    Measure(label="p95", value=result.p95_ms, unit="ms"),
                ),
            )
        )
    return tuple(arms)


def session_table(record: BenchRecord) -> str:
    lines = [
        "| G22 position | task | arm | numbers | rows before / after |",
        "|---|---|---|---|---|",
    ]
    for position in G22Position:
        arm_rows = [arm for arm in record.arms if position in arm.positions]
        fact_rows = [fact for fact in record.facts if position in fact.positions]
        if not arm_rows and not fact_rows:
            lines.append(f"| {position.value} | — | no arm informs this position | | |")
            continue
        for arm in arm_rows:
            lines.append(
                f"| {position.value} | {arm.task} | {arm.name} | {_numbers(arm.measures)} | "
                f"{arm.rows_before:,} / {arm.rows_after:,} |"
            )
        for fact in fact_rows:
            lines.append(
                f"| {position.value} | {fact.task} | {fact.statement} | "
                f"{_numbers(fact.measures)} | not counted |"
            )
    return "\n".join(lines)


def missing_positions(record: BenchRecord) -> tuple[G22Position, ...]:
    named = {position for arm in record.arms for position in arm.positions}
    named |= {position for fact in record.facts for position in fact.positions}
    return tuple(position for position in G22Position if position not in named)


def write_record(path: Path, record: BenchRecord) -> None:
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")


def read_record(path: Path) -> BenchRecord:
    return BenchRecord.model_validate_json(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------
# The driving half: `docker image inspect` and argparse. Not unit-tested for the same reason no
# sibling harness's `main` is — it shells out, and is exercised by actually running it.
# ---------------------------------------------------------------------------------------------

RunModel = (
    bench_latency.LatencyRun
    | bench_filtered.FilteredRun
    | bench_quantised.QuantisedRun
    | bench_diskann.DiskannRun
    | bench_widths.WidthsRun
    | bench_qdrant.QdrantRun
    | bench_settings.SettingsRun
)


def _read_runs[T: BaseModel](paths: Sequence[Path], model: type[T]) -> tuple[T, ...]:
    return tuple(model.model_validate_json(path.read_text(encoding="utf-8")) for path in paths)


def _resolve_digest(image: str) -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise ImageDigestError(f"no `docker` executable on PATH to resolve a digest for {image!r}")
    result = subprocess.run(  # noqa: S603
        [docker, "image", "inspect", "--format", "{{index .RepoDigests 0}}", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ImageDigestError(
            f"`docker image inspect` exited {result.returncode} for {image!r}: "
            f"{result.stderr.strip()}"
        )
    digest = result.stdout.strip()
    if not digest:
        raise ImageDigestError(f"`docker image inspect` returned no digest for {image!r}")
    return digest


def _extension_versions(
    latency: Sequence[bench_latency.LatencyRun],
    filtered: Sequence[bench_filtered.FilteredRun],
    quantised: Sequence[bench_quantised.QuantisedRun],
    diskann: Sequence[bench_diskann.DiskannRun],
    widths: Sequence[bench_widths.WidthsRun],
    qdrant: Sequence[bench_qdrant.QdrantRun],
) -> tuple[ExtensionVersion, ...]:
    seen: dict[tuple[str, str], ExtensionVersion] = {}

    def _add(name: str, version: str) -> None:
        key = (name, version)
        if key not in seen:
            seen[key] = ExtensionVersion(name=name, version=version)

    for run in (*latency, *filtered, *quantised, *diskann, *widths, *qdrant):
        _add("postgresql", run.server_version)
        _add("vector", run.pgvector_version)
    for diskann_run in diskann:
        _add("vectorscale", diskann_run.vectorscale_version)
    for qdrant_run in qdrant:
        _add("qdrant", qdrant_run.qdrant_version)

    return tuple(seen.values())


def cmd_build(args: argparse.Namespace) -> int:
    latency = _read_runs(args.latency, bench_latency.LatencyRun)
    filtered = _read_runs(args.filtered, bench_filtered.FilteredRun)
    quantised = _read_runs(args.quantised, bench_quantised.QuantisedRun)
    diskann = _read_runs(args.diskann, bench_diskann.DiskannRun)
    widths = _read_runs(args.widths, bench_widths.WidthsRun)
    qdrant = _read_runs(args.qdrant, bench_qdrant.QdrantRun)
    settings = _read_runs(args.settings, bench_settings.SettingsRun)

    all_runs: tuple[RunModel, ...] = (
        *latency,
        *filtered,
        *quantised,
        *diskann,
        *widths,
        *qdrant,
        *settings,
    )
    if not all_runs:
        print(
            "no runs given: pass at least one of --latency/--filtered/--quantised/--diskann/"
            "--widths/--qdrant/--settings",
            file=sys.stderr,
        )
        return 2

    machines = list({run.machine.label: run.machine for run in all_runs}.values())
    if len(machines) > 1:
        labels = sorted(machine.label for machine in machines)
        raise MachineMismatchError(f"the runs ran on different machines: {' vs '.join(labels)}")
    machine = machines[0]

    images = tuple(ImageDigest(image=image, digest=_resolve_digest(image)) for image in args.image)
    extensions = _extension_versions(latency, filtered, quantised, diskann, widths, qdrant)

    arms: list[ArmRecord] = []
    for latency_run in latency:
        arms.extend(arms_from_latency(latency_run))
    for filtered_run in filtered:
        arms.extend(arms_from_filtered(filtered_run))
    for quantised_run in quantised:
        arms.extend(arms_from_quantised(quantised_run))
    for diskann_run in diskann:
        arms.extend(arms_from_diskann(diskann_run))
    for widths_run in widths:
        arms.extend(arms_from_widths(widths_run))
    for qdrant_run in qdrant:
        arms.extend(arms_from_qdrant(qdrant_run))
    for settings_run in settings:
        arms.extend(arms_from_settings(settings_run))

    facts: list[VersionFact] = []
    for diskann_run in diskann:
        facts.extend(facts_from_diskann(diskann_run))

    record = BenchRecord(
        machine=machine,
        images=images,
        extensions=extensions,
        arms=tuple(arms),
        facts=tuple(facts),
        taken_at=max(run.taken_at for run in all_runs),
    )

    write_record(args.out, record)
    print(session_table(record))

    missing = missing_positions(record)
    if missing:
        print("positions no arm informs: " + ", ".join(position.value for position in missing))

    return 0


def cmd_table(args: argparse.Namespace) -> int:
    print(session_table(read_record(args.record)))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench_record.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build", help="fold one or more harnesses' run records into one BenchRecord"
    )
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--latency", action="append", type=Path, default=[])
    build.add_argument("--filtered", action="append", type=Path, default=[])
    build.add_argument("--quantised", action="append", type=Path, default=[])
    build.add_argument("--diskann", action="append", type=Path, default=[])
    build.add_argument("--widths", action="append", type=Path, default=[])
    build.add_argument("--qdrant", action="append", type=Path, default=[])
    build.add_argument("--settings", action="append", type=Path, default=[])
    build.add_argument("--image", action="append", default=[])
    build.set_defaults(func=cmd_build)

    table = subparsers.add_parser("table", help="print the session table from a written record")
    table.add_argument("--record", type=Path, required=True)
    table.set_defaults(func=cmd_table)

    return parser


def main(argv: list[str] | None = None) -> int:
    bench_latency.line_buffer_stdout()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        MachineMismatchError,
        ImageDigestError,
        ValidationError,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
