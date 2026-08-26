"""`ExitCode` — the meaningful process exit values `docs/03-cli.md` → *Output* specifies.

**Task 6.20 (G13) moves the class itself to `weft_command.render`, re-exported here.** A
renderer a third-party pack registers through `weft_kernel.discovery.PackRegistrar.
add_renderer` has to answer in this same vocabulary — `weft delete` and `weft index` both
compute their own exit code from their own result's fields, so a pack's own renderer needs
the identical five values, and a pack implementing `Command` must not depend on `weft-cli`
for them (see `weft_command.render`'s own module docstring for the argument in full).
`exit_code_for` below stays exactly where it is: it maps *exceptions*, a wider family than a
renderer's own answer, and this module is still the one place `docs/03-cli.md`'s exit-code
split is decided from a caught error.

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

from typing import Final

from weft_cli.config_surface import UnknownConfigKeyError
from weft_cli.pipeline_catalogue import (
    ContributedPipelineNameCollisionError,
    DuplicatePipelineNameError,
    MalformedPipelineError,
    PipelineDocumentError,
    ProjectPipelineNameCollisionError,
)
from weft_command import ExitCode as ExitCode
from weft_kernel.errors import WeftError
from weft_kernel.registry import UnknownPluginError
from weft_kernel.runner import PipelineResolutionError

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
#: `weft_cli.eval_commands.UnknownRunIdError` belongs on this same exit-4 side by the
#: identical reasoning — a run id `weft eval compare`/`weft trace` does not hold is FF12's
#: family, "fix what you typed" rather than "something failed" — but it is **not** named
#: here: `weft_cli.eval_commands` imports `weft_cli.ingest`, which imports `weft_extract`/
#: `weft_chunk`/`weft_embed`/`weft_store` at its own module scope, and this module is
#: imported at `cli.py`'s own module scope, unconditionally, for `weft --version` too — the
#: identical shape `weft_cli.route_ask.NoRouterPipelineError` is already checked by a local
#: import for below, applied here rather than invented a second way.
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

    **`weft_cli.eval_commands.UnknownRunIdError`, task 4.6 — the identical local-import
    shape, one caller further.** `weft_cli.eval_commands` pulls in `weft_cli.ingest`
    (`weft_extract`/`weft_chunk`/`weft_embed`/`weft_store`) and `weft_eval`
    (`weft-llm`/`weft-prompts`/`rouge-score`) at its own module scope — a module-level
    import here would cost `weft --version` all of that, the exact regression
    `NoRouterPipelineError`'s own paragraph already refuses one caller up. By the time this
    branch runs, `weft_cli.eval_commands.EvalCompareCommand`/`TraceCommand` have already
    been resolved and raised, so this import is a `sys.modules` lookup, not a fresh one.

    **`weft_eval.offline.UnknownMetricNameError`, task 4.7 — the identical shape again.**
    `weft eval metrics <name>` naming a metric neither `GenerationMetric` nor `RetrievalMetric`
    registered is "fix what you typed", FF12's family, exactly as an unknown run id is —
    `weft_eval.offline.MetricNeedsCredentialsError`, by contrast, names a *real* metric that
    cannot run right now, "something failed" rather than "fix the pipeline", so it is
    deliberately left off this list to fall through to `OPERATION_FAILED` below, the identical
    footing `EmptyCorpusError`/`IncomparableRunsError` already have.
    """
    if isinstance(exc, (PipelineResolutionError, *_ALSO_RESOLUTION_FAILED)):
        return ExitCode.RESOLUTION_FAILED
    from weft_cli.eval_commands import UnknownRunIdError
    from weft_cli.route_ask import NoRouterPipelineError
    from weft_eval.offline import UnknownMetricNameError

    if isinstance(exc, (NoRouterPipelineError, UnknownRunIdError, UnknownMetricNameError)):
        return ExitCode.RESOLUTION_FAILED
    return ExitCode.OPERATION_FAILED
