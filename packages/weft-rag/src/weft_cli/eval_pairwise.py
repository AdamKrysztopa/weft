"""`weft eval pairwise <experiment> --baseline A --arm B` — task **44.43b**.

The verb over `weft_eval.pairwise.compare_arms`: it reads the experiment document, the question
text from the baseline arm's own question set, and the records beside the document, judges every
requested criterion through the command path's `LLM`, writes a pairwise record under
`<experiment>/pairwise/`, and prints the table. It calls a model and writes a file, so its
permission class is `write` — `weft_cli.eval_replay.EvalReplayCommand`'s own module docstring is
this command's `READ` sibling, mirrored here on the identical structure.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_cli.eval_records import records_of_experiment, with_unread
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_eval.experiment import Experiment, ExperimentArm, load_experiment
from weft_eval.pairwise import (
    SHIPPED_CRITERIA,
    Criterion,
    compare_arms,
    load_criteria,
    render_pairwise_table,
    resolve_criterion,
    write_pairwise_record,
)
from weft_eval.question_set import read_question_sets
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Outcome, Produced

_EVAL_PAIRWISE_HELP = (
    "judges two arms' recorded answers head to head on GraphRAG's criteria, each pair in both "
    "orders, and writes a pairwise record — calls the 'grade' role's model"
)


class EvalPairwiseArgs(BaseModel):
    """Parameters of `weft eval pairwise <experiment> --baseline A --arm B`.

    `criteria_file` names a TOML file of `[[criterion]]` tables — a name and a definition each —
    that replaces the four shipped criteria as the set available; `criterion` names one of the
    available set to judge, every one of them, in order, being judged when it is omitted. A name
    the set does not hold is refused naming the ones it does, at run time, since the set is not
    known until the file is read.
    `runs` defaults to the runs directory beside the document, `EvalReplayArgs`'s own default.
    `--baseline`/`--arm` naming the same arm is refused here, before a document is even read —
    a pairwise judgement needs two different arms to compare.
    `only` restricts judging to the ids a file names, one per line, keeping the question set's
    own order — a named id the set does not have is ignored, and a file naming none of the set's
    ids is a `ValueError` rather than a silent empty run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment: str = Field(description="the experiment document")
    baseline: str = Field(description="the baseline arm's name")
    arm: str = Field(description="the arm to compare against the baseline")
    criterion: str | None = Field(
        default=None,
        description="which criterion to judge; every criterion, in order, when omitted",
    )
    criteria_file: str | None = Field(
        default=None,
        description=(
            "a TOML file of [[criterion]] tables (name, definition) to judge instead of the "
            "four shipped criteria"
        ),
    )
    runs: str | None = Field(
        default=None,
        description=(
            "the directory of run records; `<document>/runs`, beside the document without its "
            "suffix, when omitted — where `weft eval experiment` writes them"
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
    only: str | None = Field(
        default=None,
        description="a file of question ids, one per line; judge only those",
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


def _restrict_to_named_questions(
    questions: Mapping[str, str], only_path: Path
) -> Mapping[str, str]:
    """Keep only the ids `only_path` names, one per line, in `questions`' own order.

    An id the file names that `questions` does not is ignored; a file naming none of `questions`
    is a `ValueError` naming `only_path`, since a silent empty run would look like agreement.
    """
    wanted = {
        line.strip() for line in only_path.read_text(encoding="utf-8").splitlines() if line.strip()
    }
    restricted = {
        question_id: text for question_id, text in questions.items() if question_id in wanted
    }
    if not restricted:
        raise ValueError(
            f"'{only_path}' names no question id present in the experiment's own question set."
        )
    return restricted


def _criteria_to_judge(args: EvalPairwiseArgs) -> tuple[Criterion, ...]:
    """The shipped criteria or the file's, narrowed to the one `--criterion` names, if any."""
    available = (
        load_criteria(Path(args.criteria_file))
        if args.criteria_file is not None
        else SHIPPED_CRITERIA
    )
    if args.criterion is None:
        return available
    return (resolve_criterion(args.criterion, available),)


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
            weft_eval.pairwise.UnknownCriterionError: `args.criterion` names no available
                criterion.
            weft_eval.pairwise.InvalidCriteriaError: `args.criteria_file` is unreadable or holds a
                malformed or duplicated criterion.
            weft_eval.pairwise.UnrecordedAnswersError: a chosen record kept no answer text.
            weft_eval.falsify.UnpairableRecordsError: the two arms did not answer the same
                questions of the same corpus.
        """
        pairwise_args = cast(EvalPairwiseArgs, args)
        criteria = _criteria_to_judge(pairwise_args)
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
        if pairwise_args.only is not None:
            questions = _restrict_to_named_questions(questions, Path(pairwise_args.only))
        read = records_of_experiment(experiment, experiment_path, pairwise_args.runs)
        records = [record for _, record in read.records]
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
                markdown=with_unread(render_pairwise_table(record), read),
                record_path=str(record_path),
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
