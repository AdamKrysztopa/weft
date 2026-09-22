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

**`weft eval run` reuses `weft_cli.ingest.run_index_for` unchanged, rather than re-deriving pipeline
resolution or extraction.** Task 4.0 already built the bridge from a named document to a real
run (`_specs_from_document`, `PipelineMissingExtractStageError`, every accepted-extension
derivation); this module's own contribution is two facts `run_index`'s `IndexResult` did not use
to carry back before this task — `resolved_pipeline` and `document_ids`, joined by
`content_hashes` at task 16.0 — added to that dataclass rather than re-computed here a
second, divergent way. See `weft_cli.ingest.IndexResult`'s own docstring for the extension.

**`model_versions` is `{}` today, and that is 4.7's gap, named rather than filled dishonestly.**
`RunRecord.model_versions`'s own docstring: "taken as given, never derived here... only whoever
drove the pipeline does." For the default `weft index` path that driver is `[services] embed`;
but `weft eval run` only ever runs a *named* pipeline, and Q3 (task 4.0) settled that `--pipeline`
never reads `[services]` at all — a document's own `use:`/`with:` on every stage decides what
runs, so `deps.services.embed` is not even the plugin this run actually used. Stamping it in
anyway would be exactly the wrong, misleading value V3's own failure clause warns about: "a
baseline from a different corpus, pipeline or **model version**." Leaving the field empty and
naming the gap is the honest choice; which providers and model versions a real run pins is
`docs/internal/build-ledger.md` task **4.7**'s own job (`09` §4, V5), not invented here to make this
task's record look more complete than it is.

**`weft eval compare <a> <b>` refuses outright, rather than answering, when the two runs are not
apples to apples — `09-release.md` §4's own V3 failure clause, applied at the CLI seam.** "A
shipped technique's improvement is reported against... a baseline from a different corpus,
pipeline or model version" is the exact shape a comparison across two persisted runs can produce
by accident if it only ever prints a pipeline diff: two runs over different corpora, or with
different model versions, differ by more than the pipeline, and a caller who only reads a
stage-by-stage diff would misattribute a metric delta to the pipeline change alone. So
`EvalCompareCommand` checks `corpus`/`model_versions`/`question_set` for exact equality **before**
it ever computes a pipeline diff, and raises `IncomparableRunsError`, naming which facts differ,
rather than silently reporting a diff that is true but is not the fact a caller is actually asking
about — CLAUDE.md's rule: "a silent fallback is worse than a failure." Packaging is reported
beside that comparison instead (see the R22.11 paragraph below). When corpus, model versions and
question set agree,
`weft_cli.pipeline_diff.diff_resolved` — already proven exact by `weft pipeline diff` (task 3.7)
— is reused unchanged for the pipeline half; this module writes no second comparison logic.

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
still holds — a named pipeline never reads it): `model_versions_of` reads each stage's own
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

**`weft eval compare --baseline <pipeline>` — task 8.8, the falsification instrument reaching
the CLI.** `weft_eval.falsify` derives its own tolerance from a baseline's *repetitions*, so this
flag names a **pipeline**, never a run id: every persisted run under `DEFAULT_RUNS_DIR` whose own
`resolved_pipeline.name` equals it is one of that baseline's repetitions, `--a`/`--b` themselves
excluded (a rung is not one of its own baseline's repetitions). `NoBaselineRunsError` refuses a
name nothing under `runs/` ran, naming every pipeline that actually did. Each kept repetition is
checked against `run_a` with the identical `_incomparable_reasons` this module already uses for
`run_a`/`run_b` themselves — **the pipeline is deliberately not part of that check**: a baseline
is a different pipeline from the rung being judged by construction, which is the entire point,
and corpus and model versions are what make its variability a measurement of the same system.
`weft_eval.falsify.baseline_spreads`'s own `TooFewRepetitionsError`
propagates unchanged when only one repetition is found — reaching the operator as V3's own
refusal, never as a manufactured verdict. With no `--baseline`, this command returns exactly what
it always has, plus the three new fields at their empty/`None` defaults — it must not start
answering a question nobody asked.

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

**`weft eval compare <a> <b>` over two baseline report files — ledger repair `R22.4d`.** `01` →
Phase 6's Exit asks that "`weft eval compare` against the published baseline run reports every
metric inside the interval that baseline recorded". A published baseline
(`weft_eval.baseline.BaselineReport`) is not a persisted run — `_incomparable_reasons` above
compares `active_distributions` for exact equality, and G19 renamed every one of them, so that
check can never answer this question for a published file. When `--a`/`--b` both name a file on
disk, `EvalCompareCommand` takes a second path entirely: it loads each as a `BaselineReport` and
asks `weft_eval.baseline.judge_reproduction` (`R22.4b`'s own judge) rather than reusing the
run-id comparison. `--baseline`/`--kind` both select among *persisted runs* and mean nothing for
two reports, so either given alongside two files refuses rather than being silently ignored.
Naming exactly one of `--a`/`--b` a file refuses too — a baseline report is judged only against
another baseline report, never against a run id, because the two shapes answer different
questions. A file that fails to parse as a `BaselineReport` — `pydantic.ValidationError` —
becomes `NotABaselineReportError`, naming the path; a reproduction that fails — some published
metric's mean lands outside the interval its own repetitions spanned, or the later report never
measured it at all — becomes `BaselineNotReproducedError`, naming every metric that did not
reproduce. `weft_cli.render` is where a reader actually meets each verdict's text and exit code.

**`weft eval compare --kind <kind>` — task 11.12, `_metrics_comparison`'s restriction to one
class of question.** `09` §4 asks that a rung's claim about one class of question be a number
over that class, and a per-`kind` slice on `MetricAggregate` (`weft_eval.aggregate.
MetricAggregate.by_question_kind`, ledger task 11.12's other half) only becomes that claim once a
comparison can be asked for the slice instead of the mean. `metrics_comparison_for_kind` is
`_metrics_comparison` with one more parameter: `kind=None` returns exactly what `_metrics_
comparison` already returns; a named `kind` replaces each side's `Produced[MetricAggregate]`
with one restricted to that kind's own slice — same `reported_name`, `mean`/`n`/`stdev` taken
from the slice — and a side that never recorded that kind (no `--questions` scored it, or its
`by_question_kind` simply has no entry for it) becomes `_NOT_MEASURED`, the identical value a
side that never scored a metric at all already gets. A `kind` **neither** run recorded raises
`UnknownQuestionKindError`, naming every kind either run actually did record — `01` requirement
5's rule, FF12's family — rather than reporting `0.0` for an empty subset nobody measured, the
deliberate divergence from the evaluation layer that contributed the idea (`weft_eval.aggregate`'s
own module docstring on `by_question_kind`, and `tests/unit/weft_eval/test_question_kind.py`'s
own module docstring, record the same divergence one layer down).

**Packaging is provenance, not identity — repair `R22.11`.** Which distributions were active, and
at which versions, is reported beside a comparison (`_packaging_differences`) and never refuses
it: 24 pairs of runs had been refused with a version bump as their only reason. Corpus,
digest basis, model versions and question set stay identity, the rule `R22.4b` set for published
baselines.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import ClassVar, Final, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from weft_cli.eval_scoring import score_pipeline
from weft_cli.ingest import SourceChange, content_hashes_of, corpus_documents, run_index_for
from weft_cli.installed_versions import active_distribution_versions
from weft_cli.pipeline_diff import PipelineDiff, diff_resolved
from weft_cli.route_ask import resolve_named_pipeline
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_embed import Embedder
from weft_embed.contract import EmbeddingModel, IdentifiedEmbedder
from weft_engine.registry_bootstrap import Dependencies
from weft_eval.aggregate import MetricAggregate, PartitionSlice
from weft_eval.baseline import (
    BaselineReport,
    Reproduction,
    judge_reproduction,
    load_baseline_report,
)
from weft_eval.corpus_manifest import load_manifest
from weft_eval.falsify import (
    DifferenceJudgement,
    PairedDifference,
    baseline_spreads,
    judge_differences,
    paired_differences,
)
from weft_eval.latency import LatencySummary, latency_summary
from weft_eval.offline import GateSubset, gate_subset, require_gate_safe
from weft_eval.pool import LoadedPool, PoolChunk
from weft_eval.question_set import Question, QuestionSetFormat, read_question_set
from weft_eval.run_record import (
    CorpusDigestBasis,
    CorpusIdentity,
    ExperimentRun,
    MetricRunResult,
    NotAggregated,
    PerQuestionScores,
    PerQuestionSeconds,
    QuestionSetDigestBasis,
    RoleTokens,
    RunDurations,
    RunRecord,
    ScoredQueryRung,
    build_run_record,
    corpus_identity,
    load_run_record,
    write_run_record,
)
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_kernel.runner import RunSummary
from weft_kernel.seam import aclose, wrap
from weft_llm.client import NullSink
from weft_llm.roles import LLMRoles

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
    "per-metric aggregates side by side — refuses if the two ran over a different corpus or "
    "model versions, rather than reporting a diff that is not apples to apples; a different "
    "active distribution set or distribution versions is reported beside it, never refused"
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
    (`weft_eval.run_record.corpus_identity`'s own hash-of-sorted-entries construction), so
    persisting one would not be a fact worth diffing against later — it would be a record
    that looks complete and measures nothing, which is the shape CLAUDE.md's "a silent
    fallback is worse than a failure" rule exists to refuse.
    """

    def __init__(self, message: str, *, path: str, pipeline: str) -> None:
        super().__init__(message)
        self.path = path
        self.pipeline = pipeline


class CorpusHasFailedSourcesError(WeftError):
    """An evaluation's index skipped sources an earlier run recorded `FAILED` — ledger 36.

    A skipped source has no nodes, while the run record's corpus identity still covers it, so
    the scores would be over a smaller corpus than the record names. Refused, naming the fix.
    """


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


class NotABaselineReportError(WeftError):
    """`weft eval compare` was given a file that does not parse as a `weft_eval.baseline.
    BaselineReport` — repair `R22.4d`. See the module docstring's own R22.4d paragraph.
    """


class BaselineNotReproducedError(WeftError):
    """`weft eval compare` judged one baseline report against another and at least one
    published metric fell outside the interval its own repetitions spanned — repair `R22.4d`.
    See the module docstring's own R22.4d paragraph.
    """


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


class NoBaselineRunsError(WeftError, UnresolvedNameError):
    """`weft eval compare --baseline <pipeline>` named a pipeline no persisted run under
    `DEFAULT_RUNS_DIR` ran.

    Fitness function 12's family, on `UnknownRunIdError`'s own footing one class up:
    `valid_options` is every distinct resolved-pipeline name any persisted run actually carries,
    sorted — task 8.8's own "list what does exist" rather than an empty refusal.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], baseline: str) -> None:
        super().__init__(message)
        self.valid_options = valid_options
        self.baseline = baseline


class UnknownQuestionKindError(WeftError, UnresolvedNameError):
    """`weft eval compare --kind <kind>` named a question kind neither compared run recorded.

    Fitness function 12's family, on `UnknownRunIdError`/`UnknownMetricNameError`'s own footing:
    `valid_options` is every kind either run's own `MetricAggregate.by_question_kind` actually
    carries, sorted — task 11.12's own "list what does exist" rather than the `0.0` the
    evaluation layer that contributed this idea reports for an empty subset (see the module
    docstring's own paragraph).
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], kind: str) -> None:
        super().__init__(message)
        self.valid_options = valid_options
        self.kind = kind


class UnknownSliceError(WeftError, UnresolvedNameError):
    """`weft eval compare --slice axis=value` named a slice neither compared run recorded.

    `UnknownQuestionKindError`'s twin, one level up — task 38.2 widens the restriction from
    `kind` alone to any declared axis. `valid_options` is every `f"{axis}={value}"` either run's
    own `MetricAggregate.by_axis` actually carries, plus every `f"kind={value}"` either run's own
    `by_question_kind` carries, sorted — the identical "list what does exist" rule
    `UnknownQuestionKindError` already keeps.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], slice: str) -> None:
        super().__init__(message)
        self.valid_options = valid_options
        self.slice = slice


class EvalRunArgs(BaseModel):
    """`weft eval run <path> <pipeline> [--corpus-name NAME]` — see the module docstring for
    why `pipeline` is a second required positional rather than `weft index`'s optional flag.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="directory to index")
    reuse_index: bool = Field(
        default=False,
        description=(
            "score against what is already stored instead of indexing first — the way to "
            "compare two query rungs against one index"
        ),
    )
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
            "a question directory or a single TOML question file (weft_eval.question_set's "
            "one model) — when given, this run also retrieves for every question and scores "
            "the gate-safe RetrievalMetric subset over the result, folding it into the "
            "persisted record's own 'metrics'. A JSON list of {query, relevant_documents} "
            "judgements is still read, converted at the boundary, and printed as deprecated — "
            "removed in weft-rag 3.0. Omitted, 'metrics' stays empty, the same honesty "
            "'model_versions' had before task 4.7 named its own gap."
        ),
    )
    manifest: str | None = Field(
        default=None,
        description=(
            "the corpus manifest whose ids the question set names its relevant_documents by — "
            "eval/questions/*.toml's own vocabulary. Each id resolves to that document's path, "
            "relative to the manifest's own directory, before ground truth is matched against "
            "what was actually staged. Ignored when --questions is not given."
        ),
    )
    top_k: int = Field(
        default=_DEFAULT_TOP_K,
        ge=1,
        description="how many passages to retrieve per question when --questions is given.",
    )
    query_pipeline: str | None = Field(
        default=None,
        description=(
            "ledger task 7.5: score retrieval through a named *query* rung — a pipeline "
            "resolved and run per question through 'weft_cli.route_ask.run_named_ask', "
            "rather than the plain vector top-k 'run_ask' otherwise uses — so a Retriever, "
            "Fuser, ContextPacker or Generator choice is the thing actually measured. "
            "Optional and distinct from 'pipeline': every baseline taken before this task "
            "named none, and those records must stay readable. Ignored when --questions is "
            "not given."
        ),
    )


class EvalCompareArgs(BaseModel):
    """`weft eval compare <a> <b> [--baseline <pipeline>]` — two run ids, `weft pipeline diff`'s
    own `<a> <b>` shape, plus task 8.8's own falsification flag.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: str = Field(
        description=(
            "a run id printed by 'weft eval run', or the path to a baseline report file "
            "('weft eval baseline' writes one; the release archive ships the published ones)."
        )
    )
    b: str = Field(
        description=(
            "a run id printed by 'weft eval run', or the path to a baseline report file "
            "('weft eval baseline' writes one; the release archive ships the published ones)."
        )
    )
    baseline: str | None = Field(
        default=None,
        description=(
            "the name of the pipeline whose persisted runs under 'runs/' are this baseline's "
            "own repetitions — more than one is needed, since a single run records no interval "
            "a later difference can be judged against. When given, every metric the baseline "
            "measured gets a verdict: whether --a and --b's own difference is outside the "
            "width the baseline's own repetitions spanned by doing nothing at all."
        ),
    )
    kind: str | None = Field(
        default=None,
        description=(
            "restrict metrics_comparison to one question kind's own slice (ledger task 11.12) "
            "instead of the whole-run mean — e.g. 'cross-document', 'definitional'. Refuses, "
            "naming every kind either run actually recorded, for a kind neither run did. "
            "Omitted, this compares the whole-run mean exactly as it always has. "
            "'--kind X' is '--slice kind=X' — the two are mutually exclusive."
        ),
    )
    slice: str | None = Field(
        default=None,
        description=(
            "restrict metrics_comparison to one declared axis' own slice (ledger task 38.2) — "
            "'axis=value', e.g. 'evidence=text-table', read from each run's own per-slice "
            "numbers. '--kind X' is the one case '--slice kind=X'; refuses, naming every "
            "axis=value pair either run actually recorded, for a slice neither run did. "
            "Omitted, this compares the whole-run mean exactly as it always has."
        ),
    )

    @model_validator(mode="after")
    def _slice_and_kind_are_exclusive(self) -> EvalCompareArgs:
        if self.slice is not None and self.kind is not None:
            raise ValueError(
                "--kind and --slice both given — '--kind X' is '--slice kind=X', so pass "
                "exactly one of --kind or --slice, never both."
            )
        return self


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
    #: Task **38.11** — the question set's own shape, when `--questions` was given: `render`'s
    #: cue to print a deprecation notice for a JSON `--questions` file. `None` for a run given
    #: no `--questions` at all.
    question_set_format: QuestionSetFormat | None = None


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


def _recorded_kinds(a: RunRecord, b: RunRecord) -> frozenset[str]:
    """Every question kind either run's own metrics actually recorded a slice for."""
    kinds: set[str] = set()
    for record in (a, b):
        for result in record.metrics.values():
            if isinstance(result, Produced):
                kinds.update(result.value.by_question_kind)
    return frozenset(kinds)


def _restricted_to_kind(result: MetricRunResult | None, *, kind: str) -> MetricRunResult:
    """`result`, restricted to `kind`'s own slice — see the module docstring's own `--kind`
    paragraph. `_NOT_MEASURED` for a result this run never produced, or whose `by_question_kind`
    carries no entry for `kind` — the identical value a metric a run never scored at all gets.
    """
    if not isinstance(result, Produced):
        return _NOT_MEASURED
    slice_: PartitionSlice | None = result.value.by_question_kind.get(kind)
    if slice_ is None:
        return _NOT_MEASURED
    return Produced(
        value=MetricAggregate(
            reported_name=result.value.reported_name,
            mean=slice_.mean,
            n=slice_.n,
            stdev=slice_.stdev,
            excluded=0,
            nothing_to_produce=0,
            kind=result.value.kind,
        )
    )


def metrics_comparison_for_kind(
    a: RunRecord, b: RunRecord, *, kind: str | None
) -> Mapping[str, MetricComparison]:
    """`_metrics_comparison(a, b)`, restricted to one question `kind`'s own slice — see the
    module docstring's own `--kind` paragraph.

    `kind=None` returns exactly `_metrics_comparison(a, b)`. A named `kind` replaces each side's
    `Produced[MetricAggregate]` with one restricted to that kind's own slice (see `_restricted_
    to_kind`); a `kind` **neither** run recorded for **any** metric raises
    `UnknownQuestionKindError` rather than comparing two `0.0`s nobody measured.
    """
    if kind is None:
        return _metrics_comparison(a, b)

    recorded = _recorded_kinds(a, b)
    if kind not in recorded:
        options = tuple(sorted(recorded))
        raise UnknownQuestionKindError(
            f"'{kind}' is not a question kind either run recorded. Kinds recorded: "
            f"{', '.join(options) or '(none)'}.",
            valid_options=options,
            kind=kind,
        )

    names = sorted(set(a.metrics) | set(b.metrics))
    return {
        name: MetricComparison(
            a=_restricted_to_kind(a.metrics.get(name), kind=kind),
            b=_restricted_to_kind(b.metrics.get(name), kind=kind),
        )
        for name in names
    }


def _recorded_slices(a: RunRecord, b: RunRecord) -> frozenset[str]:
    """Every `axis=value` and `kind=value` pair either run's own metrics actually recorded a
    slice for — `metrics_comparison_for_slice`'s own "list what does exist", `_recorded_kinds`
    widened from `kind` alone to any declared axis (task 38.2).
    """
    slices: set[str] = set()
    for record in (a, b):
        for result in record.metrics.values():
            if isinstance(result, Produced):
                for axis, values in result.value.by_axis.items():
                    slices.update(f"{axis}={value}" for value in values)
                slices.update(f"kind={kind}" for kind in result.value.by_question_kind)
    return frozenset(slices)


def _restricted_to_axis(
    result: MetricRunResult | None, *, axis: str, value: str
) -> MetricRunResult:
    """`result`, restricted to `axis=value`'s own slice — `_restricted_to_kind`'s twin, shaped
    identically (task 38.2). `_NOT_MEASURED` for a result this run never produced, or whose
    `by_axis` carries no entry for `axis`, or whose `by_axis[axis]` carries no entry for `value`
    — the identical value a metric a run never scored at all gets.
    """
    if not isinstance(result, Produced):
        return _NOT_MEASURED
    slice_: PartitionSlice | None = result.value.by_axis.get(axis, {}).get(value)
    if slice_ is None:
        return _NOT_MEASURED
    return Produced(
        value=MetricAggregate(
            reported_name=result.value.reported_name,
            mean=slice_.mean,
            n=slice_.n,
            stdev=slice_.stdev,
            excluded=0,
            nothing_to_produce=0,
            kind=result.value.kind,
        )
    )


def metrics_comparison_for_slice(
    a: RunRecord, b: RunRecord, *, slice_: str | None
) -> Mapping[str, MetricComparison]:
    """`_metrics_comparison(a, b)`, restricted to one declared axis' own slice — task 38.2,
    `metrics_comparison_for_kind`'s widening from `kind` alone to any axis `weft_eval.harness`
    now slices.

    `slice_=None` returns exactly `_metrics_comparison(a, b)`. A `kind=<value>` request whose
    value either run actually recorded in `by_question_kind` restricts through the existing
    `_restricted_to_kind` — the identical result `metrics_comparison_for_kind` already gives
    `--kind`, since `--kind X` is `--slice kind=X`. Any other `axis=value` request restricts
    through `_restricted_to_axis`. A slice **neither** run recorded for **any** metric — including
    a string with no `=` — raises `UnknownSliceError` naming every `axis=value` pair that is
    there, rather than comparing two absent numbers.
    """
    if slice_ is None:
        return _metrics_comparison(a, b)

    recorded = _recorded_slices(a, b)
    if slice_ not in recorded:
        options = tuple(sorted(recorded))
        raise UnknownSliceError(
            f"'{slice_}' is not a slice either run recorded. Slices recorded: "
            f"{', '.join(options) or '(none)'}.",
            valid_options=options,
            slice=slice_,
        )

    axis, _, value = slice_.partition("=")
    names = sorted(set(a.metrics) | set(b.metrics))
    if axis == "kind" and value in _recorded_kinds(a, b):
        return {
            name: MetricComparison(
                a=_restricted_to_kind(a.metrics.get(name), kind=value),
                b=_restricted_to_kind(b.metrics.get(name), kind=value),
            )
            for name in names
        }

    return {
        name: MetricComparison(
            a=_restricted_to_axis(a.metrics.get(name), axis=axis, value=value),
            b=_restricted_to_axis(b.metrics.get(name), axis=axis, value=value),
        )
        for name in names
    }


def _slice_axis_value(*, kind: str | None, slice_: str | None) -> str | None:
    """`--kind X` is `--slice kind=X` — the one string either flag reduces to, or `None` when
    neither was given — repair R38.1's own footing for restricting a paired difference the
    identical way `metrics_comparison_for_kind`/`metrics_comparison_for_slice` already restrict
    the metrics comparison.
    """
    if kind is not None:
        return f"kind={kind}"
    return slice_


def _keys_matching(
    axes: Mapping[str, Mapping[str, str]], *, axis: str, value: str
) -> frozenset[str]:
    """Every question key whose recorded axes carry `axis == value`."""
    return frozenset(key for key, recorded in axes.items() if recorded.get(axis) == value)


def paired_differences_for_slice(
    a: RunRecord, b: RunRecord, *, kind: str | None, slice_: str | None
) -> tuple[Mapping[str, PairedDifference], str | None, str | None]:
    """`weft_eval.falsify.paired_differences(a, b)`, restricted to one slice's own questions —
    repair R38.1, `metrics_comparison_for_slice`'s own restriction applied to the paired
    difference rather than the mean.

    Returns `(paired, slice_label, reason)`. `slice_label` is `"axis=value"` whenever
    `--slice`/`--kind` was given, so the renderer's header can say which slice it paired over,
    whether or not pairing actually ran; `reason` is populated only when a slice was asked for
    and either record predates this repair (`question_axes is None`) — pairing is then not
    computable, and `paired` is `{}` rather than silently pairing the whole run under a slice's
    own header. With neither `--slice` nor `--kind`, this is exactly `paired_differences(a, b)`,
    `None`, `None` — today's behaviour, unchanged.
    """
    axis_value = _slice_axis_value(kind=kind, slice_=slice_)
    if axis_value is None:
        return paired_differences(a, b), None, None

    if a.question_axes is None or b.question_axes is None:
        reason = (
            f"not paired over {axis_value}: a record written before repair R38.1 does not say "
            "which questions were in that slice"
        )
        return {}, axis_value, reason

    axis, _, value = axis_value.partition("=")
    question_keys = _keys_matching(a.question_axes, axis=axis, value=value) & _keys_matching(
        b.question_axes, axis=axis, value=value
    )
    return paired_differences(a, b, question_keys=question_keys), axis_value, None


class BaselineSelection(StrEnum):
    """Which rule chose a baseline's repetitions — printed, because a reader of a verdict
    cannot otherwise tell a rung-matched spread from a pipeline-matched one.
    """

    INGEST_AND_QUERY_RUNG = "ingest-pipeline-and-query-rung"
    INGEST_PIPELINE_ONLY = "ingest-pipeline-only"


class QueryRungDifference(BaseModel):
    """The query rung each of two compared runs scored with. A *difference*, never a reason to
    refuse: the rung is the thing being compared, so it does not join `_incomparable_reasons`
    the way the corpus does.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: ScoredQueryRung | None
    b: ScoredQueryRung | None


class EvalCompareCommandResult(CommandResult):
    """`weft eval compare`'s whole answer, once both runs pass the apples-to-apples check —
    a refusal is raised before this is ever constructed, see `IncomparableRunsError`.

    `metrics_comparison` is task 4.9's own addition — see `_metrics_comparison`. `baseline_pipeline`
    /`baseline_runs`/`falsification` are task 8.8's own addition — all three default so every
    existing construction site keeps working; `falsification` stays `None` unless `--baseline`
    was given, so "no verdict was asked for" and "a verdict was reached" are never confused.
    `query_rungs`/`baseline_selection` are task 16.1's own addition, defaulted for the identical
    reason: `query_rungs` is always constructed by `EvalCompareCommand.run`, but a construction
    site outside it (a test, a future caller) must not be forced to supply a fact it may not
    have; `baseline_selection` stays `None` unless `--baseline` was given, the same posture
    `falsification` already takes.

    `paired_differences` is task 16.9's own addition, **beside** `falsification` rather than in
    place of it — the two answer different questions (does the difference exceed this system's
    own repetition noise, and does it generalise across the questions) and a reader given one
    cannot infer the other. Unlike `falsification` it needs no flag to ask for it: it is
    computed from what `--a`/`--b` already carry, so `EvalCompareCommand.run` always fills it,
    and `{}` — the plain default, never `None` — is the honest answer for two records that
    carry no per-question scores to pair (every record written before task 16.4).

    `reproduction` is repair `R22.4d`'s own addition, defaulted like every field above: `None`
    for the ordinary two-run-id comparison, and `weft_eval.baseline.judge_reproduction`'s own
    answer when `--a`/`--b` both named a baseline report file instead. Every other field on this
    result keeps its plain, non-report meaning in that case — `corpus_matches`/`model_versions_
    match` are `True` by construction (`judge_reproduction` refuses rather than returning a
    `Reproduction` when they do not agree), `active_distributions_match` is the one fact that
    can genuinely differ between two reports and still reproduce (G19 renamed every distribution,
    so a published baseline and a re-run naming the wheel it moved into are exactly the case this
    field exists to say "differs, and reproduced anyway"), and `metrics_comparison` is `{}`
    because the per-metric verdicts already live on `reproduction`.

    `packaging_differences` is repair `R22.11`'s own addition: every fact `_packaging_
    differences` found between the two runs, reported beside the comparison rather than a
    reason to refuse it — `()` for two runs packaged identically, the plain default so every
    existing construction site keeps working.
    """

    run_a: str
    run_b: str
    corpus_matches: bool
    model_versions_match: bool
    active_distributions_match: bool
    pipeline_diff: PipelineDiff
    metrics_comparison: Mapping[str, MetricComparison]
    baseline_pipeline: str | None = None
    baseline_runs: tuple[str, ...] = ()
    falsification: Mapping[str, DifferenceJudgement] | None = None
    query_rungs: QueryRungDifference | None = None
    baseline_selection: BaselineSelection | None = None
    paired_differences: Mapping[str, PairedDifference] = {}
    #: Repair **R38.1** — `"axis=value"`, set whenever `--slice`/`--kind` restricted
    #: `paired_differences`, so the renderer's header can say which slice it paired over.
    #: `None` for an unrestricted comparison, the plain default every existing site keeps.
    paired_differences_slice: str | None = None
    #: Repair **R38.1** — why `paired_differences` is `{}` under a slice: `None` unless
    #: `--slice`/`--kind` was given and at least one of the two records predates this repair
    #: (`question_axes is None`), in which case pairing that record's questions to a slice is
    #: not computable and this says so rather than silently pairing the whole run instead.
    paired_differences_reason: str | None = None
    reproduction: Reproduction | None = None
    packaging_differences: tuple[str, ...] = ()
    #: Task 33.8 — each run's query latency; `None` when its record has no per-question timing.
    latency_a: LatencySummary | None = None
    latency_b: LatencySummary | None = None


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


def all_run_records(directory: Path = DEFAULT_RUNS_DIR) -> tuple[tuple[str, RunRecord], ...]:
    """Every run id and the `RunRecord` it holds, under `directory` — sorted by run id.

    Task 8.8's own reader: `weft eval compare --baseline` finds a baseline's repetitions among
    exactly the ordinary runs `weft eval run` already writes, no second file format.

    **Public since carried repair R11.2, when a second caller arrived** — `weft_cli.
    capability_siblings`' own precedent, for the identical reason. `weft index` now persists a
    run record of its own, and it must never be selectable as a baseline repetition: it
    measures nothing, so `metrics` is `{}` and `weft_eval.falsify.baseline_spreads` would have
    no spread to read. The check that it is invisible has to ask *this* function which runs
    `weft eval compare` considers; a second `*.json` glob written beside it could come to
    disagree, and the check would then be reporting on the wrong set.
    """
    if not directory.is_dir():
        return ()
    return tuple((path.stem, load_run_record(path)) for path in sorted(directory.glob("*.json")))


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


def document_labels_from_manifest(manifest: str | None) -> Mapping[str, str] | None:
    """`--manifest`'s own id-to-label mapping, or `None` when it was not given — task **38.11**.

    Each manifest document's own `path` is resolved (`weft_eval.corpus_manifest.load_manifest`
    resolves it against the manifest's own directory); this reduces it back to a path relative
    to that same directory, `.as_posix()`, so it is exactly the corpus-relative label
    `weft_cli.eval_scoring.resolve_labels` has always matched against — the identical shape
    `eval/questions/*.toml`'s hand-written `relevant_documents` labels already take.

    **Public since task 38.0** — `weft_cli.eval_experiment.EvalExperimentCommand` needed the
    identical id-to-label mapping for an experiment document's own `manifest =` line, and a
    second, copied reader would have been the exact "two lists" failure this pack's own module
    docstrings keep warning against.
    """
    if manifest is None:
        return None
    manifest_path = Path(manifest)
    manifest_root = manifest_path.resolve().parent
    return {
        document.id: document.path.relative_to(manifest_root).as_posix()
        for document in load_manifest(manifest_path).documents
    }


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


#: `model_versions_of`' default when no caller supplies one — a run with no `[llm.roles]` block
#: contributes no role entries, which is a fact rather than an omission. Module-level so the
#: default is one shared instance rather than a mutable built per call.
_NO_ROLES: Final[LLMRoles] = LLMRoles()

#: `model_versions_of`'s other default — a caller that never asked an embedder what it actually
#: calls keeps this function's pre-`R34.0` reading, `_model_field` off the resolved config.
_NO_STATED: Final[Mapping[str, str]] = {}


def model_versions_of(
    resolved_pipeline: ResolvedPipeline,
    *,
    roles: LLMRoles = _NO_ROLES,
    stated: Mapping[str, str] = _NO_STATED,
) -> Mapping[str, str]:
    """Every model this run actually used — **three sources, carried repairs `R10.3`, `R34.0`.**

    *Stage config*, the original reading: every stage of `resolved_pipeline` whose own config
    names a `model`, as `use:model`. Never reads `[services]` (Q3, task 4.0) and never a table
    of "which stages carry a model" — `hash`, `pgvector` and every plugin whose `config_model`
    has no `model` field simply contribute nothing, derived rather than special-cased.

    *`stated`*, and this is what `R34.0` adds — `stated_embedding_models`'s own return shape, a
    stage id mapped to what the embedder itself said it calls. Found at ledger `34.0`: this
    function used to read `config.model` for every stage, which resolution fills with a
    plugin's own default for a stage that names none — `OpenAIEmbedderConfig.model` defaults to
    `text-embedding-3-small` — while `OpenAIEmbedder` actually calls `[packs.<account>]
    embedding_model` in exactly that case (`R22.1`). A run configured to call `-3-large`
    through the account setting recorded `-3-small`, and two runs differing only in that
    setting compared as though nothing but the pipeline differed — `L10.5`'s shape a second
    time, this time between a run and itself. A stage id present in `stated` wins over its own
    config reading; a stage id absent from it (an embedder that could not state one, or no
    `stated` mapping at all) falls back to the config reading unchanged.

    *`[llm.roles]`*, `R10.3`'s own addition. A summarising or judging model is chosen per
    **role**, and no stage's config mentions it — so two eval arms differing *only* by their
    summarising model produced byte-identical `model_versions` and `_incomparable_reasons` compared
    them as though the only difference were the pipeline (`docs/internal/lessons.md` `L10.5`). That
    is the guard reading one fact and the run using another, and `09` §4's V2 pins a comparison to
    *"a different corpus, pipeline or model version"* — a role's model **is** a model version.

    **The two key spaces cannot collide**, which is why one dictionary is honest here. A stage
    entry is keyed by the stage's own id; a role entry is keyed `role:<name>`, and a stage id
    carrying a `:` is a slot qualifier whose left side is a *distribution*, never the literal
    `role`. The test asserts the disjointness rather than resting on that sentence.
    """
    versions: dict[str, str] = {}
    stage: ResolvedStage
    for stage in resolved_pipeline.stages:
        if stage.id in stated:
            versions[stage.id] = f"{stage.use}:{stated[stage.id]}"
            continue
        model = _model_field(stage.config)
        if model is not None:
            versions[stage.id] = f"{stage.use}:{model}"
    for name, mapping in sorted(roles.roles.items()):
        if mapping.model:
            versions[f"role:{name}"] = f"{mapping.provider}:{mapping.model}"
    return versions


async def _asked_identity(embedder: IdentifiedEmbedder) -> Outcome[EmbeddingModel]:
    """`embedder.embedding_model()`, `Outcome`-shaped so `weft_kernel.seam.wrap` can carry it —
    a standalone function rather than a call inline in `stated_embedding_models`, so the plugin
    instance built there is never the one an awaited method is called on in the same function
    (fitness function 33(b): every such call is handed to `wrap`).
    """
    return Produced(value=await embedder.embedding_model())


async def stated_embedding_models(
    resolved_pipeline: ResolvedPipeline, registry: Registry
) -> Mapping[str, str]:
    """Every embed stage's own stated model — `model_versions_of`'s `stated` argument.

    Built fresh, one instance per embed stage, from the resolved stage's own `use` and
    `config` — the identical construction `Runner.resolve` performs, run here only to ask
    `weft_embed.contract.IdentifiedEmbedder.embedding_model()`, never to run the stage. A
    stage not registered under the `Embedder` contract, or whose plugin does not satisfy
    `IdentifiedEmbedder`, contributes nothing — `model_versions_of` falls back to its config
    reading for exactly that stage id.
    """
    stated: dict[str, str] = {}
    stage: ResolvedStage
    for stage in resolved_pipeline.stages:
        if stage.contract != "Embedder":
            continue
        entry = registry.entry(Embedder, stage.use)
        instance = entry.factory(stage.config)
        try:
            if isinstance(instance, IdentifiedEmbedder):
                wrapped = wrap(
                    partial(_asked_identity, instance),
                    distribution=entry.distribution,
                    contract="Embedder",
                    plugin=stage.use,
                    stage=stage.id,
                )
                outcome = await wrapped()
                stated[stage.id] = cast(Produced[EmbeddingModel], outcome).value.model
        finally:
            await aclose(
                instance,
                distribution=entry.distribution,
                contract="Embedder",
                plugin=stage.use,
                stage=stage.id,
            )
    return stated


def _incomparable_reasons(a: RunRecord, b: RunRecord) -> tuple[str, ...]:
    """Which of the identity facts a comparison depends on actually differ — see
    `IncomparableRunsError`'s own docstring. Empty means the two runs are comparable.

    **Packaging — which distributions were active, and at which versions — is not identity,
    repair `R22.11`.** It moved to `_packaging_differences`, reported beside a comparison
    rather than refusing it: see that function's own docstring and the module docstring's
    R22.11 paragraph.
    """
    reasons: list[str] = []
    if a.corpus != b.corpus:
        reasons.append(
            f"corpus differs ('{a.corpus.name}' {a.corpus.digest[:12]}… vs "
            f"'{b.corpus.name}' {b.corpus.digest[:12]}…)"
        )
    if a.corpus_digest_basis != b.corpus_digest_basis:
        reasons.append(
            f"corpus digests are not over the same thing ({_basis_of(a)} vs {_basis_of(b)}) — a "
            f"record that names no basis was written before ledger task 16.0, when the digest "
            f"was over each document's resolved path rather than its bytes, so these two "
            f"digests cannot be compared even over a corpus that never changed"
        )
    if a.model_versions != b.model_versions:
        reasons.append(
            f"model versions differ ({dict(a.model_versions)} vs {dict(b.model_versions)})"
        )
    if a.question_set_digest is not None and b.question_set_digest is not None:
        if a.question_set_digest_basis != b.question_set_digest_basis:
            reasons.append(
                "question set digests are not over the same thing "
                f"({_question_set_basis_of(a)} vs {_question_set_basis_of(b)}) — task 38.11 "
                f"moved the digest from `weft_cli.eval_scoring.Question`'s canonical form to "
                f"`weft_eval.question_set.Question`'s, so the same questions digest "
                f"differently either side of that boundary and the two numbers cannot be "
                f"compared even over a set that never changed"
            )
        elif a.question_set_digest != b.question_set_digest:
            reasons.append(
                f"question set differs ({a.question_set_digest[:12]}… vs "
                f"{b.question_set_digest[:12]}…) — a metric delta between two runs scored on two "
                f"sets of questions is a fact about the questions, not about the pipelines"
            )
    return tuple(reasons)


def _packaging_differences(a: RunRecord, b: RunRecord) -> tuple[str, ...]:
    """Which distributions were active, and at which versions, differ between `a` and `b` —
    repair `R22.11`. Reported beside a comparison, never a reason to refuse it: see the module
    docstring's own R22.11 paragraph. Empty means packaging did not move.
    """
    differences: list[str] = []
    if a.active_distributions != b.active_distributions:
        differences.append(
            f"active distributions differ ({a.active_distributions} vs {b.active_distributions})"
        )
    if (
        a.distribution_versions is not None
        and b.distribution_versions is not None
        and a.distribution_versions != b.distribution_versions
    ):
        differences.append(
            f"distribution versions differ ({dict(a.distribution_versions)} vs "
            f"{dict(b.distribution_versions)})"
        )
    return tuple(differences)


def _basis_of(record: RunRecord) -> str:
    """`corpus_digest_basis` as a reader of a run record should see it — *not recorded* rather
    than `None`, because absence is the honest answer for every record written before 16.0.
    """
    basis = record.corpus_digest_basis
    return basis.value if basis is not None else "not recorded"


def _question_set_basis_of(record: RunRecord) -> str:
    """`question_set_digest_basis` as a reader of a run record should see it — *not recorded*
    rather than `None`, because absence is the honest answer for every record written before
    task 38.11 (`RunRecord.question_set_digest_basis`'s own docstring).
    """
    basis = record.question_set_digest_basis
    return basis.value if basis is not None else "not recorded"


@dataclass(frozen=True)
class IndexAndScoreResult:
    """What `index_and_score` produced — every fact `EvalRunCommand`/`EvalExperimentCommand`
    (task **38.0**) need to build their own result, from the one path both now index a corpus
    and score a question set through. `wall_clock_seconds` is the identical measurement that
    went onto `record.durations.ingest_seconds`, carried here too rather than read back off the
    record a second time — `L7.4`: two reads of one quantity agree until they do not.
    """

    run_id: str
    record: RunRecord
    summary: RunSummary
    stored_count: int | None
    wall_clock_seconds: float
    #: Task **40.2** — every packed chunk `score_pipeline` retrieved for each question, in
    #: ranking order, when `capture_pool=True` was passed through. `None` otherwise.
    question_pools: Mapping[str, tuple[PoolChunk, ...]] | None = None
    #: Task **40.2** — the store's own row count at capture time. `None` when not capturing.
    store_rows: int | None = None
    #: Task **40.2** (second half) — every corpus document id this run's questions were scored
    #: against, whichever of the three branches produced it (a fresh index, `--reuse-index`, or a
    #: pool replay's own manifest) — what `_write_arm_pool` needs to fill `PoolManifest.
    #: document_ids` without re-deriving it a second way.
    document_ids: tuple[str, ...] = ()


async def index_and_score(
    deps: Dependencies,
    *,
    ctx: Context,
    path: Path,
    pipeline: str,
    corpus_name: str | None,
    questions: tuple[Question, ...] | None,
    document_labels: Mapping[str, str] | None,
    top_k: int,
    query_pipeline: str | None,
    reuse_index: bool,
    refuse_foreign_documents: bool = False,
    experiment: ExperimentRun | None = None,
    reprocess: bool = True,
    batch_size: int | None = None,
    cutoffs: tuple[int, ...] | None = None,
    capture_pool: bool = False,
    pool: LoadedPool | None = None,
) -> IndexAndScoreResult:
    """Index `path` under `pipeline` — or, with `reuse_index`, score what is already stored — and,
    with `questions` given, score them through `score_pipeline`. This is task **38.0**'s own
    extraction: `EvalRunCommand.run` used to do this inline, twice (once per `reuse_index`
    branch); `EvalExperimentCommand` (`weft_cli.eval_experiment`) needed the identical path so an
    experiment's own scoring could never silently diverge from `weft eval run`'s, so it is a
    module-level function both call rather than one calling a method on the other.

    `score_pipeline` is called through this module's own global name — never a captured
    reference — so a caller that monkeypatches `weft_cli.eval_commands.score_pipeline`
    (`test_eval_commands.py`'s own convention) still reaches this function's call, on both the
    `weft eval run` and the `weft eval experiment` path.

    **`reuse_index` — carried repair `R10.4`.** Score against what is already stored, rather than
    indexing again: comparing two *query* rungs against one corpus otherwise means re-ingesting
    each time, harmless for a deterministic ingest rung and not at all harmless for one that calls
    a model (`L11.46` measured a corpus grow from 23 nodes to 42 across four such runs, turning a
    baseline *interval* into extraction drift). The corpus identity still comes from `corpus_
    identity` over each discovered document's own bytes (`corpus_documents`, task 16.0), so
    discovering them without ingesting yields the identical digest a real index would have —
    reading ids back out of the store instead would make the record depend on whatever a previous
    run happened to write. The ingest pipeline is still resolved and still recorded: a query-rung
    comparison needs a stated ingest rung even when this call did not itself index anything.
    `wall_clock_seconds`/`durations.ingest_seconds` are both `0.0` on this branch, a measurement
    rather than a placeholder — this call spent no time ingesting.

    Mints a fresh `uuid4` run id and writes the record to `DEFAULT_RUNS_DIR/<run_id>.json` before
    returning — the two steps `EvalRunCommand.run` always performed, now performed once.

    **`reprocess`/`batch_size` — repair R38.2.** `EvalRunCommand` still calls this with neither
    named, so `reprocess` defaults `True` and every document is re-embedded on `weft eval run`'s
    own wall-clock-timed path, unchanged. `weft_cli.eval_experiment` is the caller that passes
    both explicitly: `reprocess=False` the one time it indexes a given pipeline and corpus, so a
    document an operator already indexed is skipped rather than re-embedded at real API cost, and
    `batch_size` from the experiment document's own `index_batch_size`, so the corpus is not held
    in memory as one batch.

    `cutoffs` — ledger task 40.1 — is passed straight through to `score_pipeline`'s own keyword
    of the same name; `None` (every call site before this task, including `weft eval run`'s) is
    unchanged. `weft_cli.eval_experiment` is the one caller that passes an experiment's own
    declared `Experiment.cutoffs`.

    `capture_pool` — ledger task 40.2 — is passed straight through to `score_pipeline`'s own
    keyword of the same name; `False` (every call site before this task) is unchanged.
    `IndexAndScoreResult.question_pools`/`store_rows` carry whatever `score_pipeline` returned
    for them, `None` when `questions` is `None` or `capture_pool` is `False`.

    `pool` — ledger task 40.2's second half. `None` (every call site before this task) is
    unchanged. Given a `LoadedPool` instead, this indexes nothing and reads no corpus at all —
    no `run_index_for`, no `corpus_documents` — the ingest pipeline is resolved by name alone
    (`weft_cli.route_ask.resolve_named_pipeline`, the identical public resolution `corpus_
    documents` itself calls one layer down) purely so `PipelineNotRetrievableError`'s own check
    and `model_versions_of` have something to read, `document_ids` is `pool.manifest.
    document_ids`, and the record's own `corpus` is built directly from `pool.manifest.
    corpus_digest` rather than digested from documents this call never touched.
    `stored_count` is `None` and `ingest_seconds` is `0.0`, `--reuse-index`'s own honest
    measurement one branch up: this call spent no time reading a corpus either.
    `score_pipeline` is called with `pool=pool`, which replays every question through the
    manifest's own captured chunks rather than retrieving again.
    """
    resolved: ResolvedPipeline
    document_ids: tuple[str, ...]
    content_hashes: tuple[str, ...]
    summary: RunSummary
    stored_count: int | None
    ingest_seconds: float

    if pool is not None:
        resolved = resolve_named_pipeline(
            pipeline,
            registry=deps.registry,
            reports=deps.reports,
            contributions=deps.contributions,
        )
        document_ids = pool.manifest.document_ids
        content_hashes = ()
        summary = RunSummary()
        stored_count = None
        ingest_seconds = 0.0
    elif reuse_index:
        resolved, _specs, documents = corpus_documents(
            path,
            pipeline=pipeline,
            registry=deps.registry,
            reports=deps.reports,
            contributions=deps.contributions,
        )
        del _specs
        document_ids = tuple(str(doc.source_id) for doc in documents)
        if not document_ids:
            raise EmptyCorpusError(
                f"'{path}' holds nothing pipeline '{pipeline}' can read, so there is no corpus "
                f"identity for a run record to carry and nothing for a query rung to retrieve. "
                f"--reuse-index scores against a corpus that is already stored; point --path at "
                f"the directory that was indexed.",
                path=str(path),
                pipeline=pipeline,
            )
        content_hashes = content_hashes_of(documents)
        summary = RunSummary()
        stored_count = None
        ingest_seconds = 0.0
    else:
        # Task 4.7, V5's wall-clock half: measured around the real work, never estimated.
        started = time.monotonic()
        result = await run_index_for(
            deps,
            path,
            ctx=ctx,
            pipeline=pipeline,
            # `--reuse-index` is how a caller says *do not ingest*, and it says so in the
            # record; a wall-clock-timed run must not silently skip an unchanged document and
            # be compared against one that did the whole job (ledger task 17.0). An experiment
            # indexing one pipeline and corpus for the first time passes `reprocess=False`
            # instead, so an index an operator already built is honoured rather than redone.
            reprocess=reprocess,
            batch_size=batch_size,
            retry_failed=False,
        )
        ingest_seconds = time.monotonic() - started
        if not result.document_ids:
            raise EmptyCorpusError(
                f"'{path}' produced nothing to index under pipeline '{pipeline}' — there is "
                f"nothing for a run record to carry a corpus identity over. Point --path at a "
                f"directory pipeline '{pipeline}' can actually read.",
                path=str(path),
                pipeline=pipeline,
            )
        skipped = sorted(
            source
            for source, change in result.source_changes.items()
            if change is SourceChange.FAILED
        )
        if skipped:
            raise CorpusHasFailedSourcesError(
                f"{len(skipped)} source(s) under '{path}' were recorded failed by an earlier "
                f"index and were skipped, so this run would score a smaller corpus than its record "
                f"names (first: {skipped[0]}). Run `weft index --retry-failed` over it first, or "
                "remove them with `weft delete`."
            )
        # `run_index` always sets `resolved_pipeline` on the `pipeline=` path — see
        # `weft_cli.ingest.IndexResult`'s own docstring — and `pipeline` is required above.
        resolved = cast(ResolvedPipeline, result.resolved_pipeline)
        document_ids = result.document_ids
        content_hashes = result.content_hashes
        summary = result.summary
        stored_count = result.stored_count

    # Task 4.9's own gap to fill — see the module docstring's paragraph on `--questions`.
    # `{}` with no questions, the same honesty `model_versions` had before task 4.7.
    # Task 10.22: timed separately from ingest above, on the same clock, so a rebuild's cost
    # and a scoring run's cost never collapse into one number — see `RunDurations`'s own
    # docstring for why that split is what G15's *Remove* face actually needs.
    query_started = time.monotonic()
    metrics: Mapping[str, Outcome[MetricAggregate]] = {}
    query_rung: ScoredQueryRung | None = None
    question_scores: Mapping[str, PerQuestionScores] | None = None
    question_axes: Mapping[str, Mapping[str, str]] | None = None
    question_contributors: Mapping[str, tuple[str, ...]] | None = None
    question_set: str | None = None
    question_set_basis: QuestionSetDigestBasis | None = None
    question_seconds: PerQuestionSeconds | None = None
    token_usage: Mapping[str, RoleTokens] | None = None
    question_pools: Mapping[str, tuple[PoolChunk, ...]] | None = None
    result_store_rows: int | None = None
    if questions is not None:
        scored = await score_pipeline(
            registry=deps.registry,
            resolved_pipeline=resolved,
            questions=questions,
            top_k=top_k,
            cutoffs=cutoffs,
            ctx=ctx,
            corpus_document_ids=document_ids,
            query_pipeline=query_pipeline,
            reports=deps.reports,
            llm=deps.llm,
            services=deps.services,
            roles=deps.roles,
            # Not `deps.token_sink`: that prints to stdout (R33.0). Usage is recorded either way.
            sink=NullSink(),
            contributions=deps.contributions,
            document_labels=document_labels,
            refuse_foreign_documents=refuse_foreign_documents,
            capture_pool=capture_pool,
            pool=pool,
        )
        metrics = scored.metrics
        query_rung = scored.query_rung
        question_scores = scored.question_scores
        question_axes = scored.question_axes
        question_contributors = scored.question_contributors
        question_set = scored.question_set or None
        question_set_basis = (
            QuestionSetDigestBasis.QUESTION_SET if question_set is not None else None
        )
        question_seconds = scored.question_seconds
        token_usage = scored.token_usage
        question_pools = scored.question_pools
        result_store_rows = scored.store_rows
    query_seconds = time.monotonic() - query_started

    resolved_corpus_name = corpus_name if corpus_name is not None else str(path)
    corpus = (
        CorpusIdentity(name=resolved_corpus_name, digest=pool.manifest.corpus_digest)
        if pool is not None
        else corpus_identity(resolved_corpus_name, content_hashes)
    )
    record = build_run_record(
        recorded_at=datetime.now(UTC).isoformat(),
        resolved_pipeline=resolved,
        corpus=corpus,
        corpus_digest_basis=CorpusDigestBasis.DOCUMENT_BYTES,
        query_rung=query_rung,
        # Task 4.7's own gap to fill — see the module docstring's paragraph on
        # `model_versions_of`. Derived from what actually ran, never from `[services]`.
        model_versions=model_versions_of(
            resolved,
            roles=deps.llm.roles,
            stated=await stated_embedding_models(resolved, deps.registry),
        ),
        reports=deps.reports,
        distribution_versions=active_distribution_versions(deps.reports),
        metrics=metrics,
        durations=RunDurations(ingest_seconds=ingest_seconds, query_seconds=query_seconds),
        question_scores=question_scores,
        question_axes=question_axes,
        question_contributors=question_contributors,
        question_set_digest=question_set,
        question_set_digest_basis=question_set_basis,
        question_seconds=question_seconds,
        token_usage=token_usage,
        experiment=experiment,
    )
    run_id = str(uuid.uuid4())
    write_run_record(record, DEFAULT_RUNS_DIR / f"{run_id}.json")
    return IndexAndScoreResult(
        run_id=run_id,
        record=record,
        summary=summary,
        stored_count=stored_count,
        wall_clock_seconds=ingest_seconds,
        question_pools=question_pools,
        store_rows=result_store_rows,
        document_ids=document_ids,
    )


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

        questions: tuple[Question, ...] | None = None
        question_set_format: QuestionSetFormat | None = None
        if run_args.questions is not None:
            read_set = read_question_set(Path(run_args.questions))
            question_set_format = read_set.format
            questions = read_set.questions

        result = await index_and_score(
            deps,
            ctx=ctx,
            path=Path(run_args.path),
            pipeline=run_args.pipeline,
            corpus_name=run_args.corpus_name,
            questions=questions,
            document_labels=document_labels_from_manifest(run_args.manifest),
            top_k=run_args.top_k,
            query_pipeline=run_args.query_pipeline,
            reuse_index=run_args.reuse_index,
        )
        return Produced(
            value=EvalRunCommandResult(
                run_id=result.run_id,
                path=run_args.path,
                summary=result.summary,
                stored_count=result.stored_count,
                record=result.record,
                wall_clock_seconds=result.wall_clock_seconds,
                question_set_format=question_set_format,
            )
        )


def _falsify_against_baseline(
    baseline: str,
    run_a_id: str,
    record_a: RunRecord,
    record_b: RunRecord,
    *,
    exclude: set[str],
) -> tuple[tuple[str, ...], Mapping[str, DifferenceJudgement], BaselineSelection]:
    """`weft eval compare --baseline <pipeline>`'s own work — see the module docstring's own
    task-8.8 paragraph. `exclude` is `{--a, --b}`: a rung is not one of its own baseline's
    repetitions.

    **Task 16.1 — a repetition is keyed on the ingest pipeline *and* the query rung, when both
    sides know one.** `record_a.query_rung is None`, or any name-matched candidate's
    `query_rung is None`, means at least one side predates task 16.1 and never recorded a
    rung at all — falling back to `BaselineSelection.INGEST_PIPELINE_ONLY`, today's behaviour,
    rather than refusing every baseline taken before this task. Otherwise every name-matched
    candidate whose own `query_rung` does not equal `record_a.query_rung` is dropped before the
    spread is computed, `BaselineSelection.INGEST_AND_QUERY_RUNG`: a run of a different query
    rung over the same index is a configuration difference, not a repetition.

    Raises `NoBaselineRunsError` for a pipeline nothing under `DEFAULT_RUNS_DIR` ran,
    `IncomparableRunsError` for a kept repetition that differs from `record_a` by more than
    its pipeline (deliberately not checked — a baseline is a different pipeline from the rung
    by construction), and lets `weft_eval.falsify.baseline_spreads`'s own
    `TooFewRepetitionsError` propagate unchanged for a baseline run only once — including once
    the query-rung filter above has dropped it below two.
    """
    all_records = all_run_records()
    named = tuple(
        (run_id, record)
        for run_id, record in all_records
        if record.resolved_pipeline.name == baseline and run_id not in exclude
    )
    if not named:
        options = tuple(sorted({record.resolved_pipeline.name for _, record in all_records}))
        raise NoBaselineRunsError(
            f"'{baseline}' names no persisted baseline repetition under '{DEFAULT_RUNS_DIR}' "
            f"(excluding the two runs being compared). Pipelines actually run: "
            f"{', '.join(options) or '(none)'}.",
            valid_options=options,
            baseline=baseline,
        )

    if record_a.query_rung is None or any(record.query_rung is None for _, record in named):
        selection = BaselineSelection.INGEST_PIPELINE_ONLY
        repetitions = named
    else:
        selection = BaselineSelection.INGEST_AND_QUERY_RUNG
        repetitions = tuple(
            (run_id, record) for run_id, record in named if record.query_rung == record_a.query_rung
        )

    for run_id, repetition in repetitions:
        # Deliberately not checking the pipeline here — a baseline is a different pipeline
        # from the rung being judged by construction, which is the entire point. Corpus and
        # model versions are what make its variability a measurement of the same system.
        baseline_reasons = _incomparable_reasons(record_a, repetition)
        if baseline_reasons:
            raise IncomparableRunsError(
                f"baseline run '{run_id}' ('{baseline}') is not comparable to '{run_a_id}': "
                f"{'; '.join(baseline_reasons)}. A baseline's spread only measures this "
                "system's own variability when the corpus and model versions agree.",
                run_a=run_a_id,
                run_b=run_id,
                reasons=baseline_reasons,
            )

    spreads = baseline_spreads([record for _, record in repetitions])
    falsification = judge_differences(record_a, record_b, spreads)
    baseline_runs = tuple(sorted(run_id for run_id, _ in repetitions))
    return baseline_runs, falsification, selection


def _load_baseline_report_or_refuse(path: Path) -> BaselineReport:
    """`load_baseline_report(path)`, or `NotABaselineReportError` naming `path` for a file that
    does not parse as a `weft_eval.baseline.BaselineReport` — repair `R22.4d`.
    """
    try:
        return load_baseline_report(path)
    except ValidationError as exc:
        first_line = str(exc).splitlines()[0] if str(exc) else str(exc)
        raise NotABaselineReportError(f"'{path}' is not a baseline report: {first_line}") from exc


def _compare_baseline_reports(
    compare_args: EvalCompareArgs, *, a_is_file: bool, b_is_file: bool
) -> Outcome[CommandResult]:
    """`weft eval compare <a> <b>` where at least one names a baseline report file rather than
    a persisted run id — repair `R22.4d`. See the module docstring's own R22.4d paragraph.
    """
    a, b = compare_args.a, compare_args.b
    if a_is_file != b_is_file:
        file_arg, other_arg = (a, b) if a_is_file else (b, a)
        reason = f"'{other_arg}' is not a file"
        raise IncomparableRunsError(
            f"'{file_arg}' is a baseline report and '{other_arg}' is not a file — a baseline "
            f"report is judged against another baseline report, never against a run id.",
            run_a=a,
            run_b=b,
            reasons=(reason,),
        )
    if compare_args.baseline is not None:
        raise IncomparableRunsError(
            "--baseline selects a pipeline's own repetitions among persisted runs, and means "
            "nothing when comparing two baseline report files.",
            run_a=a,
            run_b=b,
            reasons=("--baseline was given",),
        )
    if compare_args.kind is not None:
        raise IncomparableRunsError(
            "--kind restricts the comparison to one question kind among persisted runs, and "
            "means nothing when comparing two baseline report files.",
            run_a=a,
            run_b=b,
            reasons=("--kind was given",),
        )

    published = _load_baseline_report_or_refuse(Path(a))
    later = _load_baseline_report_or_refuse(Path(b))
    reproduction = judge_reproduction(published, later)
    if not reproduction.reproduced:
        parts = tuple(
            f"{verdict.metric}: {verdict.later} is outside [{verdict.low}, {verdict.high}]"
            if verdict.later is not None
            else (
                f"{verdict.metric}: not measured (the baseline records "
                f"[{verdict.low}, {verdict.high}])"
            )
            for verdict in reproduction.verdicts
            if not verdict.inside
        )
        raise BaselineNotReproducedError(f"'{b}' does not reproduce '{a}': " + "; ".join(parts))

    return Produced(
        value=EvalCompareCommandResult(
            run_a=a,
            run_b=b,
            corpus_matches=True,
            model_versions_match=True,
            active_distributions_match=(
                reproduction.published_distributions == reproduction.later_distributions
            ),
            pipeline_diff=diff_resolved(
                published.record.resolved_pipeline, later.record.resolved_pipeline
            ),
            metrics_comparison={},
            reproduction=reproduction,
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
        a_is_file = Path(compare_args.a).is_file()
        b_is_file = Path(compare_args.b).is_file()
        if a_is_file or b_is_file:
            return _compare_baseline_reports(compare_args, a_is_file=a_is_file, b_is_file=b_is_file)

        record_a = _load_or_refuse(compare_args.a)
        record_b = _load_or_refuse(compare_args.b)

        reasons = _incomparable_reasons(record_a, record_b)
        if reasons:
            raise IncomparableRunsError(
                f"'{compare_args.a}' and '{compare_args.b}' are not comparable as a change of "
                f"pipeline alone: {'; '.join(reasons)}. A comparison is only meaningful when "
                f"the corpus, model versions and question set agree and only the pipeline "
                f"differs — otherwise a metric delta cannot be attributed to the pipeline "
                f"change ('09-release.md' §4, V3's own failure clause). Which distributions "
                f"were active, and at which versions, is reported beside a comparison and "
                f"never refused on.",
                run_a=compare_args.a,
                run_b=compare_args.b,
                reasons=reasons,
            )

        diff = diff_resolved(record_a.resolved_pipeline, record_b.resolved_pipeline)
        # Task 16.1 — the query rung each side scored with, always constructed: it is the
        # subject of the comparison, never a reason to refuse it, unlike the corpus above.
        query_rungs = QueryRungDifference(a=record_a.query_rung, b=record_b.query_rung)

        baseline_pipeline: str | None = None
        baseline_runs: tuple[str, ...] = ()
        falsification: Mapping[str, DifferenceJudgement] | None = None
        baseline_selection: BaselineSelection | None = None
        if compare_args.baseline is not None:
            baseline_pipeline = compare_args.baseline
            baseline_runs, falsification, baseline_selection = _falsify_against_baseline(
                compare_args.baseline,
                compare_args.a,
                record_a,
                record_b,
                exclude={compare_args.a, compare_args.b},
            )

        paired, paired_slice, paired_reason = paired_differences_for_slice(
            record_a, record_b, kind=compare_args.kind, slice_=compare_args.slice
        )

        return Produced(
            value=EvalCompareCommandResult(
                run_a=compare_args.a,
                run_b=compare_args.b,
                corpus_matches=True,
                model_versions_match=True,
                active_distributions_match=record_a.active_distributions
                == record_b.active_distributions,
                pipeline_diff=diff,
                metrics_comparison=(
                    metrics_comparison_for_kind(record_a, record_b, kind=compare_args.kind)
                    if compare_args.kind is not None
                    else metrics_comparison_for_slice(record_a, record_b, slice_=compare_args.slice)
                ),
                baseline_pipeline=baseline_pipeline,
                baseline_runs=baseline_runs,
                falsification=falsification,
                query_rungs=query_rungs,
                baseline_selection=baseline_selection,
                paired_differences=paired,
                paired_differences_slice=paired_slice,
                paired_differences_reason=paired_reason,
                packaging_differences=_packaging_differences(record_a, record_b),
                latency_a=latency_summary(record_a.question_seconds),
                latency_b=latency_summary(record_b.question_seconds),
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
    "BaselineNotReproducedError",
    "BaselineSelection",
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
    "IndexAndScoreResult",
    "MetricComparison",
    "NoBaselineRunsError",
    "NotABaselineReportError",
    "QueryRungDifference",
    "TraceArgs",
    "TraceCommand",
    "TraceCommandResult",
    "UnknownQuestionKindError",
    "UnknownRunIdError",
    "UnknownSliceError",
    "document_labels_from_manifest",
    "index_and_score",
    "metrics_comparison_for_kind",
    "metrics_comparison_for_slice",
    "model_versions_of",
    "paired_differences_for_slice",
    "register_eval_commands",
]
