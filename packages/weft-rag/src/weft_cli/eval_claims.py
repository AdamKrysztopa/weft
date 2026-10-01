"""`weft eval claims check` — task **44.31**: recompute every claim from its committed records.

Reads `eval/claims/*.toml` (or `directory`), recomputes each records claim's paired interval from
the experiment and run records it names, and prints one row per claim. A claim whose stated status
its own records do not support is refused, all of them named at once; a stale claim is a warning in
its row. Reads only: opens no store, calls no model, `permission_class` is `READ`, the footing
`weft_cli.eval_replay` already holds. `ClaimDocumentError`, `UnknownClaimFeatureError` and
`UnresolvedClaimArmError` propagate as raised.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_eval.claims import load_claims
from weft_eval.claims_check import ClaimCheck, ClaimMismatchError, check_claim
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Outcome, Produced

_HELP = (
    "recompute every evidence claim from the committed run records it names and refuse a stated "
    "status those records do not support — reads only, calls no model"
)


class EvalClaimsCheckArgs(BaseModel):
    """Parameters of `weft eval claims check`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    directory: str = Field(default="eval/claims", description="the directory of claim files")
    root: str = Field(
        default=".", description="the directory a claim's experiment and runs paths are relative to"
    )


class EvalClaimsCheckResult(CommandResult):
    """Finished markdown, so the table is never reformatted on the way out."""

    markdown: str


def _row(check: ClaimCheck) -> str:
    cells = [f"`{check.claim_id}`", str(check.stated)]
    if check.mean is None or check.low is None or check.high is None:
        return "| " + " | ".join([*cells, "not reproducible from committed records", "", ""]) + " |"
    reading = (
        f"{check.mean:+.3f} ({check.low:+.3f} to {check.high:+.3f}), n {check.n}, "
        f"margin {check.margin}"
    )
    checked = "asserted" if check.derived is None else f"recomputed: {check.verdict}"
    note = f"stale: {check.stale}" if check.stale else ""
    return "| " + " | ".join([*cells, checked, reading, note]) + " |"


class EvalClaimsCheckCommand:
    """`weft eval claims check` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = EvalClaimsCheckArgs
    result_model: ClassVar[type[CommandResult]] = EvalClaimsCheckResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Check every claim in the directory; raise one error naming every mismatch."""
        del ctx
        check_args = cast(EvalClaimsCheckArgs, args)
        root = Path(check_args.root)
        directory = Path(check_args.directory)
        claims = load_claims(directory if directory.is_absolute() else root / directory)
        rows: list[str] = []
        refused: list[str] = []
        for claim in claims:
            try:
                rows.append(_row(check_claim(claim, root=root)))
            except ClaimMismatchError as mismatch:
                refused.append(str(mismatch))
        if refused:
            raise ClaimMismatchError("\n".join(refused))
        header = "| claim | stated | checked | paired difference | note |\n|---|---|---|---|---|"
        return Produced(value=EvalClaimsCheckResult(markdown="\n".join([header, *rows])))


def register_eval_claims_command(registrar: PackRegistrar) -> None:
    """Make `weft eval claims check` resolvable as an ordinary registered command."""
    registrar.add(Command, "eval claims check", EvalClaimsCheckCommand)


__all__ = [
    "EvalClaimsCheckArgs",
    "EvalClaimsCheckCommand",
    "EvalClaimsCheckResult",
    "register_eval_claims_command",
]
