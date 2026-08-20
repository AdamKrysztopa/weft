"""Turning a `Command`'s `Outcome[CommandResult]` into stdout, stderr and an exit code.

Task **3.2**'s own "minimal human renderer" — `docs/03-cli.md` → *Two modes, one
implementation*: "a `Command` returns a typed result and never writes to a stream." Something
still has to write to one, and this module is that something, for exactly one reader: a human at
a terminal. `--json`'s newline-delimited event sink and the REPL's own renderer are **task 3.4 and
3.6 — not built here**, per this task's own brief; this is the smallest renderer that reproduces,
byte for byte, what the five retired `handle_*` functions in `weft_cli.cli` used to print
directly, now computed from data instead of interleaved with the logic that produced it.

**Why exit code lives here and not on the result.** `weft_command.contract.CommandResult` is
capability-agnostic — it does not know `weft_cli.exit_codes.ExitCode` exists, on the same
footing G1 holds the kernel to for a capability name. `IndexCommandResult.summary.failed > 0`
still has to become exit code `1` somewhere, and "the CLI renders it" (`03`'s governing rule) is
exactly the licence to compute that here, from the typed fields a command actually returned,
rather than smuggling a process-exit concept into the contract to avoid one `isinstance` in this
module. This mirrors `weft_cli.exit_codes.exit_code_for`'s own placement for exceptions: one
function owns the whole mapping from "what happened" to "what the process reports."

**Two things a result never carries.** Rank order in `weft ask`'s text output, never a raw
score (`docs/03-cli.md` → *Output*, *Score display* — `AskHit.score` still travels, unrendered,
for `--format json`), and the fixed sentence for an empty search (`"no matching passages
found."`), reproduced exactly rather than reworded.

**`streamed`, task 3.11 — the fix for `weft route`'s inherited double-print.** Task 3.6's own
report flagged it and named this task as the owner: a routed answer's text was printed twice —
once live, through `PrintingSink`/`JsonSink` as the generating stage streamed it, and once more
here, in full, after the run finished. `render_outcome`'s new keyword-only `streamed` carries
whether *this run's own* `TokenSink` already showed the answer (`weft_cli.cli.run_command` reads
`deps.token_sink.wrote_anything` — the real sink, not the `_EmissionTrackingSink` wrapper that
tracks a different, role-blind fact for a different repair; see `weft_cli.sinks.PrintingSink`'s
own docstring) — `_render_ask` below is the one renderer that reads it, to omit the already-shown
text rather than the whole answer: `--quiet` (`NullSink`, which carries no such attribute — read
with `getattr(..., False)`, `weft_kernel.runner._flush_of`'s own defensive-duck-typing idiom)
still gets the full text here, because nothing streamed it live and G6's "`--quiet` suppresses
progress but keeps the result" still has to hold.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from weft_cli.commands import (
    AskCommandResult,
    CommandRefusalError,
    IndexCommandResult,
    InitCommandResult,
    PluginsDoctorCommandResult,
    PluginsListCommandResult,
)
from weft_cli.config_commands import ConfigGetCommandResult, ConfigSetCommandResult
from weft_cli.exit_codes import ExitCode, exit_code_for
from weft_cli.output import AskFormat
from weft_cli.pipeline_commands import (
    PipelineDeriveCommandResult,
    PipelineDiffCommandResult,
    PipelineListCommandResult,
    PipelineShowCommandResult,
    PipelineValidateCommandResult,
)
from weft_cli.plugins_report import render_doctor, render_list
from weft_command.contract import CommandResult
from weft_kernel.errors import WeftError
from weft_kernel.payload import NothingToProduce, Outcome, Produced


@dataclass(frozen=True, slots=True)
class Rendered:
    """What `main` writes, and with what exit code — `None` means nothing prints on that stream."""

    stdout: str | None
    stderr: str | None
    exit_code: ExitCode


def render_outcome(outcome: Outcome[CommandResult], *, streamed: bool = False) -> Rendered:
    """A successfully-run command's `Outcome`, rendered — the `Produced`/`NothingToProduce`/
    `Failed` vocabulary every contract answers in, `02` §1's own three-way decision applied to
    a `Command`'s own result.

    None of the built-ins ever return `NothingToProduce` or `Failed` today — each one that
    would report "nothing" (an ask with no hits) still `Produced`s a result stating that fact, so
    the text a human reads keeps deciding *how* to say "nothing", the same way `render_results`
    always did — but a third party's `Command` is free to use either, and this function answers
    both honestly rather than assuming only `Produced` is reachable.

    `streamed` — see the module docstring's own task-3.11 paragraph — defaults to `False`, the
    safe reading for every caller that does not pass it (every existing test included): "assume
    nothing streamed, so show the full result" is the failure mode that loses no text, where the
    opposite default would risk silently dropping an answer a caller forgot to report as shown.
    """
    if isinstance(outcome, Produced):
        return _render_result(outcome.value, streamed=streamed)
    if isinstance(outcome, NothingToProduce):
        return Rendered(stdout=outcome.reason, stderr=None, exit_code=ExitCode.SUCCESS)
    return Rendered(stdout=None, stderr=outcome.reason, exit_code=ExitCode.OPERATION_FAILED)


def render_refusal(exc: WeftError) -> Rendered:
    """A `WeftError` raised before or during `run()` — a `CommandRefusalError`'s own exit code,
    or `weft_cli.exit_codes.exit_code_for`'s mapping for every other `WeftError`.
    """
    if isinstance(exc, CommandRefusalError):
        return Rendered(stdout=None, stderr=str(exc), exit_code=exc.exit_code)
    return Rendered(stdout=None, stderr=str(exc), exit_code=exit_code_for(exc))


def _render_plugins_list(result: PluginsListCommandResult) -> Rendered:
    return Rendered(stdout=render_list(result.reports), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_plugins_doctor(result: PluginsDoctorCommandResult) -> Rendered:
    stdout = render_doctor(result.reports, result.displaced, result.unconsulted_pins)
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_init(result: InitCommandResult) -> Rendered:
    return Rendered(stdout=f"wrote {result.path}.", stderr=None, exit_code=ExitCode.SUCCESS)


def _render_pipeline_validate(result: PipelineValidateCommandResult) -> Rendered:
    stdout = f"'{result.name}' resolves cleanly: {result.stage_count} stage(s)."
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_config_set(result: ConfigSetCommandResult) -> Rendered:
    stdout = f"set {result.key} = {result.value} in {result.path}."
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_unknown(result: CommandResult) -> Rendered:
    # The honest floor for a result type this module was not written against — a future
    # stranger's result gets a truthful structured dump rather than a silent `pass`.
    return Rendered(stdout=result.model_dump_json(), stderr=None, exit_code=ExitCode.SUCCESS)


#: `(result type, renderer)`, tried in order — a dispatch table rather than an `isinstance`
#: chain, so `_render_result` stays one loop no matter how many `CommandResult` subclasses
#: this module ends up knowing about (`ruff`'s own complexity check is what asked for this
#: shape once task 3.7 doubled the count it has to tell apart). Every renderer is wrapped in
#: a `lambda` that `cast`s its argument down to the specific result type it was written
#: against — the same defensive-cast idiom every `Command.run` in `weft_cli.commands` already
#: uses for its own `args` parameter — so each `_render_*` function below keeps the precise
#: signature its own tests already call it with, rather than every one of them widening to
#: `CommandResult` purely to satisfy this table. A stranger's result matches nothing here and
#: falls through to `_render_unknown`, exactly as it did before this table existed.
#: `AskCommandResult` is deliberately absent here — it is the one result type `streamed`
#: matters for, so `_render_result` special-cases it ahead of this table rather than widening
#: every other renderer's own lambda to a parameter it would never use.
_RENDERERS: tuple[tuple[type[CommandResult], Callable[[CommandResult], Rendered]], ...] = (
    (IndexCommandResult, lambda r: _render_index(cast(IndexCommandResult, r))),
    (PluginsListCommandResult, lambda r: _render_plugins_list(cast(PluginsListCommandResult, r))),
    (
        PluginsDoctorCommandResult,
        lambda r: _render_plugins_doctor(cast(PluginsDoctorCommandResult, r)),
    ),
    (InitCommandResult, lambda r: _render_init(cast(InitCommandResult, r))),
    (
        PipelineListCommandResult,
        lambda r: _render_pipeline_list(cast(PipelineListCommandResult, r)),
    ),
    (
        PipelineShowCommandResult,
        lambda r: _render_pipeline_show(cast(PipelineShowCommandResult, r)),
    ),
    (
        PipelineDeriveCommandResult,
        lambda r: _render_pipeline_derive(cast(PipelineDeriveCommandResult, r)),
    ),
    (
        PipelineValidateCommandResult,
        lambda r: _render_pipeline_validate(cast(PipelineValidateCommandResult, r)),
    ),
    (
        PipelineDiffCommandResult,
        lambda r: _render_pipeline_diff(cast(PipelineDiffCommandResult, r)),
    ),
    (ConfigGetCommandResult, lambda r: _render_config_get(cast(ConfigGetCommandResult, r))),
    (ConfigSetCommandResult, lambda r: _render_config_set(cast(ConfigSetCommandResult, r))),
)


def _render_result(result: CommandResult, *, streamed: bool) -> Rendered:
    if isinstance(result, AskCommandResult):
        return _render_ask(result, streamed=streamed)
    for result_type, renderer in _RENDERERS:
        if isinstance(result, result_type):
            return renderer(result)
    return _render_unknown(result)


def _render_index(result: IndexCommandResult) -> Rendered:
    summary = result.summary
    stored = "unknown" if result.stored_count is None else str(result.stored_count)
    stdout = (
        f"produced {summary.produced}, nothing to produce {summary.nothing_to_produce}, "
        f"failed {summary.failed}. nodes now stored: {stored}."
    )
    stderr = (
        "\n".join(f"  failed: {reason}" for reason in summary.failed_reasons)
        if summary.failed_reasons
        else None
    )
    exit_code = ExitCode.SUCCESS if summary.failed == 0 else ExitCode.OPERATION_FAILED
    return Rendered(stdout=stdout, stderr=stderr, exit_code=exit_code)


def _render_ask(result: AskCommandResult, *, streamed: bool) -> Rendered:
    """`weft ask`'s own two shapes — see `AskCommandResult`'s own docstring for why exactly
    one of `answer`/`hits` is ever populated, and this module's own task-3.11 paragraph for
    `streamed`, which only the `answer` branch reads.
    """
    if result.answer is not None:
        # The routed/named-pipeline shape — task 3.11 folds `weft route`'s own retired
        # `_render_route` in here, unchanged in every respect but one: when `streamed` is
        # `True`, `PrintingSink`/`JsonSink` already showed this exact text live, so it is
        # left out rather than printed a second time (`weft_cli.cli.run_command`'s own
        # `deps.token_sink.wrote_anything` is what decides). `--quiet`/a non-streaming sink
        # still gets the full text, because nothing showed it yet.
        lines = [f"routed to: {result.pipeline_name}"]
        if not streamed:
            lines.append(result.answer.text)
        lines.extend(
            f"  [{citation.marker}] {citation.uri}" for citation in result.answer.citations
        )
        return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)

    if result.format is AskFormat.JSON:
        # No empty-result special case on this side — a caller reading structured output
        # detects "nothing found" from an empty `hits`, and would otherwise have to match a
        # sentence that is free to be reworded. `AskResult`/`AskHit` are `weft_cli.ask`'s own
        # shape; rebuilding the envelope here keeps this function the only caller of
        # `render_results_json`'s field layout without importing the retrieval results a
        # second time.
        from weft_cli.ask import AskResult

        payload = AskResult(
            question=result.question, top_k=result.top_k, hits=result.hits
        ).model_dump_json()
        return Rendered(stdout=payload, stderr=None, exit_code=ExitCode.SUCCESS)

    if not result.hits:
        return Rendered(
            stdout="no matching passages found.", stderr=None, exit_code=ExitCode.SUCCESS
        )

    lines = [f"{hit.rank}. {hit.content}" for hit in result.hits]
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_pipeline_list(result: PipelineListCommandResult) -> Rendered:
    stdout = "\n".join(result.names) if result.names else "no pipelines known."
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_pipeline_show(result: PipelineShowCommandResult) -> Rendered:
    """`weft pipeline show` — task 3.7's own bar: every stage's provenance, every var's
    final value, and — the two a pre-G2 `show` could never have printed at all, because
    the fields did not exist before task 1.11 — unapplied operators and unplaced
    contributions, each explicit even when empty rather than a line that silently
    disappears the day one finally has something to say (`docs/03-cli.md`: "printing them
    is the only way they are visible").
    """
    resolved = result.resolved
    lines = [f"pipeline: {resolved.name}", "vars:"]
    lines.extend(f"  {name} = {resolved.vars[name]}" for name in sorted(resolved.vars))
    if not resolved.vars:
        lines.append("  (none)")

    lines.append("stages:")
    for stage in resolved.stages:
        dumped = stage.model_dump(mode="json")
        lines.append(
            f"  {stage.id}: {stage.contract}:{stage.use} "
            f"(distribution: {stage.distribution}, provenance: {stage.provenance})"
        )
        if dumped["config"]:
            lines.append(f"    with: {dumped['config']}")
        if stage.applies_to:
            lines.append(f"    applies_to: {dumped['applies_to']}")
        if stage.fallback:
            lines.append(f"    fallback: {', '.join(stage.fallback)}")

    unapplied = ", ".join(resolved.unapplied_operators) or "(none)"
    unplaced = ", ".join(resolved.unplaced_contributions) or "(none)"
    lines.append(f"unapplied operators: {unapplied}")
    lines.append(f"unplaced contributions: {unplaced}")
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_pipeline_derive(result: PipelineDeriveCommandResult) -> Rendered:
    stdout = (
        f"wrote {result.path} — '{result.name}' extends '{result.parent}'. Run "
        f"`weft pipeline validate {result.name}` next."
    )
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_pipeline_diff(result: PipelineDiffCommandResult) -> Rendered:
    """`weft pipeline diff` — the diff itself is proven exact by `weft_cli.pipeline_diff.
    diff_resolved` (structural comparison of two resolved values, never rendered text);
    this function only turns that already-exact answer into lines for a human.
    """
    diff = result.diff
    if diff.identical:
        stdout = f"'{diff.a_name}' and '{diff.b_name}' resolve identically."
        return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)

    lines = [f"'{diff.a_name}' vs '{diff.b_name}':"]
    lines.extend(f"  + {stage.id} ({stage.contract}:{stage.use})" for stage in diff.added_stages)
    lines.extend(f"  - {stage.id} ({stage.contract}:{stage.use})" for stage in diff.removed_stages)
    lines.extend(
        f"  ~ {change.id}: {change.a.use} -> {change.b.use}" for change in diff.changed_stages
    )
    lines.extend(f"  var {var.name}: {var.a!r} -> {var.b!r}" for var in diff.var_changes)
    if diff.unapplied_operators_changed:
        lines.append("  unapplied operators differ")
    if diff.unplaced_contributions_changed:
        lines.append("  unplaced contributions differ")
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_config_get(result: ConfigGetCommandResult) -> Rendered:
    lines: list[str] = []
    for entry in result.entries:
        line = f"{entry.key} = {entry.value}"
        if result.show_origin:
            line += f"  (origin: {entry.origin.value})"
        lines.append(line)
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)
