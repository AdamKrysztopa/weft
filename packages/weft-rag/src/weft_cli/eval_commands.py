"""`weft eval run|compare` and `weft trace` — task **4.6**: let an operator ask what a run
actually did, after `docs/03-cli.md` → *Command surface* named both and 4.4 built the record
they read.

**Q2, settled here, restating and closing the question 4.4 and 4.5 already answered in their
own ledger entries** (`.phase4-design.md` §3): `weft trace` reads the **persisted run record**
task 4.4 built, never exported OTel spans. The kernel depends on `opentelemetry-api` only, and
`01` → *The kernel boundary* is explicit that everything that **exports** a span is a pack; Phase
4 ships no exporter pack (4.5's own finding: the seam already emits everything a future exporter
would need, and nothing in this tree configures a real `TracerProvider` outside a test fixture).
Reading spans would mean shipping an exporter pack as a second artefact this phase never
budgeted. The record is the cheaper, and the honest, answer — and it forces a **narrowing** of
what `03` promises: that document said `weft trace` would "replay what a run actually did",
language that fits a span-level replay (stage durations, which stage failed and why) far better
than it fits four static facts. `weft trace` here prints exactly what `weft_eval.run_record.
RunRecord` carries — the resolved pipeline, the corpus identity, the model versions taken as
given, and the active distribution set — and nothing about per-stage timing or attribution,
because nothing in this tree persists that. `docs/03-cli.md` is corrected in the same commit
that ships this module, per the standing rule against a control document that paraphrases a
capability it does not have.

**`weft eval run <path> <pipeline>` — `pipeline` is not optional, and that is a decision, not an
omission.** A run record's `resolved_pipeline` field is mandatory (`weft_eval.run_record.
RunRecord`, "four fields, and no more"), and only a *named* pipeline document produces a
`weft_kernel.resolution.ResolvedPipeline` at all — the default four-stage `weft index` path
builds its `StageSpec`s as Python constants and never calls `resolve()`, which is the exact gap
task 4.0 exists to have closed for a document, and has no resolved form to persist regardless.
So `weft eval run` cannot offer `weft index`'s optional `--pipeline`; a caller names one, always.
Per `weft_cli.argparse_gen`'s own mechanical floor — "a field with no default is a required
positional... a field with a default is an optional flag" — a value with no honest default is
spelled as a **second positional**, `weft_cli.pipeline_commands.PipelineDeriveArgs`'s own
`<parent> <name>` shape, never as a `--pipeline` flag pretending to be optional when it is not.

**`weft eval run` reuses `weft_cli.ingest.run_index` unchanged, rather than re-deriving pipeline
resolution or extraction.** Task 4.0 already built the bridge from a named document to a real
run (`_specs_from_document`, `PipelineMissingExtractStageError`, every accepted-extension
derivation); this module's own contribution is two facts `run_index`'s `IndexResult` did not use
to carry back before this task — `resolved_pipeline` and `document_ids` — added to that
dataclass rather than re-computed here a second, divergent way. See `weft_cli.ingest.
IndexResult`'s own docstring for the extension.

**`model_versions` is `{}` today, and that is 4.7's gap, named rather than filled dishonestly.**
`RunRecord.model_versions`'s own docstring: "taken as given, never derived here... only whoever
drove the pipeline does." For the default `weft index` path that driver is `[services] embed`;
but `weft eval run` only ever runs a *named* pipeline, and Q3 (task 4.0) settled that `--pipeline`
never reads `[services]` at all — a document's own `use:`/`with:` on every stage decides what
runs, so `deps.services.embed` is not even the plugin this run actually used. Stamping it in
anyway would be exactly the wrong, misleading value V3's own failure clause warns about: "a
baseline from a different corpus, pipeline or **model version**." Leaving the field empty and
naming the gap is the honest choice; which providers and model versions a real run pins is
`docs/build-ledger.md` task **4.7**'s own job (`09` §4, V5), not invented here to make this
task's record look more complete than it is.

**`weft eval compare <a> <b>` refuses outright, rather than answering, when the two runs are not
apples to apples — `09-release.md` §4's own V3 failure clause, applied at the CLI seam.** "A
shipped technique's improvement is reported against... a baseline from a different corpus,
pipeline or model version" is the exact shape a comparison across two persisted runs can produce
by accident if it only ever prints a pipeline diff: two runs over different corpora, or with a
different active distribution set (`weft_eval.run_record`'s own docstring: "`weft eval compare`
across two pipelines is meaningless if the installed pack set differed between them" — this is
FF8(c)'s reason to exist, restated here at its first real caller), differ by more than the
pipeline, and a caller who only reads a stage-by-stage diff would misattribute a metric delta to
the pipeline change alone. So `EvalCompareCommand` checks `corpus`/`model_versions`/
`active_distributions` for exact equality **before** it ever computes a pipeline diff, and raises
`IncomparableRunsError`, naming which facts differ, rather than silently reporting a diff that is
true but is not the fact a caller is actually asking about — CLAUDE.md's rule: "a silent fallback
is worse than a failure." When all three agree, `weft_cli.pipeline_diff.diff_resolved` — already
proven exact by `weft pipeline diff` (task 3.7) — is reused unchanged for the pipeline half; this
module writes no second comparison logic.

**Run ids are filenames, and `runs/` is a project-local directory, on `weft_cli.pipeline_catalogue.
DEFAULT_PIPELINES_DIR`'s own footing** — a single, obvious, cwd-relative default, no new
`weft.toml` key. `weft eval run` mints one with `uuid.uuid4()` (the same generator `weft_cli.cli.
_context()` already uses for `Context.run_id`/`trace_id`) and writes `runs/<id>.json` through
`weft_eval.run_record.write_run_record` unchanged; `weft eval compare`/`weft trace` read one back
through `load_run_record`, refusing by name — `UnknownRunIdError`, naming every run id actually
found under `runs/` — for one that does not exist, `01` requirement 5's rule applied to a run id
exactly as `weft_cli.pipeline_catalogue.UnknownPipelineNameError` already applies it to a
pipeline name.

**Permission classes, decided rather than defaulted.** `EvalRunCommand` is `write`-class: it
indexes a corpus (`docs/03-cli.md` → *Permissions*' own worked example, "index into a new
collection") and writes a file under `runs/` — a *create*, on `weft_cli.commands.InitCommand`'s
and `weft_cli.pipeline_commands.PipelineDeriveCommand`'s own repaired footing, never `overwrite`:
a run id is a fresh `uuid4` every call, so there is nothing an invocation could ever collide with
to ask a TTY about. `EvalCompareCommand`/`TraceCommand` are `read`-class — both only load files
already on disk and refuse loudly if one is missing; neither writes anything. **No command in
this module is `overwrite`/`destroy`-class**, on the same footing `docs/03-cli.md` → *Permissions*
already records for every first-party command as of the 2026-08-20 repair: none of the three
needs a TTY to run non-interactively, which is exactly what a CI job invoking `weft eval run`
inside a pipeline needs to be true.

**`weft trace <run-id>` is a required positional, narrowing `docs/03-cli.md`'s published
`weft trace [<run-id>]`.** The bracket implied an *optional* positional — "no id given" falling
back to something, the way `/trace` in the REPL falls back to the session's own last run. But
`weft_cli.argparse_gen`'s own floor (this module's earlier paragraph) has no shape for an
optional positional, only a required one or an optional flag, and inventing one here — the way
`weft_cli.pipeline_commands`'s own module docstring already declined to invent a CLI grammar for
`derive`'s four operator shapes — would be a second, one-off argparse mechanism built for a
single caller. There is also no honest fallback to invent: a bare `weft trace` process has no
session and no "last run" of its own the way the REPL does (`weft_cli.session.SessionState`'s
whole reason to exist is that a *session* carries that fact; a one-shot process carries none).
So the id is required, and `03`'s command surface line is corrected in the same commit.

**Task 4.7 fills two gaps this module's own docstring named rather than invented.**
`model_versions` is derived from the resolved pipeline itself, never from `[services]` (Q3
still holds — a named pipeline never reads it): `_model_versions` reads each stage's own
resolved `config` for a `model` field, generically, the same `getattr`-defensive idiom
`weft_kernel.resolution`/`weft_kernel.runner` already use for `requires`/`provides` — a stage
whose plugin declares no `model` field (`hash`, `pgvector`) contributes nothing, and one that
does (`OpenAIEmbedderConfig.model`) is pinned with no table anywhere naming which stages carry
a model. `wall_clock_seconds` is `time.monotonic()` around the real work `run_index` does — the
one concrete, executable "run" in this tree today, and V5's wall-clock half measured rather
than estimated for it.

**`weft eval metrics` — V5's "the offline subset must be identifiable as a subset."**
`EvalMetricsCommand` renders `weft_eval.offline.gate_subset`'s own answer: every registered
metric name, partitioned by whether it runs in the deterministic gate subset. Given a `name`,
it asks a different, narrower question — `weft_eval.offline.require_gate_safe` — and refuses
loudly, naming why and what would permit it, for a metric that cannot run there; it never
returns a degraded or empty result for one, per CLAUDE.md's rule against a metric that quietly
scores nothing because a credential was missing. `read`-class: it only reads the registry
`deps.registry` already built at process start, and writes nothing.

**`weft eval run --questions <path>` — task 4.9, `.phase4-design.md` §7's gap closed.**
`RunRecord.metrics` was `{}` for every run before this task, so `weft eval compare` could only
report that two runs' resolved pipelines *differ*, never what they *produced* — a diff of the
inputs, not a comparison of the outputs. `--questions` is optional, and `--top-k` defaults to
`5`: given a question file, `EvalRunCommand` calls `weft_cli.eval_scoring.score_pipeline`
after indexing (never before — retrieval needs a store with something in it) and folds the
result into `record.metrics` through `build_run_record`'s own `metrics=` parameter. With no
`--questions`, `metrics` stays `{}`, the same honesty `model_versions` already had before task
4.7 named its own gap rather than filling it dishonestly.

**`weft eval compare` reports `metrics_comparison` — the comparison the tool generates itself,
not two `RunRecord`s a caller has to read side by side.** For every metric name either run's own
`metrics` carries, `_metrics_comparison` pairs the two `MetricRunResult`s under one key; a run
that never scored that metric (no `--questions`, or a metric this run's pipeline could not
retrieve for) contributes an honest `NotAggregated("not measured for this run…")` on its own
side, never silence and never a fabricated number standing in for "unmeasured." A metric neither
run scored never appears at all — nothing invented where there is nothing to report. This is
what closes Phase 4's own exit criterion: two derived pipelines that genuinely differ in what
they retrieve now produce a comparison naming the difference in scores, not only in
stage-by-stage structure.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Final, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.eval_scoring import load_questions, score_pipeline
from weft_cli.ingest import run_index
from weft_cli.pipeline_diff import PipelineDiff, diff_resolved
from weft_cli.registry_bootstrap import Dependencies
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_eval.aggregate import MetricAggregate
from weft_eval.offline import GateSubset, gate_subset, require_gate_safe
from weft_eval.run_record import (
    MetricRunResult,
    NotAggregated,
    RunRecord,
    build_run_record,
    corpus_identity,
    load_run_record,
    write_run_record,
)
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_kernel.runner import RunSummary

#: `EvalRunArgs.top_k` default — `weft ask`'s own default depth, task 4.9's own retrieval
#: scoring reuses it rather than inventing a second "how many results" default.
_DEFAULT_TOP_K: Final[int] = 5

#: `EvalCompareCommand`'s own explanation for a metric one run never scored — never silence,
#: never a fabricated number standing in for "unmeasured."
_NOT_MEASURED = NotAggregated(
    reason="not measured for this run — 'weft eval run' was not given --questions, or this "
    "pipeline had nothing to retrieve against"
)

#: See the module docstring's own paragraph on why this is a project-local, cwd-relative
#: directory rather than a `weft.toml` key.
DEFAULT_RUNS_DIR: Final[Path] = Path("runs")

_EVAL_RUN_HELP = (
    "run a named pipeline over a corpus and persist a run record — resolved pipeline, corpus "
    "identity, active distribution set, and (with --questions) per-metric aggregates — so a "
    "later 'weft eval compare' can diff it against another. 'pipeline' is required: a run "
    "record needs a resolved pipeline to persist."
)

_EVAL_COMPARE_HELP = (
    "the exact, structural difference between two persisted runs' pipelines, and their "
    "per-metric aggregates side by side — refuses if the two ran over a different corpus, "
    "model versions or active distribution set, rather than reporting a diff that is not "
    "apples to apples"
)

_TRACE_HELP = (
    "print what one persisted run recorded — its resolved pipeline, corpus, model versions "
    "and active distribution set"
)

_EVAL_METRICS_HELP = (
    "which registered metrics run in the deterministic gate subset — no credentials, no "
    "network, no model download — and which do not, or ask about one metric by name"
)


class EmptyCorpusError(WeftError):
    """`weft eval run` found nothing under `path` for `pipeline`'s own extractor to read.

    Not raised by `weft index` for the identical directory — an empty corpus is a legitimate,
    silent no-op there (`weft_cli.ingest`'s own module docstring: "An empty directory is not an
    error"). It is refused here instead: a run record with zero documents has an empty,
    content-derived digest indistinguishable from any *other* empty corpus's digest
    (`weft_eval.run_record.corpus_identity`'s own hash-of-sorted-ids construction), so persisting
    one would not be a fact worth diffing against later — it would be a record that looks
    complete and measures nothing, which is the shape CLAUDE.md's "a silent fallback is worse
    than a failure" rule exists to refuse.
    """

    def __init__(self, message: str, *, path: str, pipeline: str) -> None:
        super().__init__(message)
        self.path = path
        self.pipeline = pipeline


class IncomparableRunsError(WeftError):
    """`weft eval compare` refused two runs that differ by more than their pipeline.

    See the module docstring's own paragraph — this is `09-release.md` §4's V3 failure clause
    ("a baseline from a different corpus, pipeline or model version"), enforced before a
    pipeline diff is ever computed rather than left for a reader to notice by the numbers being
    wrong.
    """

    def __init__(self, message: str, *, run_a: str, run_b: str, reasons: tuple[str, ...]) -> None:
        super().__init__(message)
        self.run_a = run_a
        self.run_b = run_b
        self.reasons = reasons


class UnknownRunIdError(WeftError, UnresolvedNameError):
    """`weft eval compare`/`weft trace` named a run id `runs/` (or wherever `DEFAULT_RUNS_DIR`
    points) does not hold.

    Fitness function 12's family: `valid_options` is every run id actually found on disk —
    every `*.json` file's own stem under the runs directory — the same "list what does exist"
    rule `weft_cli.pipeline_catalogue.UnknownPipelineNameError` already gives a pipeline name.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], run_id: str) -> None:
        super().__init__(message)
        self.valid_options = valid_options
        self.run_id = run_id


class EvalRunArgs(BaseModel):
    """`weft eval run <path> <pipeline> [--corpus-name NAME]` — see the module docstring for
    why `pipeline` is a second required positional rather than `weft index`'s optional flag.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="directory to index")
    pipeline: str = Field(
        description=(
            "the pipeline document to run — the same set 'weft pipeline show' resolves names "
            "against. Required: a persisted run needs a resolved pipeline (ledger task 4.0)."
        )
    )
    corpus_name: str | None = Field(
        default=None,
        description=(
            "a label for this corpus in the persisted record, defaulting to --path itself. "
            "Two runs compare only when their corpus identity — this name plus a "
            "content-derived digest over the documents actually indexed — agrees."
        ),
    )
    questions: str | None = Field(
        default=None,
        description=(
            "a JSON file of {query, relevant_documents} judgements (task 4.9) — when given, "
            "this run also retrieves for every question and scores the gate-safe "
            "RetrievalMetric subset over the result, folding it into the persisted record's "
            "own 'metrics'. Omitted, 'metrics' stays empty, the same honesty "
            "'model_versions' had before task 4.7 named its own gap."
        ),
    )
    top_k: int = Field(
        default=_DEFAULT_TOP_K,
        ge=1,
        description="how many passages to retrieve per question when --questions is given.",
    )


class EvalCompareArgs(BaseModel):
    """`weft eval compare <a> <b>` — two run ids, `weft pipeline diff`'s own `<a> <b>` shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: str = Field(description="the first run id, printed by 'weft eval run'")
    b: str = Field(description="the second run id")


class TraceArgs(BaseModel):
    """`weft trace <run-id>` — see the module docstring for why this is required, not optional."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(description="the run id 'weft eval run' printed")


class EvalMetricsArgs(BaseModel):
    """`weft eval metrics [--name <name>]` — every registered metric's gate-safety, or one by
    name. `name` has a default (`None`), so `weft_cli.argparse_gen`'s own mechanical floor —
    a field with no default is a required positional, one with a default is an optional flag —
    makes this `--name`, not a positional; see `TraceArgs`'s own paragraph, one class up, for
    the identical rule applied the other way (`run_id` has no default, so it stays positional).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str | None = Field(
        default=None,
        description=(
            "look up one registered metric's own gate-safety instead of listing every metric. "
            "Refuses, naming why and what would permit it, for a metric that cannot run in the "
            "deterministic gate subset — never a degraded or empty answer for one."
        ),
    )


class EvalRunCommandResult(CommandResult):
    """`weft eval run`'s whole answer — the run id it minted, what `run_index` produced, and
    the record it persisted.

    `wall_clock_seconds` is task 4.7's own addition — measured around the real work this
    command does, never estimated, and carried here rather than on `RunRecord`, which stays at
    the five fields `weft_eval.run_record`'s own docstring fixes (task 4.9 added `metrics`, the
    fifth).
    """

    run_id: str
    path: str
    summary: RunSummary
    stored_count: int | None
    record: RunRecord
    wall_clock_seconds: float


class MetricComparison(BaseModel):
    """One metric's result across two compared runs — task 4.9, closing `.phase4-design.md`
    §7's gap: a comparison of what two runs *produced*, not only of their resolved pipelines.

    `a`/`b` are `weft_eval.run_record.MetricRunResult` — `Produced[MetricAggregate]` for a run
    that scored this metric, `NotAggregated` for one that did not (see `_NOT_MEASURED`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: MetricRunResult
    b: MetricRunResult


def _metrics_comparison(a: RunRecord, b: RunRecord) -> Mapping[str, MetricComparison]:
    """Every metric name either `a.metrics` or `b.metrics` carries, paired under one key —
    see `MetricComparison`'s own docstring and the module docstring's paragraph on
    `weft eval compare`'s own `metrics_comparison`.
    """
    names = sorted(set(a.metrics) | set(b.metrics))
    return {
        name: MetricComparison(
            a=a.metrics.get(name, _NOT_MEASURED), b=b.metrics.get(name, _NOT_MEASURED)
        )
        for name in names
    }


class EvalCompareCommandResult(CommandResult):
    """`weft eval compare`'s whole answer, once both runs pass the apples-to-apples check —
    a refusal is raised before this is ever constructed, see `IncomparableRunsError`.

    `metrics_comparison` is task 4.9's own addition — see `_metrics_comparison`.
    """

    run_a: str
    run_b: str
    corpus_matches: bool
    model_versions_match: bool
    active_distributions_match: bool
    pipeline_diff: PipelineDiff
    metrics_comparison: Mapping[str, MetricComparison]


class TraceCommandResult(CommandResult):
    """`weft trace`'s whole answer — the persisted record itself, unmodified."""

    run_id: str
    record: RunRecord


class EvalMetricsCommandResult(CommandResult):
    """`weft eval metrics`'s whole answer — see `EvalMetricsCommand`.

    With no `name`, `gate_safe`/`gate_unsafe` is `weft_eval.offline.gate_subset`'s own full
    partition. With `name`, a metric that passed `require_gate_safe` is echoed back alone in
    `gate_safe` — one that did not never reaches this type at all, because it raised instead.
    """

    gate_safe: tuple[str, ...]
    gate_unsafe: tuple[str, ...]


def _run_ids(directory: Path) -> tuple[str, ...]:
    """Every run id persisted under `directory` — every `*.json` file's own stem, sorted."""
    if not directory.is_dir():
        return ()
    return tuple(sorted(path.stem for path in directory.glob("*.json")))


def _load_or_refuse(run_id: str, *, directory: Path = DEFAULT_RUNS_DIR) -> RunRecord:
    """`run_id` loaded from `directory`, or `UnknownRunIdError` naming every id that does exist."""
    path = directory / f"{run_id}.json"
    if not path.is_file():
        options = _run_ids(directory)
        raise UnknownRunIdError(
            f"'{run_id}' is not a persisted run — checked '{directory}'. Persisted runs: "
            f"{', '.join(options) or '(none)'}.",
            valid_options=options,
            run_id=run_id,
        )
    return load_run_record(path)


def _model_field(config: object) -> str | None:
    """The `model` field a resolved stage's own `config` carries, or `None` — see the module
    docstring's paragraph on task 4.7's `model_versions` fill. `config` is either a plugin's own
    `config_model` instance (a `BaseModel`) or an empty read-only mapping — `weft_kernel.
    resolution.StageConfig`'s own two shapes — so both are read, generically, never by importing
    any one plugin's config class by name.
    """
    if isinstance(config, BaseModel):
        value = getattr(config, "model", None)
        return value if isinstance(value, str) else None
    if isinstance(config, Mapping):
        mapping = cast("Mapping[str, object]", config)
        value = mapping.get("model")
        return value if isinstance(value, str) else None
    return None


def _model_versions(resolved_pipeline: ResolvedPipeline) -> Mapping[str, str]:
    """Every stage of `resolved_pipeline` whose own config names a `model`, as `use:model`.

    Never reads `[services]` (Q3, task 4.0) and never a table of "which stages carry a model" —
    `hash`, `pgvector` and every plugin whose `config_model` has no `model` field simply
    contribute nothing, derived rather than special-cased.
    """
    versions: dict[str, str] = {}
    stage: ResolvedStage
    for stage in resolved_pipeline.stages:
        model = _model_field(stage.config)
        if model is not None:
            versions[stage.id] = f"{stage.use}:{model}"
    return versions


def _incomparable_reasons(a: RunRecord, b: RunRecord) -> tuple[str, ...]:
    """Which of the three facts a comparison depends on actually differ — see
    `IncomparableRunsError`'s own docstring. Empty means the two runs are comparable.
    """
    reasons: list[str] = []
    if a.corpus != b.corpus:
        reasons.append(
            f"corpus differs ('{a.corpus.name}' {a.corpus.digest[:12]}… vs "
            f"'{b.corpus.name}' {b.corpus.digest[:12]}…)"
        )
    if a.model_versions != b.model_versions:
        reasons.append(
            f"model versions differ ({dict(a.model_versions)} vs {dict(b.model_versions)})"
        )
    if a.active_distributions != b.active_distributions:
        reasons.append(
            f"active distributions differ ({a.active_distributions} vs {b.active_distributions})"
        )
    return tuple(reasons)


class EvalRunCommand:
    """`weft eval run` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = EvalRunArgs
    result_model: ClassVar[type[CommandResult]] = EvalRunCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _EVAL_RUN_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        run_args = cast(EvalRunArgs, args)
        deps = ctx.require(Dependencies)

        # Task 4.7, V5's wall-clock half: measured around the real work, never estimated.
        started = time.monotonic()
        result = await run_index(
            Path(run_args.path),
            registry=deps.registry,
            ctx=ctx,
            pipeline=run_args.pipeline,
            reports=deps.reports,
        )
        wall_clock_seconds = time.monotonic() - started
        if not result.document_ids:
            raise EmptyCorpusError(
                f"'{run_args.path}' produced nothing to index under pipeline "
                f"'{run_args.pipeline}' — there is nothing for a run record to carry a "
                f"corpus identity over. Point --path at a directory pipeline "
                f"'{run_args.pipeline}' can actually read.",
                path=run_args.path,
                pipeline=run_args.pipeline,
            )
        # `run_index` always sets `resolved_pipeline` on the `pipeline=` path — see
        # `weft_cli.ingest.IndexResult`'s own docstring — and `pipeline` is required above.
        resolved_pipeline = cast(ResolvedPipeline, result.resolved_pipeline)

        # Task 4.9's own gap to fill — see the module docstring's paragraph on `--questions`.
        # `{}` with no `--questions`, the same honesty `model_versions` had before task 4.7.
        metrics: Mapping[str, Outcome[MetricAggregate]] = {}
        if run_args.questions is not None:
            questions = load_questions(Path(run_args.questions))
            metrics = await score_pipeline(
                registry=deps.registry,
                resolved_pipeline=resolved_pipeline,
                questions=questions,
                top_k=run_args.top_k,
                ctx=ctx,
            )

        corpus_name = run_args.corpus_name if run_args.corpus_name is not None else run_args.path
        corpus = corpus_identity(corpus_name, result.document_ids)
        record = build_run_record(
            recorded_at=datetime.now(UTC).isoformat(),
            resolved_pipeline=resolved_pipeline,
            corpus=corpus,
            # Task 4.7's own gap to fill — see the module docstring's paragraph on
            # `_model_versions`. Derived from what actually ran, never from `[services]`.
            model_versions=_model_versions(resolved_pipeline),
            reports=deps.reports,
            metrics=metrics,
        )
        run_id = str(uuid.uuid4())
        write_run_record(record, DEFAULT_RUNS_DIR / f"{run_id}.json")

        return Produced(
            value=EvalRunCommandResult(
                run_id=run_id,
                path=run_args.path,
                summary=result.summary,
                stored_count=result.stored_count,
                record=record,
                wall_clock_seconds=wall_clock_seconds,
            )
        )


class EvalCompareCommand:
    """`weft eval compare` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = EvalCompareArgs
    result_model: ClassVar[type[CommandResult]] = EvalCompareCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _EVAL_COMPARE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        compare_args = cast(EvalCompareArgs, args)
        record_a = _load_or_refuse(compare_args.a)
        record_b = _load_or_refuse(compare_args.b)

        reasons = _incomparable_reasons(record_a, record_b)
        if reasons:
            raise IncomparableRunsError(
                f"'{compare_args.a}' and '{compare_args.b}' are not comparable as a change of "
                f"pipeline alone: {'; '.join(reasons)}. A comparison is only meaningful when "
                f"the corpus, model versions and active distribution set agree and only the "
                f"pipeline differs — otherwise a metric delta cannot be attributed to the "
                f"pipeline change ('09-release.md' §4, V3's own failure clause).",
                run_a=compare_args.a,
                run_b=compare_args.b,
                reasons=reasons,
            )

        diff = diff_resolved(record_a.resolved_pipeline, record_b.resolved_pipeline)
        return Produced(
            value=EvalCompareCommandResult(
                run_a=compare_args.a,
                run_b=compare_args.b,
                corpus_matches=True,
                model_versions_match=True,
                active_distributions_match=True,
                pipeline_diff=diff,
                metrics_comparison=_metrics_comparison(record_a, record_b),
            )
        )


class TraceCommand:
    """`weft trace` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = TraceArgs
    result_model: ClassVar[type[CommandResult]] = TraceCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _TRACE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        trace_args = cast(TraceArgs, args)
        record = _load_or_refuse(trace_args.run_id)
        return Produced(value=TraceCommandResult(run_id=trace_args.run_id, record=record))


class EvalMetricsCommand:
    """`weft eval metrics [--name <name>]` — see the module docstring's own V5 paragraph."""

    args_model: ClassVar[type[BaseModel]] = EvalMetricsArgs
    result_model: ClassVar[type[CommandResult]] = EvalMetricsCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _EVAL_METRICS_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        metrics_args = cast(EvalMetricsArgs, args)
        deps = ctx.require(Dependencies)

        if metrics_args.name is None:
            subset: GateSubset = gate_subset(deps.registry)
            return Produced(
                value=EvalMetricsCommandResult(
                    gate_safe=subset.gate_safe, gate_unsafe=subset.gate_unsafe
                )
            )

        # Raises `UnknownMetricNameError` or `MetricNeedsCredentialsError` — either way this
        # line never returns a degraded answer for a metric that cannot run.
        require_gate_safe(deps.registry, metrics_args.name)
        return Produced(
            value=EvalMetricsCommandResult(gate_safe=(metrics_args.name,), gate_unsafe=())
        )


def register_eval_commands(registrar: PackRegistrar) -> None:
    """Register `eval run`, `eval compare`, `eval metrics` and the top-level `trace` — called
    from `weft_cli.commands.register`, never from a second entry point.
    """
    registrar.add(Command, "eval run", EvalRunCommand)
    registrar.add(Command, "eval compare", EvalCompareCommand)
    registrar.add(Command, "eval metrics", EvalMetricsCommand)
    registrar.add(Command, "trace", TraceCommand)


__all__ = [
    "DEFAULT_RUNS_DIR",
    "EmptyCorpusError",
    "EvalCompareArgs",
    "EvalCompareCommand",
    "EvalCompareCommandResult",
    "EvalMetricsArgs",
    "EvalMetricsCommand",
    "EvalMetricsCommandResult",
    "EvalRunArgs",
    "EvalRunCommand",
    "EvalRunCommandResult",
    "IncomparableRunsError",
    "MetricComparison",
    "TraceArgs",
    "TraceCommand",
    "TraceCommandResult",
    "UnknownRunIdError",
    "register_eval_commands",
]
