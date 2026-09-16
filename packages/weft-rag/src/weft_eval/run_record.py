"""The persisted run — task **4.4**, and fitness function **8(c)**.

**Q1, settled** (`.phase4-design.md` §3): a run record is a **file**, written by `weft-eval`, not
a row in the store. G4 says a store takes vectors; a run record is not a `Node`, and forcing one
through `weft_kernel.payload.Node` to get it into a store would be shaping evaluation knowledge to
fit a contract built for retrieval, not the other way round. D1 already settled the larger
question this answers: what a run record must contain is *evaluation* knowledge — what ran, over
what, with what — and a kernel that knew what a run is *for* would be a kernel naming a
capability. Nothing here touches `packages/weft-kernel`.

**Five fields were fixed by `01` -> Phase 4 *Exit* and `09` §4 **V6**; later tasks added the
rest, each with its own docstring on `RunRecord`.** The first five, and the earliest additions:

- `resolved_pipeline` — **what actually ran**, not the document that named it. Task 4.0 exists
  because of this task: before it, `weft index` named its four stages in Python and there was no
  resolved pipeline to persist. This is `weft_kernel.resolution.ResolvedPipeline` itself, reused
  rather than a second, weft-eval-shaped copy of the same information — the kernel already publishes
  the frozen, fully-explicit form a resolved document reduces to, and a run record that re-derived
  its own summary of a pipeline would be the two-lists failure `docs/internal/README.md` opens by
  describing, aimed at pipelines instead of documentation.
- `corpus` — **which corpus**, `CorpusIdentity`: a name and a digest over what the caller
  identifies each document by — each document's own content hash, since task 16.0 — so "a
  different corpus" (V3's own failure clause, already proven at `weft_cli.eval_baseline`'s own
  `corpus_identity` call, R22.4c) is a comparison two runs can make, not a promise two operators
  have to trust.
- `model_versions` — **what a role resolved to**, e.g. `{"embed": "openai:text-embedding-3-small"}`.
  Taken as given, never derived here: `weft-eval` has no way to know what an `Embedder` or an
  `LLM` role resolved to at run time — only whoever drove the pipeline does — and inventing a
  derivation here would mean guessing at a fact this pack cannot observe.
- `active_distributions` — **the active distribution set**, `active_distribution_set`'s own
  output. This is fitness function 8(c)'s subject: "the run record names the active distribution
  set, equal to what `plugins doctor` reports as `active`" (`01` -> *Fitness functions* item 8(c)).
  `docs/02-extension-model.md` §2 states why this is recorded on every run, "not as a security
  feature": a comparison has to be able to say what was installed. Since repair `R22.11`
  `weft eval compare` reports a difference here beside the comparison rather than refusing it.
- `distribution_versions` — **task 16.3's own addition**: what version of each active
  distribution was installed, so a comparison between runs on `weft-rag` 2.4.0 and 2.5.0 says
  so. Taken as given, exactly like `model_versions` one field over: `weft_cli` owns
  `installed_versions`/`active_distribution_versions`, and deriving the mapping inside
  `build_run_record` would put an arrow from this pack into the CLI that calls it. `None` is
  *not recorded* — every record written before this task; `{}` is *measured, and no active
  distribution had recorded metadata* — see `RunRecord.distribution_versions`'s own comment for
  why those are different facts.
- `metrics` — **task 4.9's own addition, `.phase4-design.md` §7's gap closed.** Every metric this
  run actually scored, keyed by the *name the metric itself computed* (never the registered
  plugin name — the same distinction `weft_eval.aggregate`'s own R5 paragraph already draws), as
  a `MetricRunResult`: `Produced[MetricAggregate]` for a metric that scored, `NotAggregated` for
  one that did not, carrying why. Empty (`{}`) is the honest answer for a run nothing scored —
  `weft eval run` with no `--questions` — never a fabricated entry. See `MetricRunResult`'s own
  docstring for why this is a two-member closed union rather than `weft_kernel.payload.Outcome`
  embedded directly.

**How 8(c)'s equality is checked, and why it is not vacuous.** `active_distribution_set` filters
`weft_kernel.discovery.PackReport` on exactly one condition — `status is PackStatus.ACTIVE` — the
identical field `weft_cli.plugins_report.render_list`/`render_doctor` print as each report's own
`status.value`. The two can disagree only if one of them starts reading a different fact off the
same `PackReport`; `tests/architecture/test_ff8_trust_model.py`'s clause-(c) test proves they do
not, by comparing this function's output against `render_doctor`'s own rendered text for the
identical report tuple — never against a second copy of the same filter, which would prove
nothing — and a second test there manufactures the exact drift (filtering by `contributed > 0`
instead of `status is ACTIVE`) to show the comparison actually fails when the two definitions
disagree.

**What this module does not do.** It does not run a pipeline, price a run, or decide when a run
happens — `weft eval run|compare` (task 4.6, scope-fenced out of this one) is the command surface
that will call `build_run_record`/`write_run_record`. It does not diff two records — that is 4.6's
`weft eval compare` and 4.9's two-pipeline comparison. It registers no plugin: folding a run's own
facts into one record is not a capability any pack or third party needs to swap, the identical
reasoning `aggregate.py`'s own module docstring already gives for not registering `aggregate()`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from weft_eval.aggregate import MetricAggregate
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced
from weft_kernel.resolution import ResolvedPipeline

_NO_MODEL_VERSIONS: Final[Mapping[str, str]] = MappingProxyType({})
_NO_REPORTS: Final[tuple[PackReport, ...]] = ()
_NO_METRICS: Final[Mapping[str, Outcome[MetricAggregate]]] = MappingProxyType({})


class CorpusDigestBasis(StrEnum):
    """What a `CorpusIdentity.digest` was computed over.

    Two members. A record that names none was written before ledger task 16.0, when every
    caller digested resolved filesystem paths — and that absence is a fact, not a gap: see
    `RunRecord.corpus_digest_basis`.
    """

    DOCUMENT_BYTES = "document-bytes"
    #: Repair **R22.4c** — `weft eval baseline`'s own basis. The digest is over each manifest
    #: document's `f"{id}\t{sha256}"`, those bytes having been verified against that sha256
    #: before the run: a manifest id is stable across a re-staging that `DOCUMENT_BYTES`'
    #: resolved-path predecessor was not, and the sha256 is the corpus's own tracked identity
    #: (`weft_eval.corpus_manifest.ManifestDocument.sha256`) rather than a digest this module
    #: would otherwise have to re-read the bytes to recompute.
    MANIFEST_DIGESTS = "manifest-digests"


class QuestionSetDigestBasis(StrEnum):
    """What function computed `RunRecord.question_set_digest` — task **38.11**.

    One member. A record that names none was digested over the retired
    `weft_cli.eval_scoring.Question` form, before this task — that absence is a fact, not a gap,
    `CorpusDigestBasis`'s own shape one field over.
    """

    QUESTION_SET = "question-set"


class CorpusIdentity(BaseModel):
    """Which corpus a run measured, in a form two runs can be compared by.

    `digest` is a sha256 over the identity strings a caller passes, sorted so order never
    changes it — and **what those strings are is the caller's choice, not a property of this
    class.** This docstring used to claim the digest was "content-derived, never a path" while
    every `weft eval run` caller was passing resolved filesystem paths, so the digest stood
    still when a document's bytes changed and moved when one was renamed; a docstring that
    states the property wanted rather than the property held is how that survived being
    written down (`docs/internal/lessons.md` `L17.2`). Which one a record actually holds is
    `RunRecord.corpus_digest_basis`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    digest: str = Field(min_length=1)


def corpus_identity(name: str, document_ids: Iterable[str]) -> CorpusIdentity:
    """A `CorpusIdentity` for `name` over `document_ids` — order-independent, and over whatever
    its caller identifies a document by.

    `document_ids` is whatever a caller's own documents are identified by — a `SourceId`, a
    manifest id, a checksum — this module does not care which, only that the same set of
    documents always produces the same digest and a different set never does.
    """
    joined = "\n".join(sorted(document_ids))
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return CorpusIdentity(name=name, digest=digest)


class QueryRung(BaseModel):
    """The query pipeline a run scored with — the rung, not the ingest pipeline.

    Both fields, because neither answers alone: a *name* is what an operator typed and two
    projects can give one name to two documents, while an *identity* is
    `weft_kernel.resolution.pipeline_identity`'s digest of what that name resolved to and is
    what a baseline's repetitions are keyed on.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    identity: str = Field(min_length=1)


class NoQueryRung(BaseModel):
    """This run named no query rung, and `reason` says what retrieved instead.

    A measurement, never an absence — `RunRecord.query_rung` is `None` for a record written
    before task 16.0's sibling 16.1, and that is a different fact. `NotAggregated` is the
    precedent one field over: the two members of the union below never share a field name, so
    the union always resolves unambiguously through JSON.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1)


#: What a run retrieved with, as a `RunRecord` carries it.
type ScoredQueryRung = QueryRung | NoQueryRung


def active_distribution_set(reports: Iterable[PackReport]) -> tuple[str, ...]:
    """Every distribution `reports` marks `PackStatus.ACTIVE`, sorted and deduplicated. See
    the module docstring for why this is fitness function 8(c)'s left-hand side and how its
    equality with what `plugins doctor` reports is checked.

    A *set*, as the name says, and now literally: one distribution may ship several packs,
    so several `ACTIVE` reports can carry the same distribution name. Recording it once is
    what the reproducibility claim needs — a distribution is the versioned unit, and the
    packs inside one move together — and repeating it twelve times would have said nothing
    a reader could act on.
    """
    return tuple(
        sorted({report.distribution for report in reports if report.status is PackStatus.ACTIVE})
    )


class NotAggregated(BaseModel):
    """A registered metric that produced no aggregate for this run — `reason` says why.

    Collapses `weft_kernel.payload.Failed`/`NothingToProduce` into one persisted shape: both
    already carry only a `reason: str` — `weft_kernel.payload.outcome`'s own two variants are
    structurally identical — so keeping them as two persisted variants would buy a reader no
    information the prose does not already carry (`weft_eval.aggregate.aggregate`'s own
    `reason` text already says which happened: "N failed" vs "N had nothing to score"). What
    must not collapse is *produced* vs *not* — that is what `MetricRunResult` keeps distinct.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str


#: One metric's outcome as a `RunRecord` carries it — R4's rule applied one level up: mutually
#: exclusive *by construction*, never a nullable `NotAggregated` sitting beside a `MetricAggregate`
#: field that defaults to `None`. `Produced[MetricAggregate]` (field `value`) and `NotAggregated`
#: (field `reason`) never share a field name, so — unlike embedding `weft_kernel.payload.Outcome`
#: here directly, whose `Failed`/`NothingToProduce` members are structurally identical and so
#: ambiguous to round-trip through JSON — this two-member union always resolves unambiguously.
type MetricRunResult = Produced[MetricAggregate] | NotAggregated


def _as_run_result(outcome: Outcome[MetricAggregate]) -> MetricRunResult:
    """`aggregate()`'s three-state `Outcome` collapsed to `MetricRunResult`'s two — see
    `NotAggregated`'s own docstring for why `Failed`/`NothingToProduce` fold into one shape here.
    """
    match outcome:
        case Produced():
            return outcome
        case Failed(reason=reason) | NothingToProduce(reason=reason):
            return NotAggregated(reason=reason)


class NotScored(BaseModel):
    """One question a metric produced no score for — `reason` says why.

    `weft_eval.aggregate`'s `NotAggregated` one granularity down, and it collapses the same
    two `Outcome` variants for the same reason: `Failed` and `NothingToProduce` are
    structurally identical, so persisting them as two members would buy a reader nothing the
    `reason` text does not already say. What must not collapse is *scored* against *not*,
    which is `docs/09-release.md`:620's V4 clause — a failed question is an error, never a
    zero, and a zero here cannot be told from a question the rung genuinely got wrong.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str


#: One question's outcome for one metric. `Produced[float]` (field `value`) and `NotScored`
#: (field `reason`) share no field name, so this union always resolves unambiguously through
#: JSON — `MetricRunResult`'s own reason to be a two-member union, one level down.
type QuestionOutcome = Produced[float] | NotScored


class QuestionKey(StrEnum):
    """What the keys of `PerQuestionScores.scores` are.

    A key of `"fetch-001"` and a key of `"0"` are read differently by anyone pairing two runs,
    and a `--questions` file with no ids is the normal case. Saying which is what stops a
    reader treating a position as an identity that survives a second questions file.
    """

    QUESTION_ID = "question-id"
    POSITION = "position"


class PerQuestionScores(BaseModel):
    """One metric's outcome for every question it was asked — task **16.4**."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    keyed_by: QuestionKey
    scores: Mapping[str, QuestionOutcome]


class PerQuestionSeconds(BaseModel):
    """How long each question's own retrieval took — task **33.7**, keyed identically to
    `PerQuestionScores` above so a reader pairing a score with its latency never has to guess
    at a second vocabulary. `RunDurations.query_seconds` is the run's total; this is the tail
    hiding inside it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    keyed_by: QuestionKey
    seconds: Mapping[str, float]

    @field_validator("seconds")
    @classmethod
    def _no_negative_seconds(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        for question_key, elapsed in value.items():
            if elapsed < 0:
                raise ValueError(f"seconds['{question_key}'] is negative: {elapsed}")
        return value


class RoleTokens(BaseModel):
    """What one `[llm.roles]` role spent across a run — task **33.7**, folded from
    `weft_llm.usage.UsageEntry`. `calls_not_reporting` is how a reader tells a role that made
    calls a provider does not meter apart from a role that made none at all — the module
    docstring's own distinction, one level up.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    calls: int = Field(ge=0)
    calls_not_reporting: int = Field(ge=0)


class ExperimentRun(BaseModel):
    """Which experiment a record was run as one arm's one repetition of — task **38.0**.

    `name`/`digest` name the experiment document (`weft_eval.experiment.Experiment`'s own
    `name`/`digest`); `invocation` is one `weft eval experiment` call's own id, shared by every
    record that call wrote, so a table can group an invocation's own runs apart from a later
    re-run of the identical document. `arm`/`repetition` are the one cell of that invocation this
    record is. `RunRecord.experiment` is `None` for a run made outside an experiment, and for
    every record written before this task — a fact stated by absence, `query_rung`'s own footing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    digest: str = Field(min_length=1)
    invocation: str = Field(min_length=1)
    arm: str = Field(min_length=1)
    repetition: int = Field(ge=1)


class RunDurations(BaseModel):
    """Ledger task 10.22 — how long the two halves of a run took, kept apart on purpose.

    `ingest_seconds` is the rebuild cost; `query_seconds` is the scoring cost. G15's *Remove*
    face turns on whether avoiding a rebuild is worth a change to a published contract family,
    and a rebuild is **ingest** — folding scoring's cost into one total would corrupt that
    comparison with a number the technique under discussion does not move at all. Both fields
    are required: a caller that measured one half and not the other has not measured the run,
    and there is no default that would not be mistaken for a measurement.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ingest_seconds: float = Field(ge=0.0)
    query_seconds: float = Field(ge=0.0)


class RunRecord(BaseModel):
    """One persisted run — `01` -> Phase 4 *Exit*, `09` §4 **V6**. See the module docstring for
    what each field is and why it is here rather than derived or omitted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recorded_at: str = Field(min_length=1)
    resolved_pipeline: ResolvedPipeline
    corpus: CorpusIdentity
    model_versions: Mapping[str, str] = Field(default_factory=dict)
    active_distributions: tuple[str, ...] = ()
    #: Task 16.3 — what version of each active distribution was installed. `None` means *not
    #: recorded*: a record written before this task named the distributions and never their
    #: versions, so two such records agree about an environment neither measured. `{}` is the
    #: different fact that versions *were* measured and no active distribution had recorded
    #: metadata — `installed_versions` omits such a name, `L5.9` — and an environment of
    #: editable installs reaches it.
    distribution_versions: Mapping[str, str] | None = None
    #: Task 10.22. `None` means *not measured*, never `0.0` — task 10.20's rule one module
    #: over: a default must not be mistakable for a value the system could legitimately have
    #: computed, and a persisted `0.0` cannot be told from a run that was instant.
    durations: RunDurations | None = None
    #: Task 16.0 — what `corpus.digest` is over. `None` means *not recorded*, which is what
    #: every record written before that task carries, and those digests are over each
    #: document's resolved *path*: not comparable to one written since. Task 10.22's rule for
    #: `durations` one field over — a default must not be mistakable for a value the system
    #: could legitimately have computed.
    corpus_digest_basis: CorpusDigestBasis | None = None
    #: Task 16.1 — the query rung this run scored with. `None` means *not recorded*: a record
    #: written before this task persisted no query pipeline at all, so a comparison across that
    #: boundary cannot tell a rung difference from a missing field. `NoQueryRung` is the
    #: measurement that no rung was named; the two are not the same claim.
    query_rung: ScoredQueryRung | None = None
    #: Task 4.9 — see the module docstring's own paragraph. `{}` for a run that scored nothing.
    metrics: Mapping[str, MetricRunResult] = Field(default_factory=dict)
    #: Task 16.6 — a sha256 over the canonical questions this run was scored with, or `None`
    #: for a record that predates the field or a run given no `--questions` at all. Built by
    #: `weft_eval.question_set.question_set_digest`, which lives there because `Question` does:
    #: this module would have to import that reader to compute it, the identical arrow
    #: `distribution_versions` already refuses to draw.
    question_set_digest: str | None = None
    #: Task **38.11** — which function produced `question_set_digest`, so a digest taken over
    #: the retired `weft_cli.eval_scoring.Question` form is told apart from one taken over the
    #: one model: the same questions digest differently under the two. `None` means *not
    #: recorded* — every record written before this task.
    question_set_digest_basis: QuestionSetDigestBasis | None = None
    #: Task 16.4 — one outcome per question per metric, keyed by metric name exactly as
    #: `metrics` above is, so a reader pairing an aggregate with its questions never has to
    #: guess at two vocabularies. `None` means *not recorded*: a record written before this
    #: task carries the means and not the observations under them, so a paired comparison
    #: against it is not computable and says so rather than inventing one.
    question_scores: Mapping[str, PerQuestionScores] | None = None
    #: Repair **R38.1** — each recorded question's own axes (`weft_eval.question_set.Question.
    #: axes`, plus `"kind"` when the question stated one), keyed identically to
    #: `question_scores`. `None` means *not recorded*: every record written before this repair
    #: names each question's scores and never which slice it belonged to, so
    #: `weft eval compare --slice`/`--kind` cannot restrict a paired difference to that slice
    #: and says so rather than pairing the whole run under a slice's own header.
    question_axes: Mapping[str, Mapping[str, str]] | None = None
    #: Task 33.7 — each question's own retrieval latency, keyed identically to
    #: `question_scores`. `None` means *not recorded*: `durations.query_seconds` one field
    #: over is the run's total, but a record written before this task never split it out per
    #: question, so a comparison against it is not computable and says so rather than
    #: inventing one.
    question_seconds: PerQuestionSeconds | None = None
    #: Task 33.7 — what each model role spent across the run, keyed by role. `None` means
    #: *not recorded*, the identical distinction `distribution_versions` draws from `{}`: a
    #: record that scored no question through a model has `{}`, a record written before this
    #: task measured nothing at all and has `None`.
    token_usage: Mapping[str, RoleTokens] | None = None
    #: Task **38.0** — which experiment, invocation, arm and repetition this run was. `None` for
    #: a run made outside an experiment, and for every record written before this task.
    experiment: ExperimentRun | None = None


def build_run_record(
    *,
    recorded_at: str,
    resolved_pipeline: ResolvedPipeline,
    corpus: CorpusIdentity,
    corpus_digest_basis: CorpusDigestBasis | None = None,
    query_rung: ScoredQueryRung | None = None,
    model_versions: Mapping[str, str] = _NO_MODEL_VERSIONS,
    reports: Iterable[PackReport] = _NO_REPORTS,
    distribution_versions: Mapping[str, str] | None = None,
    metrics: Mapping[str, Outcome[MetricAggregate]] = _NO_METRICS,
    durations: RunDurations | None = None,
    question_scores: Mapping[str, PerQuestionScores] | None = None,
    question_axes: Mapping[str, Mapping[str, str]] | None = None,
    question_set_digest: str | None = None,
    question_set_digest_basis: QuestionSetDigestBasis | None = None,
    question_seconds: PerQuestionSeconds | None = None,
    token_usage: Mapping[str, RoleTokens] | None = None,
    experiment: ExperimentRun | None = None,
) -> RunRecord:
    """Assemble one `RunRecord`. `active_distributions` is always derived from `reports`
    through `active_distribution_set` — never accepted directly — so there is no second,
    caller-supplied list of "what was active" that could drift from the one 8(c) checks.

    `metrics` takes the same `Outcome[MetricAggregate]` shape `weft_eval.aggregate.aggregate`
    itself returns — a caller (`weft_cli.eval_scoring`, task 4.9) hands back exactly what it
    measured, keyed by the name the metric itself computed, and this function is what narrows
    each entry to the two-state `MetricRunResult` a `RunRecord` actually persists.

    `durations` is passed straight through, never derived here — this function has no clock of
    its own and inventing one would mean guessing at a fact only the caller observed.

    `corpus_digest_basis` is passed straight through too, and for the identical reason one
    level up: this function cannot see what `corpus`'s digest was actually computed over, so
    the value is a claim the caller makes about its own `corpus_identity()` call, never a fact
    derived here.

    `query_rung` — task 16.1 — is passed straight through as well, on the identical footing:
    only the caller that actually ran the questions knows whether a query rung was named, and
    which one.

    `distribution_versions` — task 16.3 — is passed straight through too, and unlike
    `active_distributions` is **not** derived here from `reports`: the reader
    (`weft_cli.installed_versions.active_distribution_versions`) lives in `weft_cli`, and this
    module is `weft_eval`, so deriving it here would draw an arrow from the evaluation pack into
    the CLI. `None` means the caller did not measure versions at all; `{}` means it measured and
    found none — see `RunRecord.distribution_versions`'s own comment.

    `question_scores` — task 16.4 — is passed straight through too, on the identical footing:
    only the caller that paired samples to outcomes (`weft_cli.eval_scoring.score_pipeline`,
    through `weft_eval.harness.score_retrieval_gate_subset`) knows what each question scored.

    `question_axes` — repair R38.1 — is passed straight through too, on the identical footing:
    only the caller that read the question file (`weft_cli.eval_scoring.score_pipeline`) knows
    which axes each question carried.

    `question_set_digest_basis` — task 38.11 — is passed straight through too, on the identical
    footing: only the caller that computed `question_set_digest` knows which function produced
    it.

    `question_seconds`/`token_usage` — task 33.7 — are passed straight through as well, on the
    identical footing one field over: only the caller that ran the question loop
    (`weft_cli.eval_scoring.score_pipeline`) measured either.
    """
    return RunRecord(
        recorded_at=recorded_at,
        resolved_pipeline=resolved_pipeline,
        corpus=corpus,
        corpus_digest_basis=corpus_digest_basis,
        query_rung=query_rung,
        model_versions=model_versions,
        active_distributions=active_distribution_set(reports),
        distribution_versions=distribution_versions,
        durations=durations,
        metrics={name: _as_run_result(outcome) for name, outcome in metrics.items()},
        question_scores=question_scores,
        question_axes=question_axes,
        question_set_digest=question_set_digest,
        question_set_digest_basis=question_set_digest_basis,
        question_seconds=question_seconds,
        token_usage=token_usage,
        experiment=experiment,
    )


def write_run_record(record: RunRecord, path: Path) -> Path:
    """Write `record` as JSON to `path`, creating parent directories as needed. Returns `path`.

    Plain `Path.write_text` — no store, no database, nothing `weft_kernel` needs to know about.
    Q1's whole argument cashed out: writing a run is filesystem work, not a capability with a
    contract, so it is a function, not a plugin point.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_run_record(path: Path) -> RunRecord:
    """Read a `RunRecord` back from `path` — the other half of "two runs can be diffed after
    the fact". Raises `pydantic.ValidationError`, naming the field, for a file that is not a
    well-formed `RunRecord`; raises `FileNotFoundError` for a path nothing wrote to.
    """
    return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
