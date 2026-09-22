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
JSON dump at a person while twenty built-in commands printed for one. `register_renderers`
below registers every one of those twenty through `weft_kernel.discovery.PackRegistrar.
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
    RenderCommandResult,
    SourcesListCommandResult,
    TargetDropCommandResult,
    TargetListCommandResult,
    TargetPromoteCommandResult,
    TargetRollbackCommandResult,
)
from weft_cli.config_commands import ConfigGetCommandResult, ConfigSetCommandResult
from weft_cli.deletion import ParticipantOutcome
from weft_cli.error_envelope import build_error_envelope
from weft_cli.eval_commands import (
    BaselineSelection,
    EvalCompareCommandResult,
    EvalMetricsCommandResult,
    EvalRunCommandResult,
    MetricComparison,
    QueryRungDifference,
    TraceCommandResult,
)
from weft_cli.eval_experiment import EvalExperimentCommandResult, EvalPlanCommandResult
from weft_cli.eval_table import EvalTableCommandResult
from weft_cli.exit_codes import exit_code_for
from weft_cli.ingest import SourceChange
from weft_cli.output import AskFormat
from weft_cli.pipeline_commands import (
    PipelineDeriveCommandResult,
    PipelineDiffCommandResult,
    PipelineEstimateCommandResult,
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
from weft_engine.services import DEFAULT_EMBEDDER_MEANING
from weft_engine.targets import render_embedding_identity
from weft_eval.baseline import Reproduction
from weft_eval.contract import MetricKind
from weft_eval.falsify import BaselineSpread, DifferenceJudgement, PairedDifference
from weft_eval.latency import LatencySummary, latency_summary
from weft_eval.question_set import QuestionSetFormat
from weft_eval.run_record import (
    ExperimentRun,
    MetricRunResult,
    NoQueryRung,
    NotAggregated,
    NotScored,
    PerQuestionScores,
    QueryRung,
    RoleTokens,
)
from weft_generate.payload import AnswerStance, Citation
from weft_kernel.discovery import PackRegistrar, PackReport, PackStatus, RendererOffer
from weft_kernel.errors import WeftError
from weft_kernel.payload import NothingToProduce, Outcome, Produced
from weft_kernel.payload.applicability import Applies
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.seam import StageRecord


def render_outcome(
    outcome: Outcome[CommandResult], *, streamed: bool = False, as_json: bool = False
) -> Rendered:
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

    **`as_json`, carried repair R9.2**, and it is `render_refusal`'s own keyword arriving on the
    success path. `weft_cli.cli.run_command` reads `isinstance(deps.token_sink, JsonSink)` for
    both — the identical global `--json` flag `docs/03-cli.md` -> *Output* already used to build
    that sink, never a second flag the two could disagree about. Before this, a refusal honoured
    "no parsing of prose" and an *answer* did not: `_render_ask` guarded on `AskCommandResult.
    format`, which is `weft ask --format json`'s own per-command choice and says nothing about
    the global flag. Defaults to `False`, the human reading, for every caller that does not pass
    it.
    """
    if isinstance(outcome, Produced):
        return _render_result(outcome.value, streamed=streamed, as_json=as_json)
    if isinstance(outcome, NothingToProduce):
        return Rendered(stdout=outcome.reason, stderr=None, exit_code=ExitCode.SUCCESS)
    return Rendered(stdout=None, stderr=outcome.reason, exit_code=ExitCode.OPERATION_FAILED)


def render_refusal(exc: WeftError, *, as_json: bool = False) -> Rendered:
    """A `WeftError` raised before or during `run()` — a `CommandRefusalError`'s own exit code,
    or `weft_cli.exit_codes.exit_code_for`'s mapping for every other `WeftError`.

    **`as_json`, task 5.2d.** `docs/internal/README.md` decision log, S6/G9: CLI error prose is not
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
        result.defaulted_embedder,
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


def _removed_clause(outcome: ParticipantOutcome) -> str:
    """The half of `_render_delete`'s participant line describing what it removed.

    A failed participant keeps rendering `failed`, unchanged. A participant that reported no
    kinds — every one written before task 9.3 — keeps rendering exactly `{n} node(s) removed`,
    pinned byte-for-byte by
    `tests/unit/weft_cli/test_deletion_reports_kinds.py::test_a_participant_reporting_only_nodes_
    renders_exactly_as_it_always_did`, and separately by `test_render.py`'s own pre-existing
    delete case, which asserts the same shape with its own values. A participant that
    reported kinds inserts each one, sorted by kind name, between the node count and the
    trailing word `removed`: `0 node(s), 40 blob(s) removed`. `(s)` rather than a real
    pluraliser is this file's existing convention (`participant(s)`, `node(s)`), so
    `entity(s)` is deliberately not English — inventing a pluraliser here is a second thing
    to get wrong for no reader-facing benefit. `narrowed_count` (ledger `27.1`) appends a
    trailing `, {n} narrowed` only when non-zero, so a line written before G20 is unchanged.
    """
    if outcome.failed:
        return "failed"
    parts = [f"{outcome.node_count} node(s)"]
    parts += [f"{count} {kind}(s)" for kind, count in sorted(outcome.removed.items())]
    clause = f"{', '.join(parts)} removed"
    if outcome.narrowed_count:
        clause += f", {outcome.narrowed_count} narrowed"
    return clause


def _render_delete(result: DeleteCommandResult) -> Rendered:
    """`weft delete`'s whole answer — one line per participant, and the failures on stderr.

    Task **5.1a**'s property is that a participant that fails is *named*, so every participant
    is listed whether it succeeded or not: reading only the failures would leave an operator
    unable to tell a fan-out of one from a fan-out of five. The exit code follows
    `_render_index`'s own rule — the run happened, and a non-zero code reports that part of it
    did not — rather than a refusal, because a partial deletion is a real event with a real
    result, not a command that declined to start.

    Task **9.3** adds a per-kind breakdown, and the no-kinds line is kept byte-for-byte
    identical to what it always rendered: every participant written before this task reports
    an empty `removed`, and a shipped transcript already pins `pgvector (weft-rag): 6 node(s)
    removed` — changing that line's shape for participants that have nothing new to say would
    break a promise this task was never asked to touch.
    """
    if not result.participants:
        return Rendered(
            stdout=(f"nothing installed holds data for '{result.source_id}'; nothing was deleted."),
            stderr=None,
            exit_code=ExitCode.SUCCESS,
        )
    lines = [f"'{result.source_id}' — {len(result.participants)} participant(s):"]
    lines += [
        f"  {outcome.plugin} ({outcome.distribution}): {_removed_clause(outcome)}"
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
    """One participant's own line — see `_render_reconcile`'s docstring for the three facts a
    summary must not lose. `abstained` (ledger **11.9**) is appended to the same
    comma-separated run, ahead of the interrupted clause, and **only when non-zero**: printed
    unconditionally as `abstained 0` on every `repair` line it would be noise that trains a
    reader to skip the line the one time it says something — the same argument that already
    makes the `remaining`/interrupted clause beside it conditional. An abstention is a
    finished decision, not outstanding work, so its presence never changes `converged` or the
    exit code this line's own outcome contributes to.
    """
    if outcome.report is None:
        return "failed"
    report = outcome.report
    counts = f"examined {report.examined}, removed {report.removed}, backfilled {report.backfilled}"
    if report.abstained:
        counts += f", abstained {report.abstained}"
    if report.converged:
        return counts
    return f"{counts} — interrupted, {report.remaining} left; run again"


def _estimate_lines(outcome: ReconcileEstimateOutcome) -> tuple[str, ...]:
    """One participant's own cost, in `docs/03-cli.md`'s own worked-example shape:

    ```
    weft-kg: 4,312 nodes have no graph data
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
    `discover()` returns — `weft_engine.registry_bootstrap.build_dependencies` is the one caller.

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


def _render_result(result: CommandResult, *, streamed: bool, as_json: bool = False) -> Rendered:
    """One command result, rendered for a person or for a script — task **24.5**.

    **Under `--json` the result *is* the output**, whatever its type. Before this, `as_json`
    reached only `_render_ask`, so `weft --json index` and `weft --json plugins list` printed one
    JSON stream event and then prose, and stdout parsed as neither one document nor as
    newline-delimited JSON. `docs/03-cli.md`:840 owns the sentence that promised otherwise, and
    `R17.18` is the record of it being false.

    **The exit code still comes from the prose path, and that is the whole subtlety.** `weft
    delete` and `weft index` compute theirs from their own result's fields — a participant that
    failed is exit 1 whatever the format — so this renders the human answer to *decide the code*
    and then replaces the text. A branch that returned `SUCCESS` because it had a document to
    print would hide a failed run from exactly the caller least able to notice one.

    `_render_unknown` has always done the dump for a result type this module was never written
    against. What was missing was reaching it for the types it *was* written against, which is
    every type a script actually meets.

    **`AskCommandResult` is the exception, and it is the one that must be.** `weft ask --json`
    already writes a *designed* envelope — `weft_cli.answer_envelope`, discriminated by `kind`,
    carrying `envelope_version`, and carrying `stance` since carried repair `R11.6` so a script
    can read a refusal without parsing the sentence. That is a promise `09` §3 makes about a wire
    format; a raw `model_dump_json()` of the result would be a *different*, unversioned document
    with none of those fields. Replacing one with the other turned seven tests about the
    envelope's shape red, which is that design defending itself.

    So: a result type with a designed machine-readable rendering keeps it, and the model dump is
    the floor for every type that has none — which before this task was every type but one.
    """
    prose = _render_prose(result, streamed=streamed, as_json=as_json)
    if not as_json or (isinstance(result, AskCommandResult) and result.answer is not None):
        return prose
    return Rendered(stdout=result.model_dump_json(), stderr=prose.stderr, exit_code=prose.exit_code)


def _render_prose(result: CommandResult, *, streamed: bool, as_json: bool) -> Rendered:
    # `AskCommandResult` is the one result type `streamed` matters for — call-specific state
    # no registered `(result type, renderer)` pair carries — so it is special-cased ahead of
    # the registered dispatch rather than the dispatch widening every renderer to a parameter
    # only one of them would ever use. It is still registered (see `register_renderers`,
    # bound with `streamed=False`) so the built-in count stays honest.
    if isinstance(result, AskCommandResult):
        return _render_ask(result, streamed=streamed, as_json=as_json)
    renderer = _lookup_renderer(result)
    if renderer is not None:
        return cast(Rendered, renderer(result))
    return _render_unknown(result)


def _reparse_lines(changes: Mapping[str, SourceChange]) -> list[str]:
    """The sources a re-index re-parsed, and why — ledger task **9.17**.

    **Only what moved.** A corpus of a thousand unchanged files must not print a thousand lines
    saying so; `UNCHANGED` and `NEW` are the ordinary cases and stay silent, which is what makes
    the ones that print worth reading.

    **And `INCOMPLETE` is summarised rather than listed, which is that rule meeting a member it
    did not anticipate — task 17.1.** The other two are facts about *that document*: somebody
    edited it, or a pipeline was pointed at it, and they arrive a handful at a time. `INCOMPLETE`
    is a fact about **one interrupted run** and arrives in bulk by construction — a `kill -9` on a
    3,000-document index leaves every one of them `INDEXING`, and the next run printed 3,000
    identical lines. Measured through the shipped wheel, which is the only place it could have
    been seen. One such document still names itself, because at that size the id *is* the fact.

    A `PIPELINE_CHANGED` line is the one this task exists for: the bytes are identical and the
    pipeline that read them is not, so this document has now been read two ways.

    **Both lines said the earlier parse was still stored, and from ledger `27.2` that is false.**
    `9.17` could only report, because removing the stale nodes was a deletion on the ingest path
    nobody had argued for — `L9.37`'s half, which it deliberately left. `27.2` argued it and
    built it: a document whose bytes or whose pipeline moved has its previous parse released
    before the new one runs. So the text says what now happens instead of warning about what
    used to, and an operator reading *"the earlier parse's nodes are still stored beside the new
    ones"* against a store where they are not would be worse served than by no line at all.

    **`RETRIED` joins `INCOMPLETE` on the bulk footing, ledger `36.3`, and never as "did not
    finish".** `--retry-failed` can retry a batch of thousands at once, arriving in bulk the same
    way a `kill -9` does; but it is not the same fact — a run that finished and recorded a source
    `FAILED` did not fail to finish, and carried repair `R36.0`'s own gap was exactly that wording
    reused for a case it does not describe.
    """
    bulked = {
        SourceChange.INCOMPLETE: (
            "a previous index of this document did not finish — indexed again",
            "a previous index did not finish — indexed again",
        ),
        SourceChange.RETRIED: ("failed earlier — retried", "failed earlier — retried"),
    }
    reportable = {
        SourceChange.CONTENT_CHANGED: "changed on disk — re-parsed, and its earlier parse released",
        SourceChange.PIPELINE_CHANGED: (
            "unchanged on disk but re-parsed by a different pipeline — its earlier parse released"
        ),
    }
    lines = [
        f"  {source}: {reportable[change]}"
        for source, change in sorted(changes.items())
        if change in reportable
    ]
    for change, (singular, plural) in bulked.items():
        matched = sorted(source for source, found in changes.items() if found is change)
        if len(matched) == 1:
            lines.append(f"  {matched[0]}: {singular}")
        elif matched:
            lines.append(f"  {len(matched)} documents: {plural}")
    return lines


def _defaulted_embedder_line(embedder: str) -> str:
    """Carried repair `R17.6`'s own stderr line — printed only when `weft.toml` did not name
    an embedder.

    The sentence itself is `weft_engine.services.DEFAULT_EMBEDDER_MEANING`, shared with
    `weft plugins doctor`, `weft init`'s scaffolded `weft.toml` and `weft.toml.example`
    (task **28.8**). What this function adds is the part only this surface knows: that the
    run which just happened used it, and was not asked to.
    """
    return (
        f"  you did not choose an embedder — this ran with '{embedder}'. {DEFAULT_EMBEDDER_MEANING}"
    )


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
    discovered = result.documents_discovered
    indexed = result.documents_indexed
    failed_now = result.documents_failed
    skipped_failed = sum(
        1 for change in result.source_changes.values() if change is SourceChange.FAILED
    )
    unchanged = discovered - indexed - failed_now - skipped_failed
    failed_part = f", {failed_now} failed" if failed_now else ""
    stdout = (
        f"{discovered} documents: {indexed} indexed, {unchanged} unchanged{failed_part}. "
        f"nodes now stored: {stored}."
    )
    if result.target is not None:
        # Ledger task **34.6** — where this run wrote, before anything else it reports.
        marker = (
            "(live)"
            if result.target == result.target_live
            else f"(candidate; live is '{result.target_live}')"
        )
        stdout = f"indexing into target '{result.target}' {marker}.\n{stdout}"
    if result.payload_indexes:
        # Ledger task **31.14**. Named rather than counted: a number would satisfy "reports its
        # payload index" while telling an operator nothing they could check against the
        # `[packs.qdrant] payload_indexes` they wrote. Silent when the store declared nothing,
        # which is not the same as a store reporting none.
        stdout += f"\npayload indexes: {', '.join(result.payload_indexes)}."
    if result.degraded_expansions is not None:
        # A zero is printed because it was counted; `None` means the store was never asked.
        stdout += f"\nchunks stored without their expansion: {result.degraded_expansions}."
    reparsed = _reparse_lines(result.source_changes)
    if reparsed:
        stdout += "\n" + "\n".join(reparsed)
    # Ledger **36.3** — every source this run skipped because an earlier run already recorded it
    # `FAILED`, named as a count rather than per-document: it is a fact about the corpus's
    # standing failures, not about this run, and the remedy is the same one flag regardless of
    # how many there are.
    failed_earlier = sum(
        1 for change in result.source_changes.values() if change is SourceChange.FAILED
    )
    if failed_earlier:
        pronoun = "it" if failed_earlier == 1 else "them"
        stdout += (
            f"\n{failed_earlier} failed earlier, skipped — weft index --retry-failed includes "
            f"{pronoun}"
        )
    if summary.failed:
        stdout += f"\n{summary.failed} batch failed."
    stderr_lines = [f"  failed: {reason}" for reason in summary.failed_reasons]
    if result.defaulted_embedder is not None:
        stderr_lines.append(_defaulted_embedder_line(result.defaulted_embedder))
    stderr = "\n".join(stderr_lines) or None
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


def _citation_line(citation: Citation) -> str:
    """One citation, for a human — carried repair **R9.2**, first half.

    This rendered `  [marker] uri` alone, and `docs/internal/build-ledger.md`'s R9.2 states what
    that cost: several nodes cut from one document cite identically, so *which* node answered is
    unnameable, and a `page` the pipeline worked to resolve (`weft_generate.page.page_for`) never
    reached anybody. The node id is printed **whole** rather than abbreviated — a truncated digest
    is not something a reader can look anything up by, which is the entire complaint — on the
    precedent `_render_reconcile` already sets for `SourceChange` items one screen up.

    `page` is omitted rather than printed as a placeholder when it is `None`, because `None` is
    a fact here and not a gap: `Citation`'s own docstring says it means the source is not
    paginated, or nothing in the pipeline attached either fact. `quote` reaches
    `weft_cli.answer_envelope.AnswerEnvelope` and deliberately not this line — it is a span of
    the passage, often a paragraph, and a human already has the answer text above it.
    """
    page = f" p.{citation.page}" if citation.page is not None else ""
    return f"  [{citation.marker}] {citation.uri}{page} — {citation.node_id}"


def _render_ask(result: AskCommandResult, *, streamed: bool, as_json: bool = False) -> Rendered:
    """`weft ask`'s own two shapes — see `AskCommandResult`'s own docstring for why exactly
    one of `answer`/`hits` is ever populated, and this module's own task-3.11 paragraph for
    `streamed`, which only the `answer` branch reads.

    **`as_json` is the *global* `--json`; `result.format` is `weft ask --format json`.** They
    are two different flags (`weft_cli.output.AskFormat`'s own docstring says so, and neither
    implies the other), and until carried repair **R9.2** only the second one was read here —
    so the answer branch below printed prose on stdout under the global flag, after the event
    stream had already closed. The guard is first in the branch rather than folded into the
    `result.format` test further down, because that test is about the *retrieve-only* shape and
    is unreachable whenever `answer` is set.
    """
    if result.answer is not None:
        # The routed/named-pipeline shape — task 3.11 folds `weft route`'s own retired
        # `_render_route` in here, unchanged in every respect but one: when `streamed` is
        # `True`, `PrintingSink`/`JsonSink` already showed this exact text live, so it is
        # left out rather than printed a second time (`weft_cli.cli.run_command`'s own
        # `deps.token_sink.wrote_anything` is what decides). `--quiet`/a non-streaming sink
        # still gets the full text, because nothing showed it yet.
        if as_json:
            # Carried repair **R9.2**. One line, the run's last, on the same descriptor the
            # `StreamEvent` lines used and discriminated the same way — see
            # `weft_cli.answer_envelope` for what it carries and why `text` is present here
            # even when `streamed` is `True`.
            from weft_cli.answer_envelope import build_answer_envelope

            envelope = build_answer_envelope(result.answer, pipeline_name=result.pipeline_name)
            return Rendered(
                stdout=envelope.model_dump_json(), stderr=None, exit_code=ExitCode.SUCCESS
            )
        lines = [f"routed to: {result.pipeline_name}"]
        if result.answer.stance is AnswerStance.NOT_IN_CORPUS:
            # Carried repair **R11.6**, found by running the binary at task 11.10. A generator
            # that refuses honestly returns `Answer(text="", citations=(),
            # stance=NOT_IN_CORPUS)`, and printing `text` alone rendered that deliberate
            # refusal as the routing line and nothing else — indistinguishable from a crash
            # that happened to exit 0. Unconditional on `streamed`, because a refusal is
            # exactly the case where nothing was streamed: `cited-answer`'s `REFUSE` branch
            # calls no model at all, so the omission below would restore the silence. The
            # sentence itself is unpromised prose under G9 (`09` §3); the exit code is not,
            # and stays `SUCCESS` — nothing failed, and both sibling empty paths in this same
            # function ("no matching passages found.", `NothingToProduce`) already exit 0.
            lines.append("the corpus does not answer this.")
        elif not streamed:
            lines.append(result.answer.text)
        lines.extend(_citation_line(citation) for citation in result.answer.citations)
        return Rendered(
            stdout="\n".join([*lines, *_explain_lines(result), *_stage_lines(result)]),
            stderr=None,
            exit_code=ExitCode.SUCCESS,
        )

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
        lines = [
            "no matching passages found.",
            *_explain_lines(result),
            *_stage_lines(result),
            *_record_lines(result),
        ]
        return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)

    lines = [f"{hit.rank}. {hit.content}" for hit in result.hits]
    return Rendered(
        stdout="\n".join(
            [*lines, *_explain_lines(result), *_stage_lines(result), *_record_lines(result)]
        ),
        stderr=None,
        exit_code=ExitCode.SUCCESS,
    )


def _record_lines(result: AskCommandResult) -> list[str]:
    """`--explain`'s record block, or nothing at all — ledger task **40.3**.

    Empty unless `--explain` populated `result.records`, the same byte-identical-without-the-
    flag guarantee `_explain_lines` and `_stage_lines` already give their own blocks. Each line
    is a stage's own sentence about what it recorded on `Passages.ext` — `weft_cli.explain.
    record_lines` resolved it; this function only lays it out.
    """
    if not result.records:
        return []
    return ["", "records:", *(f"  {line}" for line in result.records)]


def _explain_lines(result: AskCommandResult) -> list[str]:
    """`--explain`'s block, or nothing at all — ledger task **21.1**.

    Empty unless the flag was passed, so every existing transcript in `manual/` and every test
    asserting this function's output is byte-identical without it. That matters more than it
    looks: `03` → *Output*'s *Score display* decision — a reader sees rank order and never the raw
    number — is unchanged, and this is an opt-in answer to *why*, not a reversal of it.

    The sentences are the producers' own, resolved in `weft_cli.commands` where the registry is;
    this function knows only how to lay them out.
    """
    if not result.explanations and result.score_note is None:
        return []
    lines = ["", "score:"]
    lines.extend(f"  {explanation}" for explanation in result.explanations)
    if result.score_note is not None:
        lines.extend(["", f"  {result.score_note}"])
    return lines


def _stage_lines(result: AskCommandResult) -> list[str]:
    """`--explain`'s stage block, or nothing at all — ledger task **33.5**.

    Empty unless `--explain` populated `result.stages`, so a transcript without the flag is
    byte-identical to before this task, exactly as `_explain_lines` already guarantees for the
    score block. Depth is read off `parent`, not off any traversal order: a record whose parent
    id is not itself in `result.stages` counts as top level, which is what keeps a nested
    `gather`'s records indented under the call that opened the scope without this function
    needing to know anything about what ran.
    """
    if not result.stages:
        return []
    records = sorted(result.stages, key=lambda record: record.id)
    by_id = {record.id: record for record in records}

    def depth_of(record: StageRecord) -> int:
        depth = 0
        parent = record.parent
        while parent is not None and parent in by_id:
            depth += 1
            parent = by_id[parent].parent
        return depth

    lines = ["", "stages:"]
    for record in records:
        text = f"{record.label}  {record.seconds * 1000:.0f} ms"
        if record.items_in is not None:
            text += f"  in {record.items_in}"
        if record.items_out is not None:
            text += f"  out {record.items_out}"
        lines.append(f"{'  ' * (depth_of(record) + 1)}{text}")
    if result.stages_seconds is not None:
        top_level_seconds = sum(
            record.seconds
            for record in records
            if record.parent is None or record.parent not in by_id
        )
        total_ms = result.stages_seconds * 1000
        outside_ms = (result.stages_seconds - top_level_seconds) * 1000
        lines.append(f"  total {total_ms:.0f} ms, outside any stage {outside_ms:.0f} ms")
    return lines


def render_applies_to(applies: Applies) -> str:
    """One `Applies` constraint, rendered the way `Applies` writes itself — carried repair
    **R9.11** (`docs/internal/lessons.md` `L9.45`).

    `Applies.__repr__` was written for the one human audience there is: someone reading
    `weft pipeline show`, e.g. `Applies(Language, code='pl')`. Before this repair,
    `_render_pipeline_show` printed `dumped["applies_to"]` instead — the JSON dump `Applies`
    itself is validated from, `{'fact': 'weft_clean.property:Language', 'constraints':
    [['code', 'pl']]}` — because nothing called `repr()` on the value it already held. A
    function rather than an inline `repr(...)` at the one call site, so a test can drive
    this seam directly and so this docstring is where the next reader finds *why* the dump
    is never used here: a serialisation form is not a rendering, and `weft pipeline show`
    is the only place a person reads this value at all.
    """
    return repr(applies)


def _render_pipeline_list(result: PipelineListCommandResult) -> Rendered:
    stdout = "\n".join(result.names) if result.names else "no pipelines known."
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_sources_list(result: SourcesListCommandResult) -> Rendered:
    """`weft sources list` — task **36.4**, widened at **R36.4**: uri and status per line, and
    for a failed source, what went wrong. When the entries came from more than one store, each
    line is prefixed with the store's own name — a project reading from a single store keeps
    today's plain `uri  status` line, unchanged.
    """
    if not result.sources:
        which = "" if result.status is None else f"{result.status.value} "
        return Rendered(
            stdout=f"no {which}sources recorded.", stderr=None, exit_code=ExitCode.SUCCESS
        )
    multi_store = len({entry.store for entry in result.sources}) > 1
    lines: list[str] = []
    for entry in result.sources:
        record = entry.record
        line = f"{entry.store}  " if multi_store else ""
        line += f"{record.uri}  {record.status.value}"
        failure = record.failure
        if failure is not None:
            line += (
                f"  stage: {failure.stage or 'unknown'}  error: {failure.error_type}  "
                f"attempts: {failure.attempts}  last: {failure.last_attempt_at.isoformat()}  "
                f"{failure.message!r}"
            )
        lines.append(line)
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_target_list(result: TargetListCommandResult) -> Rendered:
    """`weft target list` — ledger task **34.6**: one line per target, naming which store it
    belongs to when more than one is in use, on `_render_sources_list`'s own precedent.
    """
    if not result.targets:
        return Rendered(stdout="no targets recorded.", stderr=None, exit_code=ExitCode.SUCCESS)
    multi_store = len({target.store for target in result.targets}) > 1
    lines: list[str] = []
    for target in result.targets:
        mark = "live" if target.live else "previous" if target.previous else "-"
        embedding = (
            render_embedding_identity(target.embedding)
            if target.embedding is not None
            else "embedding not recorded"
        )
        prefix = f"{target.store}  " if multi_store else ""
        lines.append(f"{prefix}{target.name}  {mark}  {embedding}  {target.sources} sources")
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_target_promote(result: TargetPromoteCommandResult) -> Rendered:
    """`weft target promote` — ledger task **34.8**: which target is live now, and what was
    live before it, so a person watching the switch happen does not have to run `target list`
    to learn what `rollback` would restore.
    """
    stdout = (
        f"promoted {result.catalogue.live!r} on {result.store} "
        f"(previous live: {result.catalogue.previous!r})"
    )
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_target_rollback(result: TargetRollbackCommandResult) -> Rendered:
    """`weft target rollback` — ledger task **34.9**."""
    stdout = f"live target is {result.catalogue.live!r} again on {result.store}"
    return Rendered(stdout=stdout, stderr=None, exit_code=ExitCode.SUCCESS)


def _render_target_drop(result: TargetDropCommandResult) -> Rendered:
    """`weft target drop` — ledger task **34.9**: names how many sources went with it, the one
    fact `describe_impact`'s own confirmation prompt could not honestly state in advance (see
    `weft_cli.target_commands.TargetDropCommand`'s own docstring).
    """
    stdout = f"dropped target {result.target!r} from {result.store} ({result.sources} sources)"
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
            rendered_applies = ", ".join(render_applies_to(item) for item in stage.applies_to)
            lines.append(f"    applies_to: {rendered_applies}")
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


def _render_pipeline_estimate(result: PipelineEstimateCommandResult) -> Rendered:
    """`weft pipeline estimate` — every number named beside the assumption it rests on.

    The task's own clause, printed rather than only pinned in the model: `width` carries
    `width_assumption` on the same line when there is one, `index_bytes` prints `unmeasured`
    rather than a bare `None` a reader could mistake for zero, and `unknowns` is its own line
    so payload, text and WAL read as "nobody measured this" rather than as omitted.
    """
    projection = result.projection
    width_line = f"width: {projection.width}"
    if projection.width_assumption is not None:
        width_line += f" (assumed — {projection.width_assumption})"

    index_kind = projection.index_kind.value if projection.index_kind is not None else "none"
    precision = projection.precision.value if projection.precision is not None else "none"
    index_bytes = "unmeasured" if projection.index_bytes is None else str(projection.index_bytes)

    lines = [
        f"pipeline: {projection.pipeline}  store: {projection.store}",
        f"sample: {projection.sample_documents} document(s), {projection.sample_chunks} chunk(s) "
        f"— {projection.chunks_per_document:.2f} chunks/document",
        f"projected: {projection.projected_documents} document(s) -> "
        f"{projection.projected_vectors} vector(s)",
        width_line,
        f"index: {index_kind}  precision: {precision}",
        f"vector bytes: {projection.vector_bytes}",
        f"rescoring (full-precision copy) bytes: {projection.rescoring_original_bytes}",
        f"index bytes: {index_bytes}",
        f"model calls: {projection.model_calls}",
        f"not estimated from this sample: {', '.join(projection.unknowns)}",
    ]
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_config_get(result: ConfigGetCommandResult) -> Rendered:
    lines: list[str] = []
    for entry in result.entries:
        line = f"{entry.key} = {entry.value}"
        if result.show_origin:
            line += f"  (origin: {entry.origin.value})"
        lines.append(line)
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _percentile_text(label: str, percentile: Produced[float] | NotAggregated, samples: int) -> str:
    """One nearest-rank percentile, task 33.8 — `weft_eval.latency.LatencySummary`'s own field,
    for a human. `samples` is the summary's own count, not anything parsed from `NotAggregated.
    reason`, so the printed text does not depend on that string's exact wording.
    """
    if isinstance(percentile, Produced):
        return f"{label}: {percentile.value:.2f}s"
    return f"{label}: not aggregated ({samples} samples)"


def _latency_summary_text(summary: LatencySummary) -> str:
    """`p50: …, p95: …, p99: …` — the three percentiles task 33.8 prints beside a run's other
    metrics, never gated and never compared for comparability (the module docstring's own
    "reported, never a reason to refuse").
    """
    return ", ".join(
        _percentile_text(label, percentile, summary.samples)
        for label, percentile in (
            ("p50", summary.p50),
            ("p95", summary.p95),
            ("p99", summary.p99),
        )
    )


def _role_tokens_text(role: str, tokens: RoleTokens) -> str:
    """One `[llm.roles]` role's line in `weft eval run`'s `tokens:` sentence — ledger task
    **33.10**. A role every call of which went unreported reads *not reported*, by name and
    call count, never `0 in / 0 out`; that number would claim a metering the provider never
    did.
    """
    if tokens.calls_not_reporting == tokens.calls:
        return f"{role}: not reported ({tokens.calls} calls)"
    text = f"{role}: {tokens.prompt_tokens} in / {tokens.completion_tokens} out"
    if tokens.calls_not_reporting:
        text += f" (+{tokens.calls_not_reporting} calls not reported)"
    return text


def _render_eval_run(result: EvalRunCommandResult) -> Rendered:
    """`weft eval run` — the run id first, since that is what `weft eval compare`/`weft trace`
    need next, then `weft_cli.render._render_index`'s own summary line, then the corpus this
    record now carries, then task 4.7's own wall-clock measurement — V5's half of a priced run
    an operator can see without opening the persisted file. Task 33.8 appends the query latency
    percentiles when the record carries `question_seconds`, and prints nothing about latency for
    a record that does not — never a fabricated `p50:` for a run that measured none. Task 33.10
    appends each metered role's tokens when the record carries `token_usage`, and prints nothing
    about tokens for a record that measured none.
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
    summary_latency = latency_summary(result.record.question_seconds)
    if summary_latency is not None:
        stdout += f" query latency: {_latency_summary_text(summary_latency)}."
    token_usage = result.record.token_usage
    if token_usage:
        role_text = ", ".join(
            _role_tokens_text(role, token_usage[role]) for role in sorted(token_usage)
        )
        stdout += f" tokens: {role_text}."
    stderr_lines: list[str] = []
    if result.question_set_format is QuestionSetFormat.JSON:
        stderr_lines.append(
            "deprecated: a JSON --questions file is read by converting it into the TOML "
            "question form until weft-rag 3.0, when this reader is removed — write the "
            "TOML question form instead."
        )
    if summary.failed_reasons:
        stderr_lines.extend(f"  failed: {reason}" for reason in summary.failed_reasons)
    stderr = "\n".join(stderr_lines) if stderr_lines else None
    exit_code = ExitCode.SUCCESS if summary.failed == 0 else ExitCode.OPERATION_FAILED
    return Rendered(stdout=stdout, stderr=stderr, exit_code=exit_code)


def _slice_text(stdev: float | None) -> str:
    """The `±stdev` fragment `_metric_result_text` prints, shared with its own per-modality
    lines below — one dispersion format for the whole aggregate and each of its slices."""
    return f"±{stdev:.3f}" if stdev is not None else "±n/a"


def _metric_result_text(result: MetricRunResult) -> str:
    """One `weft_eval.run_record.MetricRunResult`, for a human — a mean with its own dispersion
    and sample count if the metric was scored, or the honest reason it was not, task 4.9's own
    "never a bare mean, and never silence for an unmeasured metric" pair of rules.

    Task 9.12 — a per-modality line for each entry `MetricAggregate.by_modality` carries, but
    **only when there is more than one**: a text-only run's `by_modality` holds at most the one
    `TEXT` slice, and printing it beside a whole-run mean that is already that same slice would
    be pure noise, not information — so a single-modality run renders exactly as it always has.
    """
    if isinstance(result, Produced):
        aggregate = result.value
        stdev = _slice_text(aggregate.stdev)
        excluded = f", excluded {aggregate.excluded}" if aggregate.excluded else ""
        text = f"{aggregate.mean:.3f} (n={aggregate.n}, {stdev}{excluded})"
        if len(aggregate.by_modality) > 1:
            per_modality = ", ".join(
                f"{modality.value}: {slice_.mean:.3f} (n={slice_.n}, {_slice_text(slice_.stdev)})"
                for modality, slice_ in sorted(aggregate.by_modality.items())
            )
            text += f" [{per_modality}]"
        return text
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


def _paired_difference_line(name: str, difference: PairedDifference) -> str:
    """One metric's own line under the paired-difference block — task 16.9, `_falsification_
    line`'s own formatting (a signed difference to three decimals) applied to the second
    interval rather than the first. A single paired question has no interval to report — the
    identical rule `_falsification_line` states for a zero-width baseline spread, one
    granularity over — so that case prints a reason instead of a fabricated bound.
    """
    if difference.low is None or difference.high is None:
        return f"  {name}: {difference.mean:+.3f} (no interval — one question)"
    return (
        f"  {name}: {difference.mean:+.3f} (95% CI {difference.low:+.3f} to "
        f"{difference.high:+.3f}, n={difference.n})"
    )


def _paired_difference_lines(
    paired: Mapping[str, PairedDifference], *, slice_: str | None = None
) -> list[str]:
    """`weft eval compare`'s paired-difference block — task 16.9. Printed only when `paired` is
    non-empty, see `_render_eval_compare`; *beside* the falsification block, never instead of
    it, since the two answer different questions.

    `slice_` — repair R38.1 — is `EvalCompareCommandResult.paired_differences_slice`: the
    `"axis=value"` a `--slice`/`--kind` restricted the pairing to, printed in the header so a
    reader cannot mistake a sliced pairing for one over the whole run.
    """
    header = "paired difference over questions (b − a):"
    if slice_ is not None:
        header = f"paired difference over questions (b − a), {slice_}:"
    lines = [header]
    lines.extend(_paired_difference_line(name, difference) for name, difference in paired.items())
    return lines


def _falsification_line(name: str, judgement: DifferenceJudgement) -> str:
    """One metric's own line under the falsification block — task 8.8. An `UNJUDGEABLE`
    verdict prints its reason instead of numbers it does not have; a decided verdict prints
    the signed difference and the baseline spread's own bounds, to three decimal places, the
    same style `_metric_result_text` already prints a `stdev` in.
    """
    spread: BaselineSpread | None = judgement.spread
    difference = judgement.difference
    # `spread`/`difference` are both `None` exactly when the verdict is `UNJUDGEABLE`, and the
    # reason is then the whole answer. Read structurally rather than off the verdict alone: a
    # judgement missing either one has no numbers to print, and printing `Δ+0.000` for it would
    # be inventing the very measurement this command exists to withhold.
    if difference is None or spread is None:
        return f"  {name}: {judgement.verdict.value} — {judgement.reason}"
    # Ledger 8.23, `docs/internal/lessons.md` L8.17. A zero-width interval is not a number like the
    # others: a genuinely deterministic system and a badly-sampled one record the identical
    # thing, and the mistake runs in the over-confident direction, because every difference
    # then falls outside it. Measured, not supposed — task 8.8's own demonstration scored
    # 0.833 and 0.667 on identical inputs while each session's repetitions agreed exactly.
    spread_note = ""
    if spread.width == 0.0:
        spread_note = " — zero-width: these repetitions did not vary at all, which is a claim "
        spread_note += "about them, not proof the system is deterministic"
    return (
        f"  {name}: {judgement.verdict.value} (Δ{difference:+.3f}, baseline spread "
        f"{spread.low:.3f}-{spread.high:.3f}){spread_note}"
    )


def _falsification_lines(
    baseline_pipeline: str,
    baseline_runs: tuple[str, ...],
    falsification: Mapping[str, DifferenceJudgement],
) -> list[str]:
    """`weft eval compare --baseline <pipeline>`'s own block — task 8.8. Printed only when a
    baseline was actually asked for, see `_render_eval_compare`.
    """
    lines = [
        f"falsification — baseline '{baseline_pipeline}', repetitions: "
        f"{', '.join(baseline_runs) or '(none)'}:"
    ]
    lines.extend(_falsification_line(name, judgement) for name, judgement in falsification.items())
    return lines


def _query_rung_side_text(rung: QueryRung | NoQueryRung | None) -> str:
    """One side of a `QueryRungDifference`, rendered for the `vs` line — task 16.1. Narrower
    than `_query_rung_text`: an identity or a `NoQueryRung.reason` would make the comparison
    line unreadable, and the two sides being *named* differently is the whole fact this line
    exists to report.
    """
    if rung is None:
        return "(not recorded)"
    if isinstance(rung, NoQueryRung):
        return "(none named)"
    return f"'{rung.name}'"


def _query_rung_difference_lines(query_rungs: QueryRungDifference | None) -> list[str]:
    """One line naming both sides' query rung, only when they differ — task 16.1. A comparison
    does not report a fact that did not move, the same posture the pipeline diff and the
    metrics comparison already take for anything unchanged.
    """
    if query_rungs is None or query_rungs.a == query_rungs.b:
        return []
    a_text = _query_rung_side_text(query_rungs.a)
    b_text = _query_rung_side_text(query_rungs.b)
    return [f"query rung: {a_text} vs {b_text}"]


def _baseline_selection_line(selection: BaselineSelection) -> str:
    """Which rule chose `--baseline`'s repetitions — task 16.1, printed so a reader of a
    verdict can tell a rung-matched spread from a pipeline-matched one.
    """
    return f"baseline selection: {selection.value}"


def _run_latency_line(run_id: str, summary: LatencySummary | None) -> str:
    """One run's own query latency line — task 33.8. `None` is a record with no per-question
    timing (written before task 33.7, or run without `--questions`), and says so rather than
    refusing the comparison: latency depends on the machine it ran on and is not identity, so it
    is reported beside a comparison the way packaging is (repair `R22.11`), never a reason to
    refuse one.
    """
    if summary is None:
        return (
            f"latency '{run_id}': not recorded "
            "(written before task 33.7, or run without --questions)"
        )
    return f"latency '{run_id}': {_latency_summary_text(summary)}"


def _render_eval_compare(result: EvalCompareCommandResult) -> Rendered:
    """`weft eval compare` — reached only once `weft_cli.eval_commands.EvalCompareCommand`
    has already confirmed corpus and model versions agree (`IncomparableRunsError` otherwise;
    packaging — the active distribution set and their versions — is reported beside the
    comparison rather than confirmed to agree, repair `R22.11`), so this prints that
    confirmation, the pipeline diff itself (reusing `_pipeline_diff_lines` rather than a second
    formatter), and — task 4.9 —
    the per-metric comparison the tool generates itself: what the two pipelines *produced*,
    not only how they resolve. Task 16.1 adds one more line — see
    `_query_rung_difference_lines` — printed only when the two runs' query rungs actually
    differ; the rung is the subject of the comparison, never a reason to refuse it.

    **Task 8.8's own falsification block, printed only when `result.falsification is not
    None`** — a plain `weft eval compare` with no `--baseline` invents no verdict, so it prints
    nothing beyond what it always has. Exit code stays `ExitCode.SUCCESS` either way: this
    command reports a fact, and an indistinguishable difference is not a failed operation.

    **Task 16.9's own paired-difference block, printed only when `result.paired_differences` is
    non-empty** — *beside* the falsification block, before it, never instead of it: the two
    intervals answer different questions (this system's own repetition noise, and whether the
    difference generalises across the questions), and a reader given one cannot infer the other.
    Repair **R38.1** — under `--slice`/`--kind`, the header names the slice it paired over
    (`result.paired_differences_slice`), and a record too old to say which questions were in
    that slice prints `result.paired_differences_reason` on its own line instead of a block
    that would otherwise silently pair the whole run under a slice's own header.

    **`result.reproduction`, repair `R22.4d`** — `--a`/`--b` both named a baseline report file
    rather than a persisted run, so nothing above applies: `_render_reproduction` is the whole
    answer, and none of the header, pipeline-diff or metrics-comparison lines below are printed.

    **Task 33.8's own two latency lines, one per run, always printed** — see `_run_latency_line`.
    Latency is reported beside the comparison, never gated and never part of `metrics_comparison`.

    **Task 34.7's own first line, printed only when `result.targets` is set** — a promotion
    comparison, owner decision Q-E: `result.targets` names the two targets and `result.subject`
    is what changed between them, joined the way `IncomparableRunsError`'s own reasons already
    are — printed before everything else, since it is the fact that makes the comparison below
    a promotion judgement rather than an ordinary same-target one.
    """
    if result.reproduction is not None:
        return _render_reproduction(result, result.reproduction)

    lines = [
        f"'{result.run_a}' vs '{result.run_b}' — same corpus and model versions; pipeline is "
        f"the only fact that may differ:",
        "not compared: pack settings ([packs.*]) — a run record does not carry them, so two runs "
        "differing only there read as identical",
        *(
            f"packaging differs, reported not refused: {difference}"
            for difference in result.packaging_differences
        ),
        *_pipeline_diff_lines(result.pipeline_diff),
        *_query_rung_difference_lines(result.query_rungs),
        *_metrics_comparison_lines(result.metrics_comparison),
        _run_latency_line(result.run_a, result.latency_a),
        _run_latency_line(result.run_b, result.latency_b),
    ]
    if result.targets is not None:
        live, candidate = result.targets
        lines.insert(
            0, f"comparing targets {live} → {candidate}; subject: {'; '.join(result.subject)}"
        )
    if result.paired_differences:
        lines.extend(
            _paired_difference_lines(
                result.paired_differences, slice_=result.paired_differences_slice
            )
        )
    elif result.paired_differences_reason is not None:
        lines.append(result.paired_differences_reason)
    if result.falsification is not None:
        baseline_pipeline = result.baseline_pipeline or ""
        lines.extend(
            _falsification_lines(baseline_pipeline, result.baseline_runs, result.falsification)
        )
        if result.baseline_selection is not None:
            lines.append(_baseline_selection_line(result.baseline_selection))
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_reproduction(result: EvalCompareCommandResult, reproduction: Reproduction) -> Rendered:
    """`weft eval compare` over two baseline report files — repair `R22.4d`. Reached only once
    `weft_cli.eval_commands.EvalCompareCommand` has already judged every published metric inside
    the interval its own repetitions spanned (`BaselineNotReproducedError` otherwise, so a
    `Reproduction` reaches this function only when every verdict is `inside`).
    """
    inside = sum(1 for verdict in reproduction.verdicts if verdict.inside)
    total = len(reproduction.verdicts)
    lines = [
        f"'{result.run_b}' reproduces '{result.run_a}': {inside} of {total} metric(s) inside "
        f"the intervals '{result.run_a}' recorded",
        *(
            f"installation differs at stage '{difference.stage}': {difference.field.value} "
            f"{difference.published} -> {difference.later}"
            for difference in reproduction.provenance
        ),
        *(
            f"  {verdict.metric}: {verdict.later} inside [{verdict.low}, {verdict.high}]"
            for verdict in reproduction.verdicts
        ),
    ]
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _metric_kind(result: MetricRunResult) -> MetricKind:
    """Which contract produced `result` — read straight off the persisted aggregate when there
    is one. A `NotAggregated` metric carries no `kind` of its own — nothing was ever computed to
    read one off — so it falls back to `MetricKind.RETRIEVAL`, the same compromise
    `MetricAggregate.kind` itself documents; every metric this pack scores into a `RunRecord`
    today is a `RetrievalMetric` regardless (`weft_eval.harness` ships no generation-scoring
    counterpart yet), so the fallback names no metric wrongly in practice.
    """
    if isinstance(result, Produced):
        return result.value.kind
    return MetricKind.RETRIEVAL


def _grouped_metric_lines(metrics: Mapping[str, MetricRunResult]) -> list[str]:
    """`metrics`, one heading per `MetricKind` present, retrieval first — task 9.12.

    Printed even when every metric is the one kind: a heading that disappears the moment there
    is only one group is a heading a reader cannot rely on.
    """
    lines: list[str] = []
    for kind in (MetricKind.RETRIEVAL, MetricKind.GENERATION):
        members = {name: result for name, result in metrics.items() if _metric_kind(result) is kind}
        if not members:
            continue
        lines.append(f"  {kind.value}:")
        lines.extend(
            f"    {name}: {_metric_result_text(result)}" for name, result in sorted(members.items())
        )
    return lines


def _query_rung_text(rung: QueryRung | NoQueryRung | None) -> str:
    """`record.query_rung`, rendered — task 16.1. Three states, three readings: a reader must
    not confuse *not recorded* (every record written before this task) with *this run named
    none* (`NoQueryRung`, a measurement in its own right — see that class's own docstring).
    """
    if rung is None:
        return "(not recorded)"
    if isinstance(rung, NoQueryRung):
        # The reason is a whole sentence and already opens *"no query rung was named"*, so a
        # `(none named — …)` wrapper printed it twice: *"(none named — no query rung was named
        # — retrieval ran against …)"*. Found by running the binary at the phase Exit and by
        # nothing in 2,724 tests, which is `phase-step` → *Finish* item 4's whole argument.
        return f"({rung.reason})"
    return f"'{rung.name}' ({rung.identity[:12]}…)"


def _distribution_versions_text(versions: Mapping[str, str] | None) -> str:
    """`record.distribution_versions`, rendered — task 16.3. Three states as `_query_rung_text`
    has three: `None` is *not recorded*, `{}` is *measured, and nothing had recorded metadata*,
    and neither reads as the other.
    """
    if versions is None:
        return "(not recorded)"
    if not versions:
        return "(none had recorded metadata)"
    return ", ".join(f"{name} {version}" for name, version in sorted(versions.items()))


def _question_score_line(key: str, outcome: Produced[float] | NotScored) -> str:
    """One question's own line under a `question scores:` metric block — task 16.4.

    A `Produced[float]` prints to three decimals, the same precision `_metric_result_text`
    already prints a mean at; a `NotScored` prints its reason rather than a number it never
    produced — V4's clause at this granularity, the identical rule `_metric_result_text`
    already carries one level up.
    """
    if isinstance(outcome, NotScored):
        return f"    {key}: not scored ({outcome.reason})"
    return f"    {key}: {outcome.value:.3f}"


def _question_scores_lines(question_scores: Mapping[str, PerQuestionScores] | None) -> list[str]:
    """`record.question_scores`, rendered — task 16.4. `None` is *not recorded*: every record
    written before this task carries means and never the observations under them.
    """
    if question_scores is None:
        return ["question scores: (not recorded)"]
    lines = ["question scores:"]
    for name in sorted(question_scores):
        lines.append(f"  {name}:")
        scores = question_scores[name].scores
        lines.extend(_question_score_line(key, scores[key]) for key in sorted(scores))
    return lines


def _question_set_text(digest: str | None) -> str:
    """The question set a run was scored with — task **16.6**.

    `(not recorded)` covers two states a reader tells apart from the `metrics:` line right
    above: a record written before this task, and a run given no `--questions` at all. Both
    genuinely have no question-set identity to print, and neither is a set this run measured.
    """
    return f"{digest[:12]}…" if digest else "(not recorded)"


def _experiment_text(experiment: ExperimentRun | None) -> str:
    """The experiment a record was run as one arm's one repetition of — task **38.0**.

    `(none)` covers both a run made outside an experiment and a record written before this task:
    neither is a fact `weft eval experiment` recorded, and a reader tracing one run has no reason
    to tell them apart the way `_query_rung_text`'s three states do — there is no second,
    distinct "this run named no experiment" measurement the way `NoQueryRung` is one.
    """
    if experiment is None:
        return "(none)"
    return (
        f"'{experiment.name}' ({experiment.digest[:12]}…) arm {experiment.arm}, "
        f"repetition {experiment.repetition}"
    )


def _render_trace(result: TraceCommandResult) -> Rendered:
    """`weft trace` — every fact `weft_eval.run_record.RunRecord` carries, and nothing this
    module invents on top of it (Q2, `weft_cli.eval_commands`'s own module docstring: this is
    what the persisted record holds, never a stage-level replay nothing in this tree persists).
    Task 4.9 widened the record by one field, `metrics`, so this widens by one block to match.
    Task 9.12 groups that block by `MetricKind` — see `_grouped_metric_lines`. Task 16.1 widens
    it by one more line, `query rung` — see `_query_rung_text`. Task 16.4 widens it by one more
    block, `question scores` — see `_question_scores_lines`.
    """
    record = result.record
    lines = [
        f"run {result.run_id} — recorded {record.recorded_at}",
        f"pipeline: {record.resolved_pipeline.name}",
        f"corpus: '{record.corpus.name}' ({record.corpus.digest[:12]}…)",
        f"query rung: {_query_rung_text(record.query_rung)}",
        f"model versions: {dict(record.model_versions) or '(none recorded)'}",
        f"active distributions: {', '.join(record.active_distributions) or '(none)'}",
        f"distribution versions: {_distribution_versions_text(record.distribution_versions)}",
        f"question set: {_question_set_text(record.question_set_digest)}",
        f"experiment: {_experiment_text(record.experiment)}",
    ]
    if record.metrics:
        lines.append("metrics:")
        lines.extend(_grouped_metric_lines(record.metrics))
    else:
        lines.append("metrics: (none recorded — 'weft eval run' was not given --questions)")
    lines.extend(_question_scores_lines(record.question_scores))
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_eval_plan(result: EvalPlanCommandResult) -> Rendered:
    """`weft eval plan` — task **38.12**. The size of the run the document asks for: one line per
    arm, then one per `(ingest pipeline, corpus)`, and a total of the query executions. What it
    does not print — model calls, hours, memory — is what no document can answer.
    """
    lines = [f"plan for '{result.name}' ({result.digest[:12]}…)"]
    lines.extend(
        f"  {arm.arm}: {arm.pipeline}"
        + (f" → {arm.query_pipeline}" if arm.query_pipeline else "")
        + f", {arm.repetitions} × {arm.questions} question(s) = {arm.executions} execution(s)"
        for arm in result.arms
    )
    lines.extend(
        f"  index {corpus.pipeline} over {corpus.corpus}: {corpus.documents} document(s)"
        for corpus in result.corpora
    )
    lines.append(f"  total query executions: {sum(arm.executions for arm in result.arms)}")
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_eval_experiment(result: EvalExperimentCommandResult) -> Rendered:
    """`weft eval experiment` — task **38.0**. The experiment's own identity and invocation
    first, since `weft trace <run-id>` is what a reader opens next for any one cell of it, then
    one line per record it wrote, in the same arm-then-repetition order the command built them.
    """
    lines = [
        f"experiment '{result.name}' ({result.digest[:12]}…) — invocation "
        f"{result.invocation}: {len(result.runs)} record(s)"
    ]
    lines.extend(f"  {run.arm} r{run.repetition}: run {run.run_id}" for run in result.runs)
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


def _render_eval_table(result: EvalTableCommandResult) -> Rendered:
    """`weft eval table` — task **38.1**. `weft_eval.evidence.render_evidence_table` already
    wrote the whole answer; this only trims the one trailing newline `Rendered.stdout` does not
    carry, the identical convention every other prose renderer here already follows.
    """
    return Rendered(stdout=result.markdown.rstrip("\n"), stderr=None, exit_code=ExitCode.SUCCESS)


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


# --- the twenty-two built-in dispatch wrappers, and `register_renderers` — task 6.20 ------
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
def _render_render(result: RenderCommandResult) -> Rendered:
    """`weft render`'s answer: the rendered text on stdout, and what rendering cost on stderr.

    **The text goes to stdout alone, so `weft render x preview-markdown > x.md`
    produces a usable file.** Everything about the rendering — how many nodes went in, what was
    dropped — goes to stderr, which is the same split `03` → *Output* already draws for every
    other command and the reason this one is usable in a shell pipeline at all. A count folded
    into stdout would corrupt the document it is describing.

    `dropped` is reported rather than summarised away: `Rendition.dropped` exists because a
    renderer that silently omits content it could not represent is the plausible-wrong-answer
    failure this project refuses, and a driver that printed only `text` would hide exactly the
    field that was added to stop it.
    """
    if result.rendition is None:
        return Rendered(
            stdout=None,
            stderr=(
                f"nothing to render: no file in that directory is claimed by an extractor "
                f"'{result.pipeline}' names."
            ),
            exit_code=ExitCode.SUCCESS,
        )
    rendition = result.rendition
    notes = [f"{rendition.nodes_rendered} node(s) rendered as {rendition.media_type}"]
    if rendition.dropped:
        notes.append(f"{len(rendition.dropped)} dropped:")
        notes.extend(
            f"  {item.node_id}: {item.kind.value} — {item.detail}" for item in rendition.dropped
        )
    return Rendered(stdout=rendition.text, stderr="\n".join(notes), exit_code=ExitCode.SUCCESS)


def _dispatch_render(result: object) -> Rendered:
    return _render_render(cast(RenderCommandResult, result))


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


def _dispatch_sources_list(result: object) -> Rendered:
    return _render_sources_list(cast(SourcesListCommandResult, result))


def _dispatch_target_list(result: object) -> Rendered:
    return _render_target_list(cast(TargetListCommandResult, result))


def _dispatch_target_promote(result: object) -> Rendered:
    return _render_target_promote(cast(TargetPromoteCommandResult, result))


def _dispatch_target_rollback(result: object) -> Rendered:
    return _render_target_rollback(cast(TargetRollbackCommandResult, result))


def _dispatch_target_drop(result: object) -> Rendered:
    return _render_target_drop(cast(TargetDropCommandResult, result))


def _dispatch_pipeline_show(result: object) -> Rendered:
    return _render_pipeline_show(cast(PipelineShowCommandResult, result))


def _dispatch_pipeline_derive(result: object) -> Rendered:
    return _render_pipeline_derive(cast(PipelineDeriveCommandResult, result))


def _dispatch_pipeline_validate(result: object) -> Rendered:
    return _render_pipeline_validate(cast(PipelineValidateCommandResult, result))


def _dispatch_pipeline_diff(result: object) -> Rendered:
    return _render_pipeline_diff(cast(PipelineDiffCommandResult, result))


def _dispatch_pipeline_estimate(result: object) -> Rendered:
    return _render_pipeline_estimate(cast(PipelineEstimateCommandResult, result))


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


def _dispatch_eval_experiment(result: object) -> Rendered:
    return _render_eval_experiment(cast(EvalExperimentCommandResult, result))


def _dispatch_eval_plan(result: object) -> Rendered:
    return _render_eval_plan(cast(EvalPlanCommandResult, result))


def _dispatch_eval_table(result: object) -> Rendered:
    return _render_eval_table(cast(EvalTableCommandResult, result))


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
    so every one of these twenty-two calls to `registrar.add_renderer` is indistinguishable, at
    the seam, from the identical call any third-party pack's own `register()` makes for its own
    result type. **This module may not name the pack that proves it**, and that is fitness
    function 9(b) rather than shyness: a first-party file naming the out-of-tree pack would make
    the pack part of what it is meant to be independent of.
    """
    registrar.add_renderer(IndexCommandResult, _dispatch_index)
    registrar.add_renderer(RenderCommandResult, _dispatch_render)
    registrar.add_renderer(PluginsListCommandResult, _dispatch_plugins_list)
    registrar.add_renderer(PluginsDoctorCommandResult, _dispatch_plugins_doctor)
    registrar.add_renderer(InitCommandResult, _dispatch_init)
    registrar.add_renderer(DeleteCommandResult, _dispatch_delete)
    registrar.add_renderer(ReconcileCommandResult, _dispatch_reconcile)
    registrar.add_renderer(PipelineListCommandResult, _dispatch_pipeline_list)
    registrar.add_renderer(SourcesListCommandResult, _dispatch_sources_list)
    registrar.add_renderer(TargetListCommandResult, _dispatch_target_list)
    registrar.add_renderer(TargetPromoteCommandResult, _dispatch_target_promote)
    registrar.add_renderer(TargetRollbackCommandResult, _dispatch_target_rollback)
    registrar.add_renderer(TargetDropCommandResult, _dispatch_target_drop)
    registrar.add_renderer(PipelineShowCommandResult, _dispatch_pipeline_show)
    registrar.add_renderer(PipelineDeriveCommandResult, _dispatch_pipeline_derive)
    registrar.add_renderer(PipelineValidateCommandResult, _dispatch_pipeline_validate)
    registrar.add_renderer(PipelineDiffCommandResult, _dispatch_pipeline_diff)
    registrar.add_renderer(PipelineEstimateCommandResult, _dispatch_pipeline_estimate)
    registrar.add_renderer(ConfigGetCommandResult, _dispatch_config_get)
    registrar.add_renderer(ConfigSetCommandResult, _dispatch_config_set)
    registrar.add_renderer(EvalRunCommandResult, _dispatch_eval_run)
    registrar.add_renderer(EvalCompareCommandResult, _dispatch_eval_compare)
    registrar.add_renderer(TraceCommandResult, _dispatch_trace)
    registrar.add_renderer(EvalMetricsCommandResult, _dispatch_eval_metrics)
    registrar.add_renderer(EvalExperimentCommandResult, _dispatch_eval_experiment)
    registrar.add_renderer(EvalPlanCommandResult, _dispatch_eval_plan)
    registrar.add_renderer(EvalTableCommandResult, _dispatch_eval_table)
    registrar.add_renderer(AskCommandResult, _dispatch_ask)


def _bootstrap_built_in_renderers() -> None:
    """Seed `_renderer_registry` with the built-ins the moment this module is imported.

    `weft_cli.commands.register` calling `register_renderers` (through discovery, or through
    `weft_engine.registry_bootstrap.build_dependencies` calling `register_renderers_from_reports`
    beside it) is what a *running* `weft` does — but this module is usable stand-alone, and
    most of this module's own tests, plus every caller that pre-dates task 6.20, call
    `render_outcome` directly without ever running discovery first. This runs the identical
    `register_renderers`/`register_renderers_from_reports` path a real discovery pass would,
    against a throwaway `Registry`/`PackRegistrar`, so the built-ins are reachable either way
    without a second, independently-drifting registration mechanism: a later, real discovery
    pass registering the same twenty-two callables again is the identical-renderer repeat case
    `register_renderers_from_reports` already treats as a no-op, never a collision.
    """
    registrar = PackRegistrar(Registry(), distribution="weft-cli")
    register_renderers(registrar)
    report = PackReport(
        pack="cli",
        distribution="weft-cli",
        status=PackStatus.ACTIVE,
        renderers=registrar.renderers,
    )
    register_renderers_from_reports([report])


_bootstrap_built_in_renderers()
