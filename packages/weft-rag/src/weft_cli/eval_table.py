"""`weft eval table <experiment>` — ledger task **38.1**: the evidence table, printed.

`weft_eval.evidence` computes and renders it; this module is the command that reads the records
under `runs/` and an experiment document from disk and prints the markdown — so an operator
regenerates a committed table with

    weft eval table eval/experiments/<name>.toml > eval/experiments/<name>/table.md

**Reads only, on purpose.** `weft eval experiment` (task 38.0) is what writes a run record; this
command opens no store, indexes nothing, and its `permission_class` is `READ` — the identical
footing `weft eval compare`/`weft trace` already hold for a command that only folds records
already on disk into a printed answer, never `WRITE`, which task 38.0's own `eval experiment`
carries instead.

Every refusal `weft_eval.evidence.evidence_table` raises — `IncompleteExperimentError`,
`AmbiguousInvocationError` — propagates from `run` exactly as raised, on the same footing
`weft_cli.eval_experiment.EvalExperimentCommand` already holds for `IncomparableArmsError`: the
registration seam (`weft_cli.exit_codes.exit_code_for`) is where a `WeftError` becomes an exit
code, never this command.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_eval.evidence import evidence_table, render_evidence_table
from weft_eval.experiment import load_experiment
from weft_eval.run_record import load_run_record
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Outcome, Produced

_EVAL_TABLE_HELP = (
    "print the evidence table an experiment's own records produce: per arm and metric the "
    "paired mean difference over questions with its bootstrap interval and the verdict against "
    "the baseline's between-repetition spread, beside latency and tokens per query — reads "
    "only, writes nothing"
)


class EvalTableArgs(BaseModel):
    """`weft eval table <experiment>` — the document, the runs directory to read records from,
    and an invocation to name when more than one of this document is complete.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment: str = Field(description="the experiment document")
    runs: str = Field(default="runs", description="the directory of run records to read")
    invocation: str | None = Field(
        default=None,
        description="which invocation to build the table from, when more than one is complete",
    )


class EvalTableCommandResult(CommandResult):
    """`weft eval table`'s whole answer — the rendered markdown, exactly as `weft_eval.evidence.
    render_evidence_table` wrote it.
    """

    markdown: str


class EvalTableCommand:
    """`weft eval table` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = EvalTableArgs
    result_model: ClassVar[type[CommandResult]] = EvalTableCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _EVAL_TABLE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        table_args = cast(EvalTableArgs, args)
        experiment = load_experiment(Path(table_args.experiment))
        runs_dir = Path(table_args.runs)
        records = (
            [load_run_record(path) for path in sorted(runs_dir.glob("*.json"))]
            if runs_dir.is_dir()
            else []
        )
        table = evidence_table(experiment, records, invocation=table_args.invocation)
        return Produced(value=EvalTableCommandResult(markdown=render_evidence_table(table)))


def register_eval_table_command(registrar: PackRegistrar) -> None:
    """Register `eval table` — called from `weft_cli.commands.register`, right after
    `register_eval_experiment_command`.
    """
    registrar.add(Command, "eval table", EvalTableCommand)


__all__ = [
    "EvalTableArgs",
    "EvalTableCommand",
    "EvalTableCommandResult",
    "register_eval_table_command",
]
