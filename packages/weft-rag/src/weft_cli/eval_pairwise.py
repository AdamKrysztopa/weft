"""`weft eval pairwise <experiment> --baseline A --arm B` — task **44.43b**.

The verb over `weft_eval.pairwise.compare_arms`: it reads the experiment document, the question
text from the baseline arm's own question set, and the records beside the document, judges every
requested criterion through the command path's `LLM`, writes a pairwise record under
`<experiment>/pairwise/`, and prints the table. It calls a model and writes a file, so its
permission class is `write` — `weft_cli.eval_replay.EvalReplayCommand`'s own module docstring is
this command's `READ` sibling, mirrored here on the identical structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_eval.experiment import Experiment, ExperimentArm, load_experiment
from weft_eval.pairwise import (
    PairwiseCriterion,
    compare_arms,
    render_pairwise_table,
    write_pairwise_record,
)
from weft_eval.question_set import read_question_sets
from weft_eval.run_record import load_run_record
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Outcome, Produced

_EVAL_PAIRWISE_HELP = (
    "judges two arms' recorded answers head to head on GraphRAG's criteria, each pair in both "
    "orders, and writes a pairwise record — calls the 'grade' role's model"
)


class EvalPairwiseArgs(BaseModel):
    """Parameters of `weft eval pairwise <experiment> --baseline A --arm B`.

    `criterion` names one criterion to judge; every criterion, in `PairwiseCriterion`'s own
    declaration order, is judged when it is omitted — `str | None` wrapping a `StrEnum`,
    `weft_cli.commands.SourcesListArgs.status`'s own shape, which `weft_cli.argparse_gen`
    already knows how to turn into a `choices=`-bounded flag.
    `runs` defaults to the runs directory beside the document, `EvalReplayArgs`'s own default.
    `--baseline`/`--arm` naming the same arm is refused here, before a document is even read —
    a pairwise judgement needs two different arms to compare.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment: str = Field(description="the experiment document")
    baseline: str = Field(description="the baseline arm's name")
    arm: str = Field(description="the arm to compare against the baseline")
    criterion: PairwiseCriterion | None = Field(
        default=None,
        description="which criterion to judge; every criterion, in order, when omitted",
    )
    runs: str | None = Field(
        default=None,
        description=(
            "the directory of run records; the runs directory beside the document when omitted"
        ),
    )
    invocation: str | None = Field(
        default=None,
        description="which invocation to judge, when more than one is complete",
    )
    limit: int | None = Field(
        default=None,
        gt=0,
        description=(
            "judge only the first this-many paired questions; every paired question when omitted"
        ),
    )

    @model_validator(mode="after")
    def _baseline_and_arm_differ(self) -> EvalPairwiseArgs:
        if self.baseline == self.arm:
            raise ValueError(
                f"--baseline and --arm both name '{self.arm}' — a pairwise judgement compares "
                "two different arms."
            )
        return self


class EvalPairwiseCommandResult(CommandResult):
    """Hands the renderer finished markdown and where the paid record was written."""

    markdown: str
    record_path: str


def _arm_by_name(experiment: Experiment, name: str) -> ExperimentArm | None:
    return next((candidate for candidate in experiment.arms if candidate.name == name), None)


class EvalPairwiseCommand:
    """`weft eval pairwise` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = EvalPairwiseArgs
    result_model: ClassVar[type[CommandResult]] = EvalPairwiseCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _EVAL_PAIRWISE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Judge `args.baseline` against `args.arm`, write the record and render the table.

        Args:
            args: The parsed `EvalPairwiseArgs`.
            ctx: The command's context — read for `LLM` (through `compare_arms`/`judge_pair`)
                and for `run_id`, which makes the written record's own filename unique.

        Returns:
            `Produced` with the `EvalPairwiseCommandResult`.

        Raises:
            weft_eval.pairwise.UnknownArmError: `args.baseline`/`args.arm` names no arm of the
                document.
            weft_eval.pairwise.UnrecordedAnswersError: a chosen record kept no answer text.
            weft_eval.falsify.UnpairableRecordsError: the two arms did not answer the same
                questions of the same corpus.
        """
        pairwise_args = cast(EvalPairwiseArgs, args)
        experiment_path = Path(pairwise_args.experiment)
        experiment = load_experiment(experiment_path)
        baseline_arm = _arm_by_name(experiment, pairwise_args.baseline)
        question_paths = (
            experiment.questions_for(baseline_arm)
            if baseline_arm is not None
            else experiment.questions
        )
        questions = {
            question.id: question.text for question in read_question_sets(question_paths).questions
        }
        runs_dir = (
            Path(pairwise_args.runs)
            if pairwise_args.runs is not None
            else experiment_path.with_suffix("") / "runs"
        )
        records = (
            [load_run_record(path) for path in sorted(runs_dir.glob("*.json"))]
            if runs_dir.is_dir()
            else []
        )
        criteria = (
            (pairwise_args.criterion,)
            if pairwise_args.criterion is not None
            else tuple(PairwiseCriterion)
        )
        record = await compare_arms(
            experiment,
            records,
            questions=questions,
            baseline=pairwise_args.baseline,
            arm=pairwise_args.arm,
            criteria=criteria,
            ctx=ctx,
            invocation=pairwise_args.invocation,
            limit=pairwise_args.limit,
        )
        record_path = (
            experiment_path.with_suffix("")
            / "pairwise"
            / f"{pairwise_args.baseline}-vs-{pairwise_args.arm}-{ctx.run_id}.json"
        )
        write_pairwise_record(record, record_path)
        return Produced(
            value=EvalPairwiseCommandResult(
                markdown=render_pairwise_table(record), record_path=str(record_path)
            )
        )


def register_eval_pairwise_command(registrar: PackRegistrar) -> None:
    """Make `weft eval pairwise` resolvable as an ordinary registered command.

    Register `eval pairwise` — called from `weft_cli.commands.register`, right after
    `register_eval_replay_command`.
    """
    registrar.add(Command, "eval pairwise", EvalPairwiseCommand)


__all__ = [
    "EvalPairwiseArgs",
    "EvalPairwiseCommand",
    "EvalPairwiseCommandResult",
    "register_eval_pairwise_command",
]
