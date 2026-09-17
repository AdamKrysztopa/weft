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

**A metric no run would record is refused before anything is indexed — repair R38.2.** The names a
run actually records at `experiment.top_k` are asked of the registered metrics themselves
(`weft_eval.harness.score_retrieval_gate_subset` against one synthetic sample), never assumed from
the document's own `metrics =` list: a typo (`recal@5` beside `recall@10`, neither of them a name
any run has ever written) used to pass every other refusal and run the whole, paid experiment,
rendering `unjudgeable` naming nothing an operator could act on.

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
    document_labels_from_manifest,
    index_and_score,
    model_versions_of,
)
from weft_cli.ingest import content_hashes_of, corpus_documents
from weft_cli.route_ask import resolve_named_pipeline
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_engine.registry_bootstrap import Dependencies
from weft_eval.contract import RetrievalSample, RetrievedPassage
from weft_eval.experiment import Experiment, ExperimentArm, load_experiment
from weft_eval.harness import score_retrieval_gate_subset
from weft_eval.offline import UnknownMetricNameError
from weft_eval.question_set import QuestionSet, read_question_set
from weft_eval.run_record import ExperimentRun, corpus_identity
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.resolution import ResolvedPipeline

_EVAL_EXPERIMENT_HELP = (
    "run every arm of an experiment document (eval/experiments/*.toml) for every repetition, "
    "through the identical index-and-score path 'weft eval run' uses, and persist one run "
    "record per arm and repetition — refuses before indexing anything if two arms are not "
    "comparable by corpus digest, question-set digest or model version"
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


def _arm_identity(
    experiment: Experiment, arm: ExperimentArm, question_set: QuestionSet, *, deps: Dependencies
) -> _ArmIdentity:
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
        model_versions=dict(model_versions_of(resolved, roles=deps.llm.roles)),
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
    """Refuse before any arm is indexed if `experiment.metrics` names something no run at
    `experiment.top_k` would actually record. See the module docstring's own paragraph.
    """
    passages = tuple(
        RetrievedPassage(id=f"pre-flight-{position}") for position in range(experiment.top_k)
    )
    sample = RetrievalSample(
        query="weft eval experiment metric pre-flight",
        retrieved=passages,
        relevant_ids=frozenset({passages[0].id}),
    )
    subset = await score_retrieval_gate_subset(
        deps.registry, [sample], top_k=experiment.top_k, ctx=ctx
    )
    recorded = {name for name, outcome in subset.metrics.items() if isinstance(outcome, Produced)}
    for name in experiment.metrics:
        if name not in recorded:
            valid_options = tuple(sorted(recorded))
            raise UnknownMetricNameError(
                f"'{name}' is not a metric name a run at top_k={experiment.top_k} would ever "
                f"record. Recorded metrics: "
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
        invocation = uuid.uuid4().hex

        document_labels = (
            document_labels_from_manifest(str(experiment.manifest))
            if experiment.manifest is not None
            else None
        )

        for arm in experiment.arms:
            if arm.query_pipeline is None:
                continue
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

        await _refuse_unrecordable_metrics(experiment, deps=deps, ctx=ctx)

        question_sets: dict[str, QuestionSet] = {
            arm.name: read_question_set(experiment.questions_for(arm)) for arm in experiment.arms
        }

        identities: dict[str, _ArmIdentity] = {
            arm.name: _arm_identity(experiment, arm, question_sets[arm.name], deps=deps)
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
            corpus_path = experiment.corpus_for(arm)
            questions = question_sets[arm.name].questions
            index_key = (arm.pipeline, corpus_path)
            for repetition in range(1, experiment.repeats_for(arm) + 1):
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
                    query_pipeline=arm.query_pipeline,
                    reuse_index=already_indexed,
                    refuse_foreign_documents=True,
                    reprocess=False,
                    batch_size=experiment.index_batch_size,
                    experiment=ExperimentRun(
                        name=experiment.name,
                        digest=experiment.digest,
                        invocation=invocation,
                        arm=arm.name,
                        repetition=repetition,
                    ),
                )
                indexed_keys.add(index_key)
                runs.append(
                    ExperimentRunRef(arm=arm.name, repetition=repetition, run_id=result.run_id)
                )

        return Produced(
            value=EvalExperimentCommandResult(
                name=experiment.name,
                digest=experiment.digest,
                invocation=invocation,
                runs=tuple(runs),
            )
        )


def register_eval_experiment_command(registrar: PackRegistrar) -> None:
    """Register `eval experiment` — called from `weft_cli.commands.register`, right after
    `register_eval_baseline_command`, never from a second entry point.
    """
    registrar.add(Command, "eval experiment", EvalExperimentCommand)


__all__ = [
    "EvalExperimentArgs",
    "EvalExperimentCommand",
    "EvalExperimentCommandResult",
    "ExperimentRunRef",
    "IncomparableArmsError",
    "UnscorableArmError",
    "register_eval_experiment_command",
]
