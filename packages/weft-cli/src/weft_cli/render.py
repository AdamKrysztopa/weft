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

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

from weft_cli.commands import (
    AskCommandResult,
    CommandRefusalError,
    DeleteCommandResult,
    IndexCommandResult,
    InitCommandResult,
    PluginsDoctorCommandResult,
    PluginsListCommandResult,
    ReconcileCommandResult,
)
from weft_cli.config_commands import ConfigGetCommandResult, ConfigSetCommandResult
from weft_cli.error_envelope import build_error_envelope
from weft_cli.eval_commands import (
    EvalCompareCommandResult,
    EvalMetricsCommandResult,
    EvalRunCommandResult,
    MetricComparison,
    TraceCommandResult,
)
from weft_cli.exit_codes import ExitCode, exit_code_for
from weft_cli.output import AskFormat
from weft_cli.pipeline_commands import (
    PipelineDeriveCommandResult,
    PipelineDiffCommandResult,
    PipelineListCommandResult,
    PipelineShowCommandResult,
    PipelineValidateCommandResult,
)
from weft_cli.pipeline_diff import PipelineDiff
from weft_cli.plugins_report import render_doctor, render_list
from weft_cli.reconcile import ReconcileEstimateOutcome, ReconcileOutcome
from weft_command.contract import CommandResult
from weft_eval.run_record import MetricRunResult
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


def render_refusal(exc: WeftError, *, as_json: bool = False) -> Rendered:
    """A `WeftError` raised before or during `run()` — a `CommandRefusalError`'s own exit code,
    or `weft_cli.exit_codes.exit_code_for`'s mapping for every other `WeftError`.

    **`as_json`, task 5.2d.** `docs/README.md` decision log, S6/G9: CLI error prose is not
    promised, but a structured channel is in its place — the `WeftError` subclass name as
    failure identity, `valid_options` where the error has them, and the human string as a
    `rendered` field (`docs/09-release.md` §3). Before this task every failure printed
    `str(exc)` to stderr regardless of `--json`, so none of the 78 `valid_options` sites this
    distribution's raise sites compute ever reached a script except as a sentence it would
    have had to parse. `as_json=True` — set by `weft_cli.cli.run_command` from
    `isinstance(deps.token_sink, JsonSink)`, the same global flag `docs/03-cli.md` -> *Output*
    already uses to decide the run's whole scripting contract — builds the envelope
    (`weft_cli.error_envelope.build_error_envelope`) instead and puts it on `stdout`, with
    nothing on `stderr`: the envelope is the whole answer a script reads, the same way
    `weft_cli.sinks.JsonSink` already puts every event on `stdout` rather than splitting a run
    across two streams. The default, `as_json=False`, is every existing caller and every human
    invocation: the exit-code decision itself is unchanged either way, computed once, here,
    exactly as before.
    """
    exit_code = exc.exit_code if isinstance(exc, CommandRefusalError) else exit_code_for(exc)
    if as_json:
        envelope = build_error_envelope(exc, exit_code=exit_code)
        return Rendered(stdout=envelope.model_dump_json(), stderr=None, exit_code=exit_code)
    return Rendered(stdout=None, stderr=str(exc), exit_code=exit_code)


def _render_plugins_list(result: PluginsListCommandResult) -> Rendered:
    return Rendered(stdout=render_list(result.reports), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_plugins_doctor(result: PluginsDoctorCommandResult) -> Rendered:
    stdout = render_doctor(
        result.reports,
        result.displaced,
        result.unconsulted_pins,
        result.tracing,
        result.skew,
        result.unreachable_contributions,
    )
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_init(result: InitCommandResult) -> Rendered:
    return Rendered(stdout=f"wrote {result.path}.", stderr=None, exit_code=ExitCode.SUCCESS)


def _render_pipeline_validate(result: PipelineValidateCommandResult) -> Rendered:
    stdout = f"'{result.name}' resolves cleanly: {result.stage_count} stage(s)."
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_config_set(result: ConfigSetCommandResult) -> Rendered:
    stdout = f"set {result.key} = {result.value} in {result.path}."
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_delete(result: DeleteCommandResult) -> Rendered:
    """`weft delete`'s whole answer — one line per participant, and the failures on stderr.

    Task **5.1a**'s property is that a participant that fails is *named*, so every participant
    is listed whether it succeeded or not: reading only the failures would leave an operator
    unable to tell a fan-out of one from a fan-out of five. The exit code follows
    `_render_index`'s own rule — the run happened, and a non-zero code reports that part of it
    did not — rather than a refusal, because a partial deletion is a real event with a real
    result, not a command that declined to start.
    """
    if not result.participants:
        return Rendered(
            stdout=(f"nothing installed holds data for '{result.source_id}'; nothing was deleted."),
            stderr=None,
            exit_code=ExitCode.SUCCESS,
        )
    lines = [f"'{result.source_id}' — {len(result.participants)} participant(s):"]
    lines += [
        f"  {outcome.plugin} ({outcome.distribution}): "
        + ("failed" if outcome.failed else f"{outcome.node_count} node(s) removed")
        for outcome in result.participants
    ]
    failures = result.failed
    stderr = (
        "\n".join(
            f"  failed: {outcome.plugin} ({outcome.distribution}) — {outcome.error}"
            for outcome in failures
        )
        or None
    )
    exit_code = ExitCode.SUCCESS if not failures else ExitCode.OPERATION_FAILED
    return Rendered(stdout="\n".join(lines), stderr=stderr, exit_code=exit_code)


def _render_reconcile(result: ReconcileCommandResult) -> Rendered:
    """`weft reconcile`'s whole answer — task **5.1b**, and `full`'s own cost block, 5.1c's.

    Three facts a summary must not lose, which is why every participant gets a line. What each
    one removed and backfilled. Whether it **converged** — `remaining` non-zero means the pass
    was interrupted and another is owed, which is a different thing from a failure and reads as
    one if it is folded into the same count. And a failure, named, on stderr.

    An unconverged participant exits non-zero for the same reason a failed one does: the
    command did not finish the job, and a script that read `0` here would go on believing the
    corpus had converged.

    **`result.estimates`, task 5.1c — printed first, ahead of every other line, and only when
    non-empty.** `docs/03-cli.md` → *Command surface*: "full states its cost before it spends
    it." `ReconcileCommand.run` only ever populates `estimates` for `full` (never `repair`,
    which has nothing to backfill), so this function needs no mode check of its own — an
    empty tuple already means "nothing to print here." Ordering the estimate lines first is
    what "before it spends it" means for a result rendered once, after `run()` returns: the
    number was computed, and is shown, ahead of what converging actually did.
    """
    estimate_lines = [line for outcome in result.estimates for line in _estimate_lines(outcome)]
    if result.dry_run:
        head = (
            f"mode '{result.mode.value}' would run against {len(result.would_ask)} participant(s):"
        )
        if not result.would_ask:
            return Rendered(
                stdout="nothing installed can reconcile.", stderr=None, exit_code=ExitCode.SUCCESS
            )
        body = estimate_lines or [f"  {label}" for label in result.would_ask]
        return Rendered(stdout="\n".join([head, *body]), stderr=None, exit_code=ExitCode.SUCCESS)
    if not result.participants:
        return Rendered(
            stdout="nothing installed can reconcile; nothing to converge.",
            stderr=None,
            exit_code=ExitCode.SUCCESS,
        )
    lines = [f"mode '{result.mode.value}' — {len(result.participants)} participant(s):"]
    lines += estimate_lines
    lines += [
        f"  {outcome.plugin} ({outcome.distribution}): {_reconcile_line(outcome)}"
        for outcome in result.participants
    ]
    failures = result.failed
    stderr = (
        "\n".join(
            f"  failed: {outcome.plugin} ({outcome.distribution}) — {outcome.error}"
            for outcome in failures
        )
        or None
    )
    finished = not failures and not result.unconverged
    exit_code = ExitCode.SUCCESS if finished else ExitCode.OPERATION_FAILED
    return Rendered(stdout="\n".join(lines), stderr=stderr, exit_code=exit_code)


def _reconcile_line(outcome: ReconcileOutcome) -> str:
    if outcome.report is None:
        return "failed"
    report = outcome.report
    counts = f"examined {report.examined}, removed {report.removed}, backfilled {report.backfilled}"
    if report.converged:
        return counts
    return f"{counts} — interrupted, {report.remaining} left; run again"


def _estimate_lines(outcome: ReconcileEstimateOutcome) -> tuple[str, ...]:
    """One participant's own cost, in `docs/03-cli.md`'s own worked-example shape:

    ```
    weft-graph: 4,312 nodes have no graph data
                backfill will make ~4,312 model calls
    ```

    A second, indented line names the model-call cost only when there is one to name —
    `model_calls == 0` is the honest floor every first-party store reports today (`node
    stores hold no derived state to build), and a bare "~0 model calls" would say nothing a
    reader could not already tell from the first line.
    """
    if outcome.estimate is None:
        return (f"  {outcome.plugin} ({outcome.distribution}): estimate failed — {outcome.error}",)
    head = f"  {outcome.plugin} ({outcome.distribution}): {outcome.estimate.description}"
    if outcome.estimate.model_calls <= 0:
        return (head,)
    indent = " " * len(head[: head.index(": ") + 2])
    return (head, f"{indent}backfill will make ~{outcome.estimate.model_calls} model calls")


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
    (DeleteCommandResult, lambda r: _render_delete(cast(DeleteCommandResult, r))),
    (
        ReconcileCommandResult,
        lambda r: _render_reconcile(cast(ReconcileCommandResult, r)),
    ),
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
    (EvalRunCommandResult, lambda r: _render_eval_run(cast(EvalRunCommandResult, r))),
    (EvalCompareCommandResult, lambda r: _render_eval_compare(cast(EvalCompareCommandResult, r))),
    (TraceCommandResult, lambda r: _render_trace(cast(TraceCommandResult, r))),
    (
        EvalMetricsCommandResult,
        lambda r: _render_eval_metrics(cast(EvalMetricsCommandResult, r)),
    ),
)


def _render_result(result: CommandResult, *, streamed: bool) -> Rendered:
    if isinstance(result, AskCommandResult):
        return _render_ask(result, streamed=streamed)
    for result_type, renderer in _RENDERERS:
        if isinstance(result, result_type):
            return renderer(result)
    return _render_unknown(result)


def _render_index(result: IndexCommandResult) -> Rendered:
    """`weft index`'s whole answer, plus the automatic post-index reconciliation pass, task
    **5.1c**. `result.reconcile` is rendered through `_render_reconcile` itself — one renderer
    for both `weft reconcile`'s own result and this command's automatic pass, so a participant
    line, a cost estimate or a failure can never read differently depending on which command
    produced it. `None` only when `run_index` itself raised before the pass could run, so there
    is nothing to append; every successful run reports one, even an empty one.
    """
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
    if result.reconcile is not None:
        reconciled = _render_reconcile(result.reconcile)
        if reconciled.stdout:
            stdout = f"{stdout}\n{reconciled.stdout}"
        if reconciled.stderr:
            stderr = f"{stderr}\n{reconciled.stderr}" if stderr else reconciled.stderr
        if reconciled.exit_code is not ExitCode.SUCCESS:
            exit_code = ExitCode.OPERATION_FAILED
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


def _pipeline_diff_lines(diff: PipelineDiff) -> list[str]:
    """The lines `weft pipeline diff` and `weft eval compare` both print for one `PipelineDiff`
    — task **4.6** pulls this out of `_render_pipeline_diff` so `_render_eval_compare` reuses
    the identical formatting rather than a second, independently-drifting copy of it.
    """
    if diff.identical:
        return [f"'{diff.a_name}' and '{diff.b_name}' resolve identically."]

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
    return lines


def _render_pipeline_diff(result: PipelineDiffCommandResult) -> Rendered:
    """`weft pipeline diff` — the diff itself is proven exact by `weft_cli.pipeline_diff.
    diff_resolved` (structural comparison of two resolved values, never rendered text);
    this function only turns that already-exact answer into lines for a human.
    """
    stdout = "\n".join(_pipeline_diff_lines(result.diff))
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_config_get(result: ConfigGetCommandResult) -> Rendered:
    lines: list[str] = []
    for entry in result.entries:
        line = f"{entry.key} = {entry.value}"
        if result.show_origin:
            line += f"  (origin: {entry.origin.value})"
        lines.append(line)
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_eval_run(result: EvalRunCommandResult) -> Rendered:
    """`weft eval run` — the run id first, since that is what `weft eval compare`/`weft trace`
    need next, then `weft_cli.render._render_index`'s own summary line, then the corpus this
    record now carries, then task 4.7's own wall-clock measurement — V5's half of a priced run
    an operator can see without opening the persisted file.
    """
    summary = result.summary
    stored = "unknown" if result.stored_count is None else str(result.stored_count)
    corpus = result.record.corpus
    stdout = (
        f"run {result.run_id} persisted ({result.path} -> pipeline "
        f"'{result.record.resolved_pipeline.name}'). produced {summary.produced}, nothing to "
        f"produce {summary.nothing_to_produce}, failed {summary.failed}. nodes now stored: "
        f"{stored}. corpus: '{corpus.name}' ({corpus.digest[:12]}…). "
        f"wall clock: {result.wall_clock_seconds:.2f}s."
    )
    stderr = (
        "\n".join(f"  failed: {reason}" for reason in summary.failed_reasons)
        if summary.failed_reasons
        else None
    )
    exit_code = ExitCode.SUCCESS if summary.failed == 0 else ExitCode.OPERATION_FAILED
    return Rendered(stdout=stdout, stderr=stderr, exit_code=exit_code)


def _metric_result_text(result: MetricRunResult) -> str:
    """One `weft_eval.run_record.MetricRunResult`, for a human — a mean with its own dispersion
    and sample count if the metric was scored, or the honest reason it was not, task 4.9's own
    "never a bare mean, and never silence for an unmeasured metric" pair of rules.
    """
    if isinstance(result, Produced):
        aggregate = result.value
        stdev = f"±{aggregate.stdev:.3f}" if aggregate.stdev is not None else "±n/a"
        excluded = f", excluded {aggregate.excluded}" if aggregate.excluded else ""
        return f"{aggregate.mean:.3f} (n={aggregate.n}, {stdev}{excluded})"
    return f"not produced ({result.reason})"


def _metrics_comparison_lines(comparison: Mapping[str, MetricComparison]) -> list[str]:
    """One line per metric name either compared run carries — `weft eval compare`'s own
    per-metric half, task 4.9. A metric both runs scored also gets a signed delta, computed
    here rather than stored, since `MetricComparison` carries the two aggregates, not their
    difference (`02` §1: derive, do not duplicate).
    """
    if not comparison:
        return ["metrics: (none scored on either run — 'weft eval run' was not given --questions)"]
    lines = ["metrics:"]
    for name, pair in comparison.items():
        left = _metric_result_text(pair.a)
        right = _metric_result_text(pair.b)
        delta = ""
        if isinstance(pair.a, Produced) and isinstance(pair.b, Produced):
            delta = f"  Δ{pair.b.value.mean - pair.a.value.mean:+.3f}"
        lines.append(f"  {name}: {left} vs {right}{delta}")
    return lines


def _render_eval_compare(result: EvalCompareCommandResult) -> Rendered:
    """`weft eval compare` — reached only once `weft_cli.eval_commands.EvalCompareCommand`
    has already confirmed corpus, model versions and active distributions all agree
    (`IncomparableRunsError` otherwise), so this prints that confirmation, the pipeline diff
    itself (reusing `_pipeline_diff_lines` rather than a second formatter), and — task 4.9 —
    the per-metric comparison the tool generates itself: what the two pipelines *produced*,
    not only how they resolve.
    """
    lines = [
        f"'{result.run_a}' vs '{result.run_b}' — same corpus, model versions and active "
        f"distributions; pipeline is the only fact that may differ:",
        *_pipeline_diff_lines(result.pipeline_diff),
        *_metrics_comparison_lines(result.metrics_comparison),
    ]
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_trace(result: TraceCommandResult) -> Rendered:
    """`weft trace` — every fact `weft_eval.run_record.RunRecord` carries, and nothing this
    module invents on top of it (Q2, `weft_cli.eval_commands`'s own module docstring: this is
    what the persisted record holds, never a stage-level replay nothing in this tree persists).
    Task 4.9 widened the record by one field, `metrics`, so this widens by one block to match.
    """
    record = result.record
    lines = [
        f"run {result.run_id} — recorded {record.recorded_at}",
        f"pipeline: {record.resolved_pipeline.name}",
        f"corpus: '{record.corpus.name}' ({record.corpus.digest[:12]}…)",
        f"model versions: {dict(record.model_versions) or '(none recorded)'}",
        f"active distributions: {', '.join(record.active_distributions) or '(none)'}",
    ]
    if record.metrics:
        lines.append("metrics:")
        lines.extend(
            f"  {name}: {_metric_result_text(metric_result)}"
            for name, metric_result in sorted(record.metrics.items())
        )
    else:
        lines.append("metrics: (none recorded — 'weft eval run' was not given --questions)")
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_eval_metrics(result: EvalMetricsCommandResult) -> Rendered:
    """`weft eval metrics [<name>]` — task 4.7, V5's "the offline subset must be identifiable
    as a subset". A metric that cannot run never reaches this renderer at all — `weft_eval.
    offline.require_gate_safe` raises before `EvalMetricsCommandResult` is ever constructed —
    so every line printed here names a metric that genuinely runs with no credentials and no
    network, or is honestly listed as one that does not.
    """
    lines = [
        f"runs in the gate (no credentials, no network): {', '.join(result.gate_safe) or '(none)'}",
        f"does not run in the gate: {', '.join(result.gate_unsafe) or '(none)'}",
    ]
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)
