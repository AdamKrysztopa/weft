"""Turning a `Command`'s `Outcome[CommandResult]` into stdout, stderr and an exit code.

Task **3.2**'s own "minimal human renderer" — `docs/03-cli.md` → *Two modes, one
implementation*: "a `Command` returns a typed result and never writes to a stream." Something
still has to write to one, and this module is that something, for exactly one reader: a human at
a terminal. `--json`'s newline-delimited event sink and the REPL's own renderer are **task 3.4 and
3.6 — not built here**, per this task's own brief; this is the smallest renderer that reproduces,
byte for byte, what the five retired `handle_*` functions in `weft_cli.cli` used to print
directly, now computed from data instead of interleaved with the logic that produced it.

**Task 6.20 (G13) — `Rendered` and `ExitCode` move to `weft_command`, and the dispatch itself
becomes a registration, not a table.** `docs/03-cli.md` → *Plugin-contributed commands*: "a
result type nobody outside the CLI can format is only half a contract" — before this task,
`_RENDERERS` matched only the CLI's own result types, so a pack's own `show` command printed a raw
JSON dump at a person while eighteen built-in commands printed for one. `register_renderers`
below registers every one of those eighteen through `weft_kernel.discovery.PackRegistrar.
add_renderer`, the identical seam a third-party pack's own `register()` calls — so a built-in
renderer and a stranger's are indistinguishable at the seam, and `weft_cli.commands.register`
calls this function on exactly the same footing it calls `register_pipeline_commands` or
`register_eval_commands`. `register_renderers_from_reports` is the generic consumer, modelled
directly on `weft_store.rehydrate.register_from_reports` (task 5.2g) — read that function's own
docstring first; this is the identical mechanism one surface over: idempotent for a result type
already held by the identical renderer callable (discovery runs more than once in one process
across this tree's own suite, and a report re-read is the same fact stated again), and a
`weft_kernel.registry.DuplicateRegistrationError` for a *different* renderer claiming a result
type already held, naming both distributions — two packs claiming one result type is a real
collision, not a repeat. `_render_result` below looks a result up in that registry by walking
`type(result).__mro__`, and still falls through to `_render_unknown` when nothing is registered
— the floor stays the floor, and stops being the ceiling.

**Why exit code still lives in a renderer's vocabulary, not on the result — now stated in
`weft_command.render`'s own docstring, since that is where `Rendered`/`ExitCode` now live.**
`weft_command.contract.CommandResult` is still capability-agnostic — it does not know
`ExitCode` exists, on the same footing G1 holds the kernel to for a capability name.
`IndexCommandResult.summary.failed > 0` still has to become exit code `1` somewhere, and "the
CLI renders it" (`03`'s governing rule) is exactly the licence every renderer registered here
takes, computing it from the typed fields a command actually returned. This mirrors
`weft_cli.exit_codes.exit_code_for`'s own placement for exceptions: one function owns the whole
mapping from "what happened" to "what the process reports," for a wider family — exceptions,
not results.

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
progress but keeps the result" still has to hold. `AskCommandResult` still reaches `_render_ask`
through a special case in `_render_result` rather than through the registered dispatch, because
`streamed` is call-specific state no registered `(result type, renderer)` pair carries — it is
still registered, bound with `streamed=False`, so the built-in count stays honest even though
`_render_result` never actually calls it that way.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
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
from weft_cli.exit_codes import exit_code_for
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
from weft_command import ExitCode

# Explicit re-export — `Rendered` moved to `weft-command` at task 6.20 (see that
# module's own docstring), and roughly six callers in this distribution plus their
# tests import it from here. `as Rendered` rather than a bare import is what makes it
# a *public* re-export under pyright strict, the identical form `weft_cli.exit_codes`
# already uses for `ExitCode` one module over.
from weft_command import Rendered as Rendered
from weft_command.contract import CommandResult
from weft_eval.run_record import MetricRunResult
from weft_kernel.discovery import PackRegistrar, PackReport, PackStatus, RendererOffer
from weft_kernel.errors import WeftError
from weft_kernel.payload import NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry, UnknownPluginError


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
        result.versions,
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


#: `(CommandResult, qualified result-type name) -> renderer` — task **6.20**. A `Registry`
#: rather than a hand-rolled `dict`, on `weft_store.rehydrate.ext_models`'s own precedent
#: (that module's docstring names the reasoning in full): a result type claimed twice by two
#: different renderers raises `DuplicateRegistrationError` naming both distributions, for
#: free, rather than one silently overwriting the other. Keyed on `CommandResult` as the
#: shared "contract" — every real key is a `CommandResult` subclass's own qualified name, so
#: two unrelated types happening to share a bare class name in different modules never
#: collide. Never read directly: `register_renderers_from_reports` writes it,
#: `_lookup_renderer` reads it, and this module never learns any capability from what it
#: holds — the kernel's own restraint, kept up here too.
_renderer_registry: Registry = Registry()


def _renderer_key(result_type: type[object]) -> str:
    """The `Registry` name a `CommandResult` subclass registers its renderer under."""
    return f"{result_type.__module__}.{result_type.__qualname__}"


def register_renderers_from_reports(reports: Iterable[PackReport]) -> None:
    """Register every renderer any pack declared through `PackRegistrar.add_renderer`.

    Task **6.20** — the generic consumer of `PackReport.renderers`, modelled directly on
    `weft_store.rehydrate.register_from_reports` (task 5.2g): it walks whatever every report
    carries and knows nothing about which pack contributed which renderer, so a future pack
    shipping a new `CommandResult` costs this function nothing to support. Call once, after
    `discover()` returns — `weft_cli.registry_bootstrap.build_dependencies` is the one caller.

    **Idempotent for a result type already held by the identical renderer callable** — the
    same check `register_from_reports` makes for a namespace and its `ExtModel`, generalised
    here for a result type and its renderer: this function is safe to call more than once in
    one process (every test in this tree's own suite that calls `discover()` more than once
    does), because a result type `_renderer_registry` already holds against the exact same
    callable is not a collision, only a repeat report of the same fact. A *different*
    callable claiming a result type already held raises
    `weft_kernel.registry.DuplicateRegistrationError`, naming both distributions — two packs
    claiming one result type is a real collision this function must not paper over.
    """
    for report in reports:
        for offer in report.renderers:
            _register_renderer_if_new(offer)


def _register_renderer_if_new(offer: RendererOffer) -> None:
    """`_renderer_registry.add(...)` for `offer`, skipped only when `offer.result_type`
    already claims `offer.render` itself — see `register_renderers_from_reports`'s own
    docstring for why.
    """
    name = _renderer_key(offer.result_type)
    try:
        registrant = _renderer_registry.entry(CommandResult, name).factory
    except UnknownPluginError:
        _renderer_registry.add(CommandResult, name, offer.render, distribution=offer.distribution)
        return
    if registrant is not offer.render:
        _renderer_registry.add(CommandResult, name, offer.render, distribution=offer.distribution)


def _lookup_renderer(result: CommandResult) -> Callable[[object], object] | None:
    """The registered renderer for `result`'s own type, or the first ancestor of it that has
    one — `type(result).__mro__`, walked most-specific first, so a subclass's own registered
    renderer wins over a base class's. `None` when nothing along that chain was ever
    registered, which `_render_result` reads as "fall through to `_render_unknown`."
    """
    for cls in type(result).__mro__:
        try:
            entry = _renderer_registry.entry(CommandResult, _renderer_key(cls))
        except UnknownPluginError:
            continue
        return entry.factory
    return None


def _render_result(result: CommandResult, *, streamed: bool) -> Rendered:
    # `AskCommandResult` is the one result type `streamed` matters for — call-specific state
    # no registered `(result type, renderer)` pair carries — so it is special-cased ahead of
    # the registered dispatch rather than the dispatch widening every renderer to a parameter
    # only one of them would ever use. It is still registered (see `register_renderers`,
    # bound with `streamed=False`) so the built-in count stays honest.
    if isinstance(result, AskCommandResult):
        return _render_ask(result, streamed=streamed)
    renderer = _lookup_renderer(result)
    if renderer is not None:
        return cast(Rendered, renderer(result))
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


# --- the eighteen built-in dispatch wrappers, and `register_renderers` — task 6.20 ----------
#
# Each wrapper below is a plain module-level `def`, never a `lambda` bound inside
# `register_renderers` itself: `register_renderers` runs once per `discover()` call, and a
# `lambda` built inside its body would be a *new* callable object every time, which would
# make every call after the first look like "a different renderer for a result type already
# held" to `register_renderers_from_reports`'s identity check — a false collision between
# `weft-cli` and itself. A module-level `def`, built exactly once at import time, is the same
# object every time `register_renderers` runs, so a second `discover()` in the same process
# is correctly read as the identical fact restated. Each one still only `cast`s its argument
# down to the specific result type the wrapped `_render_*` function was written against — the
# same defensive-cast idiom every `Command.run` in `weft_cli.commands` already uses for its
# own `args` parameter — so no `_render_*` function widens its own signature to `CommandResult`
# purely to satisfy this seam.
def _dispatch_index(result: object) -> Rendered:
    return _render_index(cast(IndexCommandResult, result))


def _dispatch_plugins_list(result: object) -> Rendered:
    return _render_plugins_list(cast(PluginsListCommandResult, result))


def _dispatch_plugins_doctor(result: object) -> Rendered:
    return _render_plugins_doctor(cast(PluginsDoctorCommandResult, result))


def _dispatch_init(result: object) -> Rendered:
    return _render_init(cast(InitCommandResult, result))


def _dispatch_delete(result: object) -> Rendered:
    return _render_delete(cast(DeleteCommandResult, result))


def _dispatch_reconcile(result: object) -> Rendered:
    return _render_reconcile(cast(ReconcileCommandResult, result))


def _dispatch_pipeline_list(result: object) -> Rendered:
    return _render_pipeline_list(cast(PipelineListCommandResult, result))


def _dispatch_pipeline_show(result: object) -> Rendered:
    return _render_pipeline_show(cast(PipelineShowCommandResult, result))


def _dispatch_pipeline_derive(result: object) -> Rendered:
    return _render_pipeline_derive(cast(PipelineDeriveCommandResult, result))


def _dispatch_pipeline_validate(result: object) -> Rendered:
    return _render_pipeline_validate(cast(PipelineValidateCommandResult, result))


def _dispatch_pipeline_diff(result: object) -> Rendered:
    return _render_pipeline_diff(cast(PipelineDiffCommandResult, result))


def _dispatch_config_get(result: object) -> Rendered:
    return _render_config_get(cast(ConfigGetCommandResult, result))


def _dispatch_config_set(result: object) -> Rendered:
    return _render_config_set(cast(ConfigSetCommandResult, result))


def _dispatch_eval_run(result: object) -> Rendered:
    return _render_eval_run(cast(EvalRunCommandResult, result))


def _dispatch_eval_compare(result: object) -> Rendered:
    return _render_eval_compare(cast(EvalCompareCommandResult, result))


def _dispatch_trace(result: object) -> Rendered:
    return _render_trace(cast(TraceCommandResult, result))


def _dispatch_eval_metrics(result: object) -> Rendered:
    return _render_eval_metrics(cast(EvalMetricsCommandResult, result))


def _dispatch_ask(result: object) -> Rendered:
    # `_render_result`'s own special-case is what actually reads `streamed` for a live
    # request — see that function's docstring. Registering this bound-`False` wrapper keeps
    # `AskCommandResult` counted among the built-ins `register_renderers` offers, without
    # changing what `_render_result` does for it.
    return _render_ask(cast(AskCommandResult, result), streamed=False)


def register_renderers(registrar: PackRegistrar) -> None:
    """Register every built-in renderer through the identical seam a stranger's pack uses.

    Task **6.20**, G13's third repair — requirement 4 ("built-ins get no privileged path"),
    made checkable at runtime rather than merely asserted: `weft_cli.commands.register` calls
    this on the same footing it calls `register_pipeline_commands`/`register_eval_commands`,
    so every one of these eighteen calls to `registrar.add_renderer` is indistinguishable, at
    the seam, from the identical call any third-party pack's own `register()` makes for its own
    result type. **This module may not name the pack that proves it**, and that is fitness
    function 9(b) rather than shyness: a first-party file naming the out-of-tree pack would make
    the pack part of what it is meant to be independent of.
    """
    registrar.add_renderer(IndexCommandResult, _dispatch_index)
    registrar.add_renderer(PluginsListCommandResult, _dispatch_plugins_list)
    registrar.add_renderer(PluginsDoctorCommandResult, _dispatch_plugins_doctor)
    registrar.add_renderer(InitCommandResult, _dispatch_init)
    registrar.add_renderer(DeleteCommandResult, _dispatch_delete)
    registrar.add_renderer(ReconcileCommandResult, _dispatch_reconcile)
    registrar.add_renderer(PipelineListCommandResult, _dispatch_pipeline_list)
    registrar.add_renderer(PipelineShowCommandResult, _dispatch_pipeline_show)
    registrar.add_renderer(PipelineDeriveCommandResult, _dispatch_pipeline_derive)
    registrar.add_renderer(PipelineValidateCommandResult, _dispatch_pipeline_validate)
    registrar.add_renderer(PipelineDiffCommandResult, _dispatch_pipeline_diff)
    registrar.add_renderer(ConfigGetCommandResult, _dispatch_config_get)
    registrar.add_renderer(ConfigSetCommandResult, _dispatch_config_set)
    registrar.add_renderer(EvalRunCommandResult, _dispatch_eval_run)
    registrar.add_renderer(EvalCompareCommandResult, _dispatch_eval_compare)
    registrar.add_renderer(TraceCommandResult, _dispatch_trace)
    registrar.add_renderer(EvalMetricsCommandResult, _dispatch_eval_metrics)
    registrar.add_renderer(AskCommandResult, _dispatch_ask)


def _bootstrap_built_in_renderers() -> None:
    """Seed `_renderer_registry` with the built-ins the moment this module is imported.

    `weft_cli.commands.register` calling `register_renderers` (through discovery, or through
    `weft_cli.registry_bootstrap.build_dependencies` calling `register_renderers_from_reports`
    beside it) is what a *running* `weft` does — but this module is usable stand-alone, and
    most of this module's own tests, plus every caller that pre-dates task 6.20, call
    `render_outcome` directly without ever running discovery first. This runs the identical
    `register_renderers`/`register_renderers_from_reports` path a real discovery pass would,
    against a throwaway `Registry`/`PackRegistrar`, so the built-ins are reachable either way
    without a second, independently-drifting registration mechanism: a later, real discovery
    pass registering the same eighteen callables again is the identical-renderer repeat case
    `register_renderers_from_reports` already treats as a no-op, never a collision.
    """
    registrar = PackRegistrar(Registry(), distribution="weft-cli")
    register_renderers(registrar)
    report = PackReport(
        distribution="weft-cli", status=PackStatus.ACTIVE, renderers=registrar.renderers
    )
    register_renderers_from_reports([report])


_bootstrap_built_in_renderers()
