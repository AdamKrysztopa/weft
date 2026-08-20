"""`ExitCode` — the meaningful process exit values `docs/03-cli.md` → *Output* specifies.

"Exit codes are meaningful, because a CLI that always exits 0 cannot be used
in CI." Five values, and the split between 3 and 4 is G3's policy-versus-
resolution distinction, restated here as the mechanical fact `weft_cli.cli`
dispatches on:

- **3** covers policy refusals of both kinds G3 names: a pipeline naming a
  plugin from a `REFUSED` pack, and — since task 3.3 — an `overwrite`/
  `destroy`-class command with no TTY to confirm in, or one an interactive
  caller declined. Both are `weft_cli.commands.CommandRefusalError`, carrying
  this code as data; see `weft_cli.confirm` for the second case's own gate,
  called from `weft_cli.cli.run_command` immediately before a `Command` runs.
- **4** stays with genuine resolution failure: a name no pack provides, or one
  lost to a `FAILED`, `PARTIAL` or `ALLOWED_NOT_INSTALLED` report.

Both are computed *before* a pipeline is ever resolved — see
`weft_cli.registry_bootstrap.require_active` — so `4` is also the fallback for
`weft_kernel.registry.UnknownPluginError` and
`weft_kernel.runner.PipelineResolutionError`, should either occur despite that
check having passed.
"""

from enum import IntEnum
from typing import Final

from weft_cli.config_surface import UnknownConfigKeyError
from weft_cli.pipeline_catalogue import (
    ContributedPipelineNameCollisionError,
    DuplicatePipelineNameError,
    MalformedPipelineError,
    PipelineDocumentError,
    ProjectPipelineNameCollisionError,
)
from weft_kernel.errors import WeftError
from weft_kernel.registry import UnknownPluginError
from weft_kernel.runner import PipelineResolutionError


class ExitCode(IntEnum):
    """`docs/03-cli.md` → *Output*: "0 success, 1 operation failed, 2 bad usage, 3 refused for
    permissions, 4 pipeline failed to resolve." `2` is never assigned by this module — `argparse`
    itself calls `sys.exit(2)` on a usage error, before any command runs, so `weft_cli.cli` adds
    nothing on top of it.
    """

    SUCCESS = 0
    OPERATION_FAILED = 1
    BAD_USAGE = 2
    POLICY_REFUSED = 3
    RESOLUTION_FAILED = 4


#: Every `WeftError` type that maps to exit 4 despite carrying no `PipelineResolutionError`
#: in its own inheritance — task 1.13, widened by task 3.7. All are deliberately *not*
#: `PipelineResolutionError` subclasses (see `weft_kernel.resolution`'s own module docstring
#: for `UnknownPluginError`, `weft_cli.pipeline_catalogue`'s for the three document-level
#: ones and `ProjectPipelineNameCollisionError` beside them — a document that will not even
#: validate, or two sources naming the same pipeline, "has no resolved parent and no
#: distributions to name", so filing either under the family "would hand the failure-mode
#: ratchet one already-documented name to hide behind"; `weft_cli.config_surface.
#: UnknownConfigKeyError` the identical reasoning one surface over — a key `weft config`
#: does not read has no pipeline, no stage and no distribution to name either), yet
#: `docs/03-cli.md` -> *Output* puts every one of them on the exit-4 side of the split: "a
#: name no pack provides" for `UnknownPluginError`, "fix the pipeline"/"fix the command" for
#: the rest. Named explicitly rather than derived, unlike the family walk `exit_code_for`
#: performs below — there is no shared base to walk for a group this small and this
#: deliberately disjoint. (`UnknownPipelineNameError` needs no entry here: it already
#: inherits `PipelineResolutionError` directly, so `isinstance` below already catches it.)
_ALSO_RESOLUTION_FAILED: Final[tuple[type[WeftError], ...]] = (
    UnknownPluginError,
    PipelineDocumentError,
    MalformedPipelineError,
    DuplicatePipelineNameError,
    ContributedPipelineNameCollisionError,
    ProjectPipelineNameCollisionError,
    UnknownConfigKeyError,
)


def exit_code_for(exc: WeftError) -> ExitCode:
    """The one place `docs/03-cli.md`'s exit-code split is decided from a caught exception.

    Task 1.13, `docs/02-extension-model.md` §3 → *When resolution fails*: "The CLI maps the
    whole family to exit code 4." Before this function existed that mapping was written out
    by hand, twice, inside `handle_index` and `handle_ask` (`except (UnknownPluginError,
    PipelineResolutionError): ... except WeftError: ...`) — and a third caller reaching for
    the same pattern was exactly how `weft_cli.pipeline_catalogue`'s family (task 1.9, never
    reachable through the CLI as shipped, so never actually reached this bug) would have
    fallen through the generic branch to exit `1` the moment a real handler called it, rather
    than the `4` `docs/03-cli.md` reserves for "fix the pipeline". One function, one truth:
    every `PipelineResolutionError` subclass (walked by `isinstance`, so a class defined
    after this function is written still matches — no list to fall out of step with) and
    every name in `_ALSO_RESOLUTION_FAILED` map to `RESOLUTION_FAILED`; every other
    `WeftError` maps to `OPERATION_FAILED`, "something failed" rather than "fix the pipeline".

    **`weft_cli.route_ask.NoRouterPipelineError` is checked by a local import, task 2.8.**
    `exit_codes.py` is imported at `cli.py`'s own module scope — every command needs it,
    `weft --version` included — so a module-level import of `weft_cli.route_ask` here
    would pull `weft_retrieve`, `weft_generate`, `weft_llm` and `weft_prompts` into every
    command's own import path, exactly what fitness function 8(b) refuses. By the time
    this branch can ever be reached, `handle_route` has already imported `route_ask`
    itself (`weft_cli.cli`'s own local-import convention for every pack-touching module),
    so the import below costs nothing beyond a `sys.modules` lookup in the one case it runs.
    """
    if isinstance(exc, (PipelineResolutionError, *_ALSO_RESOLUTION_FAILED)):
        return ExitCode.RESOLUTION_FAILED
    from weft_cli.route_ask import NoRouterPipelineError

    if isinstance(exc, NoRouterPipelineError):
        return ExitCode.RESOLUTION_FAILED
    return ExitCode.OPERATION_FAILED
