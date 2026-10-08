"""`weft eval claims check` and `render` — tasks **44.31**, **44.32**.

`check` recomputes every claim from its committed records; `render` prints the rung table of
`manual/evidence.md` §3 generated from those same claims and the shipped rungs, so a page that
says a rung helps is the page of a claim that was just recomputed.

Reads `eval/claims/*.toml` (or `directory`), recomputes each records claim's paired interval from
the experiment and run records it names, and prints one row per claim. A claim whose stated status
its own records do not support is refused, all of them named at once; a stale claim is a warning in
its row. Reads only: opens no store, calls no model, `permission_class` is `READ`, the footing
`weft_cli.eval_replay` already holds. `ClaimDocumentError`, `UnknownClaimFeatureError` and
`UnresolvedClaimArmError` propagate as raised.

`pin` (task **44.62**) writes each records claim's evidence fingerprint into its file — what
`weft_eval.fingerprint` compares — after the claim's records have been recomputed and found to
support it, all of them or none. It is the one claims command that writes, and the diff it leaves is
the act of saying *the records still speak for these pipelines*.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.claims_live import live_evidence
from weft_cli.pipeline_catalogue import load_contributed
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_engine.registry_bootstrap import Dependencies, resolution_dependencies
from weft_eval.claims import Claim, ClaimDocumentError, load_claims, pin_claim
from weft_eval.claims_check import ClaimCheck, ClaimMismatchError, check_claim
from weft_eval.claims_render import render_claims_table
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
    stated = f"{check.stated} ({check.stated_verdict})" if check.stated_verdict else check.stated
    cells = [f"`{check.claim_id}`", str(stated)]
    if check.mean is None or check.low is None or check.high is None:
        return "| " + " | ".join([*cells, "not reproducible from committed records", "", ""]) + " |"
    reading = (
        f"{check.mean:+.3f} ({check.low:+.3f} to {check.high:+.3f}), n {check.n}, "
        f"margin {check.margin}"
    )
    checked = "asserted" if check.derived is None else f"recomputed: {check.verdict}"
    note = f"{check.staleness}: {check.stale}" if check.stale else ""
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
        entries = _checked(cast(EvalClaimsCheckArgs, args), resolution_dependencies())
        header = "| claim | stated | checked | paired difference | note |\n|---|---|---|---|---|"
        rows = [_row(check) for _, check in entries]
        return Produced(value=EvalClaimsCheckResult(markdown="\n".join([header, *rows])))


def _claims_of(args: EvalClaimsCheckArgs) -> tuple[Claim, ...]:
    directory = Path(args.directory)
    return load_claims(directory if directory.is_absolute() else Path(args.root) / directory)


def _checked(args: EvalClaimsCheckArgs, deps: Dependencies) -> list[tuple[Claim, ClaimCheck]]:
    """Every claim in `args.directory` with what recomputing it found; every mismatch at once."""
    root = Path(args.root)
    entries: list[tuple[Claim, ClaimCheck]] = []
    refused: list[str] = []
    for claim in _claims_of(args):
        live = live_evidence(claim, root=root, deps=deps)
        try:
            entries.append((claim, check_claim(claim, root=root, live=live)))
        except ClaimMismatchError as mismatch:
            refused.append(str(mismatch))
    if refused:
        raise ClaimMismatchError("\n".join(refused))
    return entries


def _shipped_rungs(deps: Dependencies) -> tuple[str, ...]:
    """Every pipeline an active pack contributed — the rungs a claim can be about."""
    return tuple(sorted(load_contributed(deps.reports)))


class EvalClaimsRenderCommand:
    """`weft eval claims render` — the evidence page's rung table, generated from the claims."""

    args_model: ClassVar[type[BaseModel]] = EvalClaimsCheckArgs
    result_model: ClassVar[type[CommandResult]] = EvalClaimsCheckResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = (
        "print the rung table of manual/evidence.md section 3 from the evidence claims, each "
        "recomputed from its committed records; a shipped rung with no claim reads never"
    )

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Render the table; a claim its records do not support refuses it, as `check` does."""
        del ctx
        deps = resolution_dependencies()
        entries = _checked(cast(EvalClaimsCheckArgs, args), deps)
        table = render_claims_table(entries, shipped_rungs=_shipped_rungs(deps))
        return Produced(value=EvalClaimsCheckResult(markdown=table))


class EvalClaimsPinArgs(EvalClaimsCheckArgs):
    """Parameters of `weft eval claims pin`: the one claim to pin, then the check's own."""

    claim: str = Field(description="the id of the claim to pin")


class EvalClaimsPinCommand:
    """`weft eval claims pin <claim>` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = EvalClaimsPinArgs
    result_model: ClassVar[type[CommandResult]] = EvalClaimsCheckResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = (
        "pin one evidence claim to the pipelines, judge prompt and profiler it is validated "
        "against, after recomputing it from its committed records; `claims check` then reports "
        "whether any has changed since. Read the diff: pinning says the records still speak "
        "for the pipelines as they are"
    )

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Pin one claim; refuse, writing nothing, if it is unsupported or cannot be resolved."""
        del ctx
        typed = cast(EvalClaimsPinArgs, args)
        claims = {claim.id: claim for claim in _claims_of(typed)}
        if typed.claim not in claims:
            raise ClaimDocumentError(
                f"no claim '{typed.claim}' in {typed.directory}. "
                f"Claims: {', '.join(sorted(claims))}."
            )
        claim = claims[typed.claim]
        root = Path(typed.root)
        live = live_evidence(claim, root=root, deps=resolution_dependencies())
        check_claim(claim, root=root, live=live)
        if live.fingerprint is None:
            raise ClaimMismatchError(f"claim '{claim.id}' cannot be pinned: {live.unresolved}")
        directory = Path(typed.directory)
        pin_claim(
            (directory if directory.is_absolute() else root / directory) / f"{claim.id}.toml",
            live.fingerprint,
        )
        return Produced(
            value=EvalClaimsCheckResult(
                markdown=f"pinned `{claim.id}` to `{live.fingerprint.digest()}`"
            )
        )


def register_eval_claims_command(registrar: PackRegistrar) -> None:
    """Make `weft eval claims check`, `render` and `pin` resolvable as registered commands."""
    registrar.add(Command, "eval claims check", EvalClaimsCheckCommand)
    registrar.add(Command, "eval claims render", EvalClaimsRenderCommand)
    registrar.add(Command, "eval claims pin", EvalClaimsPinCommand)


__all__ = [
    "EvalClaimsCheckArgs",
    "EvalClaimsCheckCommand",
    "EvalClaimsCheckResult",
    "EvalClaimsPinArgs",
    "EvalClaimsPinCommand",
    "EvalClaimsRenderCommand",
    "register_eval_claims_command",
]
