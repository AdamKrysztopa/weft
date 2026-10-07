"""`weft eval replay <experiment>` — task **44.6a**: prints what a per-question choice would score.

`weft_eval.replay` computes and renders the table; this module is the command that reads the
records beside an experiment document from disk and prints the markdown. The runs directory
defaults to the one beside the document (`<experiment>/runs`, `experiment` with its suffix
stripped), never the working directory — `R44.3` is `weft eval table` getting that wrong, and
this command does not repeat it.

**Reads only, on purpose.** The identical footing `weft_cli.eval_table.EvalTableCommand` already
holds: this command opens no store, indexes nothing, calls no model, and its `permission_class`
is `READ`.

Every refusal `weft_eval.replay.replay`/`weft_eval.evidence.select_invocation` raises —
`IncompleteExperimentError`, `AmbiguousInvocationError`, `UnpairableRecordsError`,
`UnscoredMetricError` — propagates from `run` exactly as raised, on `EvalTableCommand`'s own
footing: the registration seam (`weft_cli.exit_codes.exit_code_for`) is where a `WeftError`
becomes an exit code, never this command.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.eval_records import records_of_experiment
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_eval.experiment import load_experiment
from weft_eval.replay import render_replay_table, replay
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Outcome, Produced

_EVAL_REPLAY_HELP = (
    "print what any per-question choice among an experiment's arms would have scored, from its "
    "recorded scores: every arm, the oracle and the best arm's own-repetition oracle, each "
    "paired against the best arm — reads only, calls no model"
)


class EvalReplayArgs(BaseModel):
    """Parameters of `weft eval replay <experiment>`.

    `weft eval replay <experiment>` — the document, the metric, the runs directory to read
    records from, and an invocation to name when more than one of this document is complete.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment: str = Field(description="the experiment document")
    metric: str | None = Field(
        default=None,
        description="the metric to replay; the document's first declared metric when omitted",
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
        description="which invocation to replay, when more than one is complete",
    )


class EvalReplayCommandResult(CommandResult):
    """Hands the renderer finished markdown, so the table is never reformatted on the way out."""

    markdown: str


class EvalReplayCommand:
    """`weft eval replay` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = EvalReplayArgs
    result_model: ClassVar[type[CommandResult]] = EvalReplayCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _EVAL_REPLAY_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Render the replay table for one experiment from the run records on disk.

        Args:
            args: The parsed `EvalReplayArgs`.
            ctx: Unused; the table reads only files.

        Returns:
            The produced `EvalReplayCommandResult`.
        """
        del ctx
        replay_args = cast(EvalReplayArgs, args)
        experiment_path = Path(replay_args.experiment)
        experiment = load_experiment(experiment_path)
        records = records_of_experiment(experiment, experiment_path, replay_args.runs)
        metric = replay_args.metric if replay_args.metric is not None else experiment.metrics[0]
        table = replay(experiment, records, metric=metric, invocation=replay_args.invocation)
        return Produced(value=EvalReplayCommandResult(markdown=render_replay_table(table)))


def register_eval_replay_command(registrar: PackRegistrar) -> None:
    """Make `weft eval replay` resolvable as an ordinary registered command.

    Register `eval replay` — called from `weft_cli.commands.register`, right after
    `register_eval_table_command`.
    """
    registrar.add(Command, "eval replay", EvalReplayCommand)


__all__ = [
    "EvalReplayArgs",
    "EvalReplayCommand",
    "EvalReplayCommandResult",
    "register_eval_replay_command",
]
