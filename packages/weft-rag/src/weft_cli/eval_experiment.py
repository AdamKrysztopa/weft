"""`weft eval experiment <path>` — ledger task **38.0**.

Every experiment run in this tree before this task was its own script. `weft_eval.experiment`
reads the **document**: the arms, the question set, `repeats`, the metrics and the minimum
detectable effect, all stated before any run. This module is the command that actually runs one —
every arm times `repeats` repetitions, each through the identical index-and-score path
`weft eval run` uses (`weft_cli.eval_commands.index_and_score`), so an experiment's own numbers can
never silently diverge from a single run's.

**Comparability is checked before anything is indexed, and it is checked by digest, never by
name.** Two arms pointed at directories named identically but holding different bytes, or at two
question files that happen to share a row count, are exactly the case a name comparison would
miss — so this reads each arm's corpus digest (`weft_cli.ingest.corpus_documents` +
`content_hashes_of` + `weft_eval.run_record.corpus_identity`, the identical derivation `weft eval
run` itself persists), each arm's question-set digest (`weft_eval.question_set.QuestionSet.
digest`), and each arm's model versions (`weft_cli.eval_commands.model_versions_of`, over the
resolved *ingest* pipeline each arm names) — comparing every arm against the first, arm by arm,
and refuses at the first one that differs, naming it. A model-version key only one of the two
arms carries is not a difference: an experiment typically varies exactly one slot (a hybrid arm's
own `Retriever`, a rung's own summarising model) and every other slot present on one side and
absent on the other is what the experiment is testing, not a reason to refuse it.

**Arms share one store, so a passage from another arm's corpus is a real risk, not a hypothetical
one.** Every call into `index_and_score` below passes `refuse_foreign_documents=True`
(`weft_cli.eval_scoring.score_pipeline`'s own task-38.0 guard): a retrieved hit naming a document
outside the arm's own corpus refuses loudly rather than scoring as a silent miss, which is exactly
what would make a shared store read as a worse pipeline.

**Every distinct ingest pipeline and corpus is indexed once, in bounded batches — repair R38.2.**
Three arms naming one ingest pipeline over one corpus used to index it three times: `reuse_index`
was `repetition > 1` *per arm*, so the second and third arm's own first repetition each re-indexed
the identical corpus, paying for it again and ignoring an index an operator had already built, with
no batch size passed so the whole corpus sat in memory as one batch. This module now keeps the set
of `(pipeline, corpus)` pairs already indexed across every arm and repetition: the first time a
pair is met, `index_and_score` is called with `reuse_index=False, reprocess=False,
batch_size=experiment.index_batch_size` — unchanged documents already stored are skipped rather
than re-embedded, and the corpus is walked in the document's own batch size rather than as one
slice. Every later arm or repetition naming that same pair reuses what is already stored
(`reuse_index=True`), the identical `index_and_score`'s own `R10.4` paragraph already argues for a
rung comparison.

**A metric no run would record is refused before anything is indexed — repair R38.2, widened at
ledger task 40.1.** The names a run actually records at every one of `experiment.cutoffs` are
asked of the registered metrics themselves (`weft_eval.harness.score_retrieval_at_cutoffs`
against one synthetic sample), never assumed from the document's own `metrics =` list: a typo
(`recal@5` beside `recall@10`, neither of them a name any run has ever written) used to pass
every other refusal and run the whole, paid experiment, rendering `unjudgeable` naming nothing an
operator could act on. A name recorded at any declared cutoff is accepted; one at a cutoff the
document never declared is refused on the same footing as a typo.

**A record names its corpus as the document wrote it, not as this machine resolved it — repair
R38.2.** `corpus_name` is `corpus_for(arm)` relative to the experiment document's own directory,
POSIX-style — the same footing `weft_eval.experiment`'s own module docstring already gives every
resolved path, applied here to what a run record persists: two checkouts of one committed document
at two absolute paths must still write one corpus identity, or `weft eval compare` cannot pair them.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.eval_commands import (
    DEFAULT_RUNS_DIR,
    IndexAndScoreResult,
    all_run_records,
    document_labels_from_manifest,
    index_and_score,
    model_versions_of,
    stated_embedding_models,
)
from weft_cli.ingest import content_hashes_of, corpus_documents
from weft_cli.route_ask import resolve_named_pipeline
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_engine.registry_bootstrap import Dependencies
from weft_eval.contract import GenerationSample, RetrievalSample, RetrievedPassage
from weft_eval.experiment import Experiment, ExperimentArm, load_experiment
from weft_eval.harness import score_generation_gate_subset, score_retrieval_at_cutoffs
from weft_eval.offline import UnknownMetricNameError
from weft_eval.pool import (
    POOL_MANIFEST_SCHEMA_VERSION,
    LoadedPool,
    PoolManifest,
    PoolQuestion,
    load_pool_manifest,
    relevant_set_sha256,
    text_sha256,
    write_pool_manifest,
)
from weft_eval.question_set import Question, QuestionSet, read_question_set
from weft_eval.run_record import ExperimentRun, QueryRung, corpus_identity
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.resolution import ResolvedPipeline
from weft_retrieve.intent_and_anchors import find_anchors

_EVAL_EXPERIMENT_HELP = (
    "run every arm of an experiment document (eval/experiments/*.toml) for every repetition, "
    "through the identical index-and-score path 'weft eval run' uses, and persist one run "
    "record per arm and repetition — refuses before indexing anything if two arms are not "
    "comparable by corpus digest, question-set digest, pool manifest or model version"
)


class IncomparableArmsError(WeftError):
    """An experiment document named two arms that are not comparable — a different corpus, a
    different question set, or one model slot at two versions. See the module docstring's own
    paragraph for exactly what is compared and why absence on one side is not a difference.

    Raised before any arm is indexed or scored: `arm` is the first arm (after the baseline, the
    document's own first arm) found to differ, and `reasons` names every way it does.
    """

    def __init__(self, message: str, *, arm: str, reasons: tuple[str, ...]) -> None:
        super().__init__(message)
        self.arm = arm
        self.reasons = reasons


class UnscorableArmError(WeftError):
    """An arm named a `query_pipeline` whose resolved last stage is neither a `Generator` nor a
    `ContextPacker` — task **R38.0**'s pre-flight, so a resolvable-but-unscorable rung is refused
    before any arm writes a record rather than mid-run, after earlier arms already indexed and
    scored: `weft_cli.eval_scoring.score_pipeline` only knows how to ask a rung ending in a
    `Generator` (`run_named_ask`) or retrieve one ending in a `ContextPacker`
    (`run_named_retrieve`) — see that module's own docstring for why those are the two shapes
    a query rung can be scored over.
    """

    def __init__(self, message: str, *, arm: str, pipeline: str, contract: str) -> None:
        super().__init__(message)
        self.arm = arm
        self.pipeline = pipeline
        self.contract = contract


def _refuse_unscorable_arm(arm: ExperimentArm, *, deps: Dependencies) -> None:
    """One arm's own pre-flight — `UnscorableArmError`'s own paragraph, plus ledger task 40.2's
    second half: an arm naming `pool` must also name a `query_pipeline`, and that rung must end
    in a `ContextPacker` specifically, since a replay reranks through the rung a pool was
    captured from and a `Generator` has already answered past that point.
    """
    if arm.query_pipeline is None:
        if arm.capture_pool:
            raise UnscorableArmError(
                f"arm '{arm.name}' sets capture_pool but names no query_pipeline — a pool is "
                "what a retrieval rung packed, and this arm has none to pack one.",
                arm=arm.name,
                pipeline="(none)",
                contract="(no query pipeline)",
            )
        if arm.pool is not None:
            raise UnscorableArmError(
                f"arm '{arm.name}' names a pool to replay but names no query_pipeline — a "
                "replay reranks through the rerank document the pool names, and this arm has "
                "none.",
                arm=arm.name,
                pipeline="(none)",
                contract="(no query pipeline)",
            )
        return
    resolved = resolve_named_pipeline(
        arm.query_pipeline,
        registry=deps.registry,
        reports=deps.reports,
        contributions=deps.contributions,
    )
    contract = resolved.stages[-1].contract if resolved.stages else "(no stage)"
    if contract not in ("Generator", "ContextPacker"):
        raise UnscorableArmError(
            f"arm '{arm.name}' names query pipeline '{arm.query_pipeline}', which ends "
            f"in a {contract} stage — an arm is scored over what a ContextPacker packed "
            "or a Generator answered from, so its last stage must be one of those.",
            arm=arm.name,
            pipeline=arm.query_pipeline,
            contract=contract,
        )
    if arm.capture_pool and contract != "ContextPacker":
        raise UnscorableArmError(
            f"arm '{arm.name}' sets capture_pool but query pipeline "
            f"'{arm.query_pipeline}' ends in a {contract} stage, not a ContextPacker — "
            "a pool is what a retrieval rung packed, and a generating rung has no "
            "ranking beneath the passages it answered from.",
            arm=arm.name,
            pipeline=arm.query_pipeline,
            contract=contract,
        )
    if arm.pool is not None and contract != "ContextPacker":
        raise UnscorableArmError(
            f"arm '{arm.name}' names a pool to replay but query pipeline "
            f"'{arm.query_pipeline}' ends in a {contract} stage, not a ContextPacker — "
            "a replay reranks through the rung a pool was captured from, which a "
            "Generator has already answered past.",
            arm=arm.name,
            pipeline=arm.query_pipeline,
            contract=contract,
        )


class EvalExperimentArgs(BaseModel):
    """`weft eval experiment <path>` — one positional, the experiment document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="the experiment document")


class ExperimentRunRef(BaseModel):
    """One persisted run this invocation wrote — which arm, which repetition, which run id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: str
    repetition: int
    run_id: str


class EvalExperimentCommandResult(CommandResult):
    """`weft eval experiment`'s whole answer — the experiment's own identity, this invocation's
    id, and a reference to every record it wrote, in arm-then-repetition order.
    """

    name: str
    digest: str
    invocation: str
    runs: tuple[ExperimentRunRef, ...]


@dataclass(frozen=True)
class _ArmIdentity:
    """What one arm's identity check needs — computed once per arm, before the comparison loop
    and before any indexing, so a refusal never runs an arm it is about to reject.
    """

    resolved: ResolvedPipeline
    corpus_digest: str
    question_set_digest: str
    model_versions: dict[str, str]
    pool_manifest: str | None


async def _arm_identity(
    experiment: Experiment,
    arm: ExperimentArm,
    question_set: QuestionSet,
    *,
    deps: Dependencies,
    pool: LoadedPool | None,
) -> _ArmIdentity:
    """A replay arm (`pool` given) resolves its ingest pipeline by name alone — the identical
    resolution `corpus_documents` performs, minus the directory read a corpus this arm never
    touches would need — and takes its corpus digest from the manifest, so a replay arm compares
    equal, on corpus, to the capture arm it came from.
    """
    if pool is not None:
        resolved = resolve_named_pipeline(
            arm.pipeline,
            registry=deps.registry,
            reports=deps.reports,
            contributions=deps.contributions,
        )
        return _ArmIdentity(
            resolved=resolved,
            corpus_digest=pool.manifest.corpus_digest,
            question_set_digest=question_set.digest,
            model_versions=dict(
                model_versions_of(
                    resolved,
                    roles=deps.llm.roles,
                    stated=await stated_embedding_models(resolved, deps.registry),
                )
            ),
            pool_manifest=pool.sha256,
        )
    resolved, _specs, documents = corpus_documents(
        experiment.corpus_for(arm),
        pipeline=arm.pipeline,
        registry=deps.registry,
        reports=deps.reports,
        contributions=deps.contributions,
    )
    del _specs
    return _ArmIdentity(
        resolved=resolved,
        corpus_digest=corpus_identity(arm.name, content_hashes_of(documents)).digest,
        question_set_digest=question_set.digest,
        model_versions=dict(
            model_versions_of(
                resolved,
                roles=deps.llm.roles,
                stated=await stated_embedding_models(resolved, deps.registry),
            )
        ),
        pool_manifest=None,
    )


def _arm_incomparable_reasons(
    baseline_name: str, baseline: _ArmIdentity, arm_name: str, candidate: _ArmIdentity
) -> tuple[str, ...]:
    """Every way `candidate` (arm `arm_name`) is not comparable to `baseline` (arm
    `baseline_name`) — see the module docstring's own paragraph. Empty means comparable.
    """
    reasons: list[str] = []
    if candidate.corpus_digest != baseline.corpus_digest:
        reasons.append(
            f"corpus differs ('{baseline_name}' {baseline.corpus_digest[:12]}… vs "
            f"'{arm_name}' {candidate.corpus_digest[:12]}…)"
        )
    if candidate.question_set_digest != baseline.question_set_digest:
        reasons.append(
            f"question set differs ('{baseline_name}' {baseline.question_set_digest[:12]}… vs "
            f"'{arm_name}' {candidate.question_set_digest[:12]}…)"
        )
    if (
        baseline.pool_manifest is not None
        and candidate.pool_manifest is not None
        and candidate.pool_manifest != baseline.pool_manifest
    ):
        reasons.append(
            f"pool manifest differs ('{baseline_name}' {baseline.pool_manifest[:12]}… vs "
            f"'{arm_name}' {candidate.pool_manifest[:12]}…)"
        )
    shared = sorted(set(baseline.model_versions) & set(candidate.model_versions))
    for key in shared:
        baseline_value = baseline.model_versions[key]
        candidate_value = candidate.model_versions[key]
        if baseline_value != candidate_value:
            reasons.append(
                f"model '{key}' differs ('{baseline_name}' {baseline_value} vs '{arm_name}' "
                f"{candidate_value})"
            )
    return tuple(reasons)


async def _refuse_unrecordable_metrics(
    experiment: Experiment, *, deps: Dependencies, ctx: Context
) -> None:
    """Refuse before any arm is indexed if `experiment.metrics` names something no run at any of
    `experiment.cutoffs` would actually record. See the module docstring's own paragraph.
    """
    passages = tuple(
        RetrievedPassage(id=f"pre-flight-{position}") for position in range(experiment.top_k)
    )
    sample = RetrievalSample(
        query="weft eval experiment metric pre-flight",
        retrieved=passages,
        relevant_ids=frozenset({passages[0].id}),
    )
    subset = await score_retrieval_at_cutoffs(
        deps.registry, [sample], cutoffs=experiment.cutoffs, ctx=ctx
    )
    recorded = {name for name, outcome in subset.metrics.items() if isinstance(outcome, Produced)}
    # Ledger 32.14 scores a generating arm's answer too, so its names are recordable here.
    answered = await score_generation_gate_subset(
        deps.registry,
        [("pre-flight", GenerationSample(query="pre-flight", prediction="a", reference="a"))],
        ctx=ctx,
    )
    recorded |= {
        name for name, outcome in answered.metrics.items() if isinstance(outcome, Produced)
    }
    for name in experiment.metrics:
        if name not in recorded:
            valid_options = tuple(sorted(recorded))
            raise UnknownMetricNameError(
                f"'{name}' is not a metric name a run at cutoffs {experiment.cutoffs} would "
                f"ever record. Recorded metrics: "
                f"{', '.join(repr(option) for option in valid_options) or 'none'}.",
                valid_options=valid_options,
                name=name,
            )


def _corpus_name_for(document_root: Path, corpus_path: Path) -> str:
    """`corpus_path`, named as the document wrote it — relative to `document_root` (the
    experiment document's own resolved directory), POSIX-style. See the module docstring's own
    paragraph on why the resolved absolute path is never what a record persists.
    """
    return Path(os.path.relpath(corpus_path, start=document_root)).as_posix()


def _write_arm_pool(
    experiment: Experiment,
    arm: ExperimentArm,
    questions: tuple[Question, ...],
    identity: _ArmIdentity,
    result: IndexAndScoreResult,
    *,
    store: str,
) -> None:
    """Write `arm`'s captured pool beside `result`'s own run record — ledger task **40.2**.

    Called only for an arm whose `capture_pool` is set, after `index_and_score` returns; the
    pre-flight loop in `EvalExperimentCommand.run` has already refused any such arm naming no
    `query_pipeline` or one not ending in a `ContextPacker`, so `arm.query_pipeline` is a `str` here
    and `result.question_pools`/`result.store_rows` are never `None`.
    """
    if result.store_rows is None:
        raise ValueError(
            f"arm '{arm.name}' asked to capture a pool, but its run recorded no store row "
            "count — a capture with no row count is not a manifest."
        )
    pools = result.question_pools or {}
    query_rung = result.record.query_rung
    query_pipeline_identity = query_rung.identity if isinstance(query_rung, QueryRung) else ""
    manifest = PoolManifest(
        schema_version=POOL_MANIFEST_SCHEMA_VERSION,
        experiment=experiment.name,
        experiment_digest=experiment.digest,
        arm=arm.name,
        corpus_digest=identity.corpus_digest,
        question_set_digest=identity.question_set_digest,
        query_pipeline=cast(str, arm.query_pipeline),
        query_pipeline_identity=query_pipeline_identity,
        model_versions=dict(identity.model_versions),
        store=store,
        store_rows=result.store_rows,
        document_ids=result.document_ids,
        questions=tuple(
            PoolQuestion(
                id=question.id,
                text_sha256=text_sha256(question.text),
                relevant_sha256=relevant_set_sha256(question.relevant_documents),
                rule_fires=bool(find_anchors(question.text)),
                chunks=pools[question.id],
            )
            for question in questions
            if question.id in pools
        ),
    )
    write_pool_manifest(manifest, DEFAULT_RUNS_DIR / "pools" / f"{result.run_id}.json")


class EvalPlanArgs(BaseModel):
    """`weft eval plan <path>` — one positional, the experiment document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="the experiment document")


class ArmPlan(BaseModel):
    """What one arm would run: its pipelines, its repetitions, and the questions they multiply."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    arm: str
    pipeline: str
    query_pipeline: str | None
    repetitions: int
    questions: int
    executions: int


class CorpusPlan(BaseModel):
    """One `(ingest pipeline, corpus)` pair and the documents a run would walk for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str
    corpus: str
    documents: int


class EvalPlanCommandResult(CommandResult):
    """`weft eval plan`'s answer — the size of the run the document asks for, before it runs."""

    name: str
    digest: str
    arms: tuple[ArmPlan, ...]
    corpora: tuple[CorpusPlan, ...]


class EvalPlanCommand:
    """`weft eval plan <path>` — what the document would run, without running it. Task **38.12**.

    `38.6`'s spend was approved twice, and its *size* — the calls, the hours, the memory — was
    stated nowhere until a run had already been killed twice. This prints what the document and the
    corpus answer exactly: per arm the pipelines, the repetitions, the questions and the query
    executions they multiply to; per `(ingest pipeline, corpus)` the documents a run would walk.

    **It deliberately states nothing it would have to guess.** Model calls per role are not
    derivable — no stage declares that it calls one — seconds per call is a property of an account
    on a day, and the chunk count a batch holds is known only after chunking. Those three are the
    operator's to work out before `--yes`, which is what `.claude/hooks/guard_paid_measurement.py`
    asks at the command that starts a run. This command reads: it walks the corpus, writes no
    record, indexes nothing and never queries a store.
    """

    args_model: ClassVar[type[BaseModel]] = EvalPlanArgs
    result_model: ClassVar[type[CommandResult]] = EvalPlanCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "state the size of an experiment document without running it"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        plan_args = cast(EvalPlanArgs, args)
        deps = ctx.require(Dependencies)
        experiment = load_experiment(Path(plan_args.path))
        document_root = Path(plan_args.path).resolve().parent
        arms: list[ArmPlan] = []
        corpora: dict[tuple[str, Path], CorpusPlan] = {}
        for arm in experiment.arms:
            questions = read_question_set(experiment.questions_for(arm)).questions
            repetitions = experiment.repeats_for(arm)
            arms.append(
                ArmPlan(
                    arm=arm.name,
                    pipeline=arm.pipeline,
                    query_pipeline=arm.query_pipeline,
                    repetitions=repetitions,
                    questions=len(questions),
                    executions=len(questions) * repetitions,
                )
            )
            if arm.pool is not None:
                continue
            corpus_path = experiment.corpus_for(arm)
            key = (arm.pipeline, corpus_path)
            if key not in corpora:
                _resolved, _specs, documents = corpus_documents(
                    corpus_path,
                    pipeline=arm.pipeline,
                    registry=deps.registry,
                    reports=deps.reports,
                    contributions=deps.contributions,
                )
                corpora[key] = CorpusPlan(
                    pipeline=arm.pipeline,
                    corpus=_corpus_name_for(document_root, corpus_path),
                    documents=len(documents),
                )
        return Produced(
            value=EvalPlanCommandResult(
                name=experiment.name,
                digest=experiment.digest,
                arms=tuple(arms),
                corpora=tuple(corpora.values()),
            )
        )


class EvalExperimentCommand:
    """`weft eval experiment` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = EvalExperimentArgs
    result_model: ClassVar[type[CommandResult]] = EvalExperimentCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _EVAL_EXPERIMENT_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        experiment_args = cast(EvalExperimentArgs, args)
        deps = ctx.require(Dependencies)
        experiment = load_experiment(Path(experiment_args.path))
        resumed = _incomplete_invocation(experiment)
        invocation, written = resumed if resumed is not None else (uuid.uuid4().hex, {})

        document_labels = (
            document_labels_from_manifest(str(experiment.manifest))
            if experiment.manifest is not None
            else None
        )

        # Task 40.2's second half — loaded once, before any arm runs, so a bad manifest file is
        # refused before anything else does.
        pools: dict[str, LoadedPool] = {
            arm.name: load_pool_manifest(arm.pool)
            for arm in experiment.arms
            if arm.pool is not None
        }

        for arm in experiment.arms:
            _refuse_unscorable_arm(arm, deps=deps)

        await _refuse_unrecordable_metrics(experiment, deps=deps, ctx=ctx)

        question_sets: dict[str, QuestionSet] = {
            arm.name: read_question_set(experiment.questions_for(arm)) for arm in experiment.arms
        }

        identities: dict[str, _ArmIdentity] = {
            arm.name: await _arm_identity(
                experiment, arm, question_sets[arm.name], deps=deps, pool=pools.get(arm.name)
            )
            for arm in experiment.arms
        }

        baseline_arm = experiment.arms[0]
        baseline = identities[baseline_arm.name]
        for arm in experiment.arms[1:]:
            reasons = _arm_incomparable_reasons(
                baseline_arm.name, baseline, arm.name, identities[arm.name]
            )
            if reasons:
                raise IncomparableArmsError(
                    f"arm '{arm.name}' is not comparable to '{baseline_arm.name}': "
                    f"{'; '.join(reasons)}.",
                    arm=arm.name,
                    reasons=reasons,
                )

        document_root = Path(experiment_args.path).resolve().parent
        indexed_keys: set[tuple[str, Path]] = set()
        runs: list[ExperimentRunRef] = []
        for arm in experiment.arms:
            pool = pools.get(arm.name)
            corpus_path = experiment.corpus_for(arm)
            questions = question_sets[arm.name].questions
            index_key = (arm.pipeline, corpus_path)
            for repetition in range(1, experiment.repeats_for(arm) + 1):
                found = written.get((arm.name, repetition))
                if found is not None:
                    runs.append(ExperimentRunRef(arm=arm.name, repetition=repetition, run_id=found))
                    continue
                already_indexed = index_key in indexed_keys
                result = await index_and_score(
                    deps,
                    ctx=ctx,
                    path=corpus_path,
                    pipeline=arm.pipeline,
                    corpus_name=_corpus_name_for(document_root, corpus_path),
                    questions=questions,
                    document_labels=document_labels,
                    top_k=experiment.top_k,
                    cutoffs=experiment.cutoffs,
                    query_pipeline=arm.query_pipeline,
                    reuse_index=already_indexed,
                    refuse_foreign_documents=True,
                    reprocess=False,
                    batch_size=experiment.index_batch_size,
                    capture_pool=arm.capture_pool,
                    pool=pool,
                    experiment=ExperimentRun(
                        name=experiment.name,
                        digest=experiment.digest,
                        invocation=invocation,
                        arm=arm.name,
                        repetition=repetition,
                        pool_manifest=pool.sha256 if pool is not None else None,
                    ),
                )
                if pool is None:
                    indexed_keys.add(index_key)
                runs.append(
                    ExperimentRunRef(arm=arm.name, repetition=repetition, run_id=result.run_id)
                )
                if arm.capture_pool:
                    _write_arm_pool(
                        experiment,
                        arm,
                        questions,
                        identities[arm.name],
                        result,
                        store=deps.services.store,
                    )

        return Produced(
            value=EvalExperimentCommandResult(
                name=experiment.name,
                digest=experiment.digest,
                invocation=invocation,
                runs=tuple(runs),
            )
        )


def _incomplete_invocation(
    experiment: Experiment, *, directory: Path = DEFAULT_RUNS_DIR
) -> tuple[str, dict[tuple[str, int], str]] | None:
    """The newest invocation of this document that is missing a record, and what it already wrote.

    Task **38.16**: `38.6` ran six times, and three of its lost runs had written valid records for
    whole arms that the next run paid for again. Re-running a document therefore continues its
    newest invocation — newest by the latest `recorded_at` among its records — when some arm ×
    repetition in `repeats_for` has no record, and starts a new one when that invocation is
    complete, so a deliberate re-run is still a fresh measurement.
    """
    invocations: dict[str, dict[tuple[str, int], tuple[str, str]]] = {}
    for run_id, record in all_run_records(directory):
        run = record.experiment
        if run is None or run.digest != experiment.digest:
            continue
        invocations.setdefault(run.invocation, {})[(run.arm, run.repetition)] = (
            run_id,
            record.recorded_at,
        )
    if not invocations:
        return None
    invocation, found = max(
        invocations.items(), key=lambda item: max(recorded for _, recorded in item[1].values())
    )
    expected = {
        (arm.name, repetition)
        for arm in experiment.arms
        for repetition in range(1, experiment.repeats_for(arm) + 1)
    }
    if expected <= set(found):
        return None
    return invocation, {key: run_id for key, (run_id, _) in found.items()}


def register_eval_experiment_command(registrar: PackRegistrar) -> None:
    """Register `eval experiment` — called from `weft_cli.commands.register`, right after
    `register_eval_baseline_command`, never from a second entry point.
    """
    registrar.add(Command, "eval experiment", EvalExperimentCommand)
    registrar.add(Command, "eval plan", EvalPlanCommand)


__all__ = [
    "ArmPlan",
    "CorpusPlan",
    "EvalExperimentArgs",
    "EvalExperimentCommand",
    "EvalExperimentCommandResult",
    "EvalPlanArgs",
    "EvalPlanCommand",
    "EvalPlanCommandResult",
    "ExperimentRunRef",
    "IncomparableArmsError",
    "UnscorableArmError",
    "register_eval_experiment_command",
]
