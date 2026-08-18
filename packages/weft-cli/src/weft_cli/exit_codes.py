"""`ExitCode` — the meaningful process exit values `docs/03-cli.md` → *Output* specifies.

"Exit codes are meaningful, because a CLI that always exits 0 cannot be used
in CI." Five values, and the split between 3 and 4 is G3's policy-versus-
resolution distinction, restated here as the mechanical fact `weft_cli.cli`
dispatches on:

- **3** covers policy refusals of both kinds a Phase 0 command can hit: a
  pipeline naming a plugin from a `REFUSED` pack. (The other G3 policy case —
  an `ask`-class command with no TTY — never arises in Phase 0: nothing built
  here is `overwrite` or `destroy`, see `weft_cli.permissions`.)
- **4** stays with genuine resolution failure: a name no pack provides, or one
  lost to a `FAILED`, `PARTIAL` or `ALLOWED_NOT_INSTALLED` report.

Both are computed *before* a pipeline is ever resolved — see
`weft_cli.registry_bootstrap.require_active` — so `4` is also the fallback for
`weft_kernel.registry.UnknownPluginError` and
`weft_kernel.runner.PipelineResolutionError`, should either occur despite that
check having passed.
"""

from enum import IntEnum


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
