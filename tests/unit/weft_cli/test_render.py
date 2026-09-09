"""Unit tests for `weft_cli.render`.

Mirrors `packages/weft-rag/src/weft_cli/render.py`. Covers the property task 3.2 promises: the
built-in commands' human output stays byte-identical to what the retired `handle_*` functions
in `weft_cli.cli` printed directly, now computed from a `CommandResult` instead of interleaved
with the logic that produced it. Each test below reproduces the exact literal a pre-3.2 handler
test asserted (see `docs/build-ledger.md` 3.2's own evidence entry for how this was checked
commit-to-commit), plus the generic `Outcome` vocabulary (`NothingToProduce`/`Failed`) and the
unknown-result fallback a third party's own `Command` would exercise.

Task **3.11** folds `weft route`'s own retired `RouteCommandResult`/`_render_route` into
`AskCommandResult`/`_render_ask` — see the tests below covering the routed shape, and the
`streamed` keyword `render_outcome` grew to fix the double-print `weft route` inherited.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection
from typing import cast

import pytest

from weft_cli import commands, render
from weft_cli.commands import (
    AskCommandResult,
    CommandRefusalError,
    DeleteCommandResult,
    IndexCommandResult,
    PluginsDoctorCommandResult,
    PluginsListCommandResult,
    ReconcileCommandResult,
)
from weft_cli.deletion import ParticipantOutcome
from weft_cli.error_envelope import ENVELOPE_VERSION
from weft_cli.exit_codes import ExitCode
from weft_cli.output import AskFormat
from weft_cli.reconcile import ReconcileEstimateOutcome, ReconcileOutcome
from weft_command.contract import CommandResult
from weft_generate.payload import Answer, AnswerStance, Citation
from weft_kernel.discovery import PackRegistrar, PackReport, PackStatus
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, NothingToProduce, Produced
from weft_kernel.registry import (
    DisplacedRegistration,
    DuplicateRegistrationError,
    Registry,
    UnknownPluginError,
)
from weft_kernel.runner import RunSummary
from weft_retrieve.payload import Query
from weft_store import ReconcileEstimate, ReconcileMode, ReconcileReport


def test_render_index_success_matches_the_retired_handler_s_line() -> None:
    # Arrange — `handle_index`'s own line, byte for byte.
    summary = RunSummary(produced=2, nothing_to_produce=1, failed=0)
    result = IndexCommandResult(summary=summary, stored_count=2)

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout == "produced 2, nothing to produce 1, failed 0. nodes now stored: 2."
    assert rendered.stderr is None
    assert rendered.exit_code is ExitCode.SUCCESS


def test_render_index_with_failures_prints_reasons_to_stderr_and_exits_1() -> None:
    # Arrange
    summary = RunSummary(produced=1, nothing_to_produce=0, failed=1, failed_reasons=("bad file",))
    result = IndexCommandResult(summary=summary, stored_count=None)

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert (
        rendered.stdout == "produced 1, nothing to produce 0, failed 1. nodes now stored: unknown."
    )
    assert rendered.stderr == "  failed: bad file"
    assert rendered.exit_code is ExitCode.OPERATION_FAILED


def test_render_ask_text_with_no_hits_matches_the_retired_sentence() -> None:
    # Arrange
    result = AskCommandResult(question="q", top_k=5, format=AskFormat.TEXT, hits=())

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout == "no matching passages found."
    assert rendered.exit_code is ExitCode.SUCCESS


def test_render_ask_text_ranks_hits_by_position() -> None:
    # Arrange
    from weft_cli.ask import AskHit

    hits = (
        AskHit(rank=1, node_id="n1", score=0.9, content="first"),
        AskHit(rank=2, node_id="n2", score=0.1, content="second"),
    )
    result = AskCommandResult(question="q", top_k=5, format=AskFormat.TEXT, hits=hits)

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout == "1. first\n2. second"


def test_render_ask_json_never_prints_the_raw_score_to_a_human_but_carries_it() -> None:
    # Arrange — `docs/03-cli.md` -> Output, Score display: JSON is the one reader who gets it.
    from weft_cli.ask import AskHit

    hits = (AskHit(rank=1, node_id="n1", score=-0.09, content="c"),)
    result = AskCommandResult(question="q", top_k=5, format=AskFormat.JSON, hits=hits)

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout is not None
    assert '"score":-0.09' in rendered.stdout


def _routed_answer() -> tuple[Query, Answer]:
    # Shared by the two tests below — a citation must resolve into `used`, to exactly one
    # passage (`Answer`'s own `_citations_resolve` validator), so this builds the smallest
    # passage a marker can legitimately point at.
    from weft_kernel.payload import MediaType, Node
    from weft_retrieve.payload import Passage
    from weft_store import Scored

    node = Node.synthetic(content="a passage", media_type=MediaType.TEXT, reason="test")
    passage = Passage(scored=Scored(value=node, score=0.9), rank=0, retrieved_by="test", label="1")
    query = Query(text="q")
    answer = Answer(
        origin=query,
        text="the answer",
        stance=AnswerStance.ANSWERED,
        citations=(
            Citation(marker="1", node_id=node.id, uri="doc://a", quote="a passage", page=7),
        ),
        used=(passage,),
        answered_by="scripted",
    )
    return query, answer


def test_render_ask_prints_the_routed_answer_and_its_citations_when_nothing_streamed() -> None:
    # Arrange — the default reading (`streamed` defaults to `False`): nothing showed this
    # answer live yet (e.g. `--quiet`, or a caller that never passes `streamed`), so the full
    # text belongs in `Rendered.stdout` — G6's "`--quiet` suppresses progress but keeps the
    # result."
    _query, answer = _routed_answer()
    result = AskCommandResult(
        question="q", top_k=5, format=AskFormat.TEXT, pipeline_name="specific", answer=answer
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout is not None
    lines = rendered.stdout.splitlines()
    assert lines[0] == "routed to: specific"
    assert lines[1] == "the answer"
    # R9.2's human half: the marker and the uri alone made several nodes of one document cite
    # identically. The node id is what makes the node that answered nameable, and the page is
    # what stops a reader searching a whole document for one claim.
    _query_again, answer_again = _routed_answer()
    citation = answer_again.citations[0]
    assert citation.uri in lines[2]
    assert "[1]" in lines[2]
    assert str(citation.node_id) in lines[2]
    assert "7" in lines[2]


def test_render_ask_omits_the_answer_text_when_it_already_streamed() -> None:
    # Arrange — task 3.11's own fix for `weft route`'s inherited double-print: when
    # `PrintingSink`/`JsonSink` already showed the answer live, `_render_ask` leaves the text
    # out of the final render rather than printing it a second time. The pipeline name and
    # citations still print — they were never streamed.
    _query, answer = _routed_answer()
    result = AskCommandResult(
        question="q", top_k=5, format=AskFormat.TEXT, pipeline_name="specific", answer=answer
    )

    # Act
    rendered = render.render_outcome(Produced(value=result), streamed=True)

    # Assert
    assert rendered.stdout is not None
    lines = rendered.stdout.splitlines()
    assert lines[0] == "routed to: specific"
    assert "doc://a" in lines[1]
    assert "the answer" not in rendered.stdout


def test_render_ask_under_global_json_emits_only_json_on_stdout() -> None:
    # Arrange — carried repair **R9.2**, second half. `docs/03-cli.md` -> *Output*: "`--json`
    # switches to newline-delimited JSON events and disables every decoration... That is the
    # scripting contract: same events, no parsing of prose." `_render_ask`'s JSON guard read
    # `result.format`, which is `weft ask --format json`'s per-command choice and is `TEXT`
    # here — the *global* `--json` never reached this function at all, so a routed answer
    # printed `routed to: ...` and its citations as prose after the event stream. Confirmed
    # live at task 10.16 from outside this repository: five lines of prose on stdout.
    _query, answer = _routed_answer()
    result = AskCommandResult(
        question="q", top_k=5, format=AskFormat.TEXT, pipeline_name="specific", answer=answer
    )

    # Act
    rendered = render.render_outcome(Produced(value=result), as_json=True)

    # Assert — every line on stdout parses, which is the property a consumer needs; asserting
    # "no prose" by absence of one phrase would pass for prose nobody thought to name.
    assert rendered.stdout is not None
    for line in rendered.stdout.splitlines():
        json.loads(line)


def test_the_answer_envelope_carries_every_field_a_citation_holds() -> None:
    # Arrange — carried repair **R9.2**, first half, stated as *every field a persisted
    # `Citation` carries reaches some rendering*. `weft_generate.payload.Citation` holds five
    # fields and the human line rendered two of them, so whether the node that answered was a
    # `raptor` summary was unobservable — which is what task 10.16 was asked to show and could
    # not.
    _query, answer = _routed_answer()
    citation = answer.citations[0]
    result = AskCommandResult(
        question="q", top_k=5, format=AskFormat.TEXT, pipeline_name="specific", answer=answer
    )

    # Act
    rendered = render.render_outcome(Produced(value=result), as_json=True)

    # Assert
    assert rendered.stdout is not None
    envelope = json.loads(rendered.stdout.splitlines()[-1])
    emitted = envelope["citations"][0]
    assert emitted["marker"] == citation.marker
    assert emitted["node_id"] == str(citation.node_id)
    assert emitted["source_id"] == citation.source_id
    assert emitted["uri"] == citation.uri
    assert emitted["quote"] == citation.quote
    assert emitted["page"] == citation.page


def test_the_answer_envelope_is_discriminated_by_kind_like_the_error_envelope() -> None:
    # Arrange — `weft_cli.sinks.LineKind`, ledger task **6.16**: `weft --json` writes more than
    # one line shape on one descriptor and "a consumer must not have to tell them apart by
    # which keys are present". A third shape arriving without joining that vocabulary would
    # reopen exactly the key-sniffing this enum ended.
    from weft_cli.sinks import LineKind

    _query, answer = _routed_answer()
    result = AskCommandResult(
        question="q", top_k=5, format=AskFormat.TEXT, pipeline_name="specific", answer=answer
    )

    # Act
    rendered = render.render_outcome(Produced(value=result), as_json=True)

    # Assert
    assert rendered.stdout is not None
    envelope = json.loads(rendered.stdout.splitlines()[-1])
    assert envelope["kind"] == LineKind.ANSWER_ENVELOPE.value
    assert envelope["kind"] not in {LineKind.STREAM_EVENT.value, LineKind.ERROR_ENVELOPE.value}
    assert envelope["envelope_version"]


def test_the_answer_envelope_carries_the_text_even_when_it_already_streamed() -> None:
    # Arrange — the prose branch omits an answer that `PrintingSink`/`JsonSink` already showed,
    # so a human does not read the same paragraph twice (task 3.11). That reasoning does not
    # cross to a machine: a field present or absent depending on which sink ran is the state
    # `ErrorEnvelope`'s own docstring refuses for `valid_options` — "indistinguishable from
    # 'there really were no alternatives'". The envelope is self-contained either way.
    _query, answer = _routed_answer()
    result = AskCommandResult(
        question="q", top_k=5, format=AskFormat.TEXT, pipeline_name="specific", answer=answer
    )

    # Act
    rendered = render.render_outcome(Produced(value=result), as_json=True, streamed=True)

    # Assert
    assert rendered.stdout is not None
    envelope = json.loads(rendered.stdout.splitlines()[-1])
    assert envelope["text"] == answer.text
    assert envelope["pipeline_name"] == "specific"


def test_render_plugins_list_delegates_to_the_shared_renderer() -> None:
    # Arrange
    reports = (PackReport(pack="chunk", distribution="weft-chunk", status=PackStatus.ACTIVE),)
    result = PluginsListCommandResult(reports=reports)

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout == "chunk (weft-chunk): active (0 contributed)"


def test_render_plugins_doctor_delegates_to_the_shared_renderer_including_displaced() -> None:
    # Arrange
    class _Chunker:
        pass

    reports = (
        PackReport(
            pack="loser", distribution="weft-loser", status=PackStatus.ACTIVE, contributed=1
        ),
    )
    displaced = (
        DisplacedRegistration(
            contract=_Chunker,
            name="shared",
            distribution="weft-loser",
            winner="weft-winner",
            pin="_Chunker:shared",
        ),
    )
    result = PluginsDoctorCommandResult(
        reports=reports,
        displaced=displaced,
        unconsulted_pins=(),
        tracing="not configured",
        skew=(),
        unreachable_contributions=(),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout is not None
    assert "displaced" in rendered.stdout


def test_render_outcome_handles_nothing_to_produce_generically() -> None:
    # Arrange — no built-in returns this today; a third party's `Command` may.
    outcome = NothingToProduce(reason="no pipelines installed")

    # Act
    rendered = render.render_outcome(outcome)

    # Assert
    assert rendered.stdout == "no pipelines installed"
    assert rendered.exit_code is ExitCode.SUCCESS


def test_render_outcome_handles_failed_generically() -> None:
    # Arrange
    outcome = Failed(reason="collection does not exist")

    # Act
    rendered = render.render_outcome(outcome)

    # Assert
    assert rendered.stderr == "collection does not exist"
    assert rendered.exit_code is ExitCode.OPERATION_FAILED


def test_render_outcome_falls_back_to_structured_output_for_an_unknown_result_type() -> None:
    # Arrange — a stranger's `CommandResult` this module was never written against by name.
    class _StrangerResult(CommandResult):
        detail: str

    # Act
    rendered = render.render_outcome(Produced(value=_StrangerResult(detail="hello")))

    # Assert
    assert rendered.stdout is not None
    assert "hello" in rendered.stdout
    assert rendered.exit_code is ExitCode.SUCCESS


def test_render_refusal_reads_the_exit_code_off_a_command_refusal_error() -> None:
    # Arrange
    exc = CommandRefusalError("refused by policy", exit_code=ExitCode.POLICY_REFUSED)

    # Act
    rendered = render.render_refusal(exc)

    # Assert
    assert rendered.stderr == "refused by policy"
    assert rendered.exit_code is ExitCode.POLICY_REFUSED


def test_render_refusal_falls_back_to_exit_code_for_any_other_weft_error() -> None:
    # Arrange
    exc = WeftError("something in the library refused")

    # Act
    rendered = render.render_refusal(exc)

    # Assert
    assert rendered.exit_code is ExitCode.OPERATION_FAILED


# --- task 5.2d: the structured error envelope under --json --------------------------------


def test_render_refusal_puts_str_exc_on_stderr_when_json_was_not_asked_for() -> None:
    # Arrange — the default, and every caller before this task: human output is unchanged.
    exc = UnknownPluginError("unknown retriever: 'graf'", valid_options=("graph", "vector"))

    # Act
    rendered = render.render_refusal(exc)

    # Assert
    assert rendered.stdout is None
    assert rendered.stderr == "unknown retriever: 'graf'"


def test_render_refusal_emits_a_structured_envelope_on_stdout_under_as_json() -> None:
    # Arrange
    exc = UnknownPluginError("unknown retriever: 'graf'", valid_options=("graph", "vector"))

    # Act
    rendered = render.render_refusal(exc, as_json=True)

    # Assert — nothing on stderr: the envelope is the whole answer a script reads.
    assert rendered.stderr is None
    assert rendered.exit_code is ExitCode.RESOLUTION_FAILED
    dumped = json.loads(cast(str, rendered.stdout))
    assert dumped["error"] == "UnknownPluginError"
    assert dumped["valid_options"] == ["graph", "vector"]
    assert dumped["rendered"] == "unknown retriever: 'graf'"
    assert dumped["exit_code"] == int(ExitCode.RESOLUTION_FAILED)
    assert dumped["envelope_version"] == ENVELOPE_VERSION


def test_render_refusal_as_json_still_reads_the_exit_code_off_a_command_refusal_error() -> None:
    # Arrange — the `CommandRefusalError` branch stays the one source of truth for its own
    # exit code; `as_json` only changes where the envelope goes, never how the code is chosen.
    exc = CommandRefusalError("refused by policy", exit_code=ExitCode.POLICY_REFUSED)

    # Act
    rendered = render.render_refusal(exc, as_json=True)

    # Assert
    assert rendered.exit_code is ExitCode.POLICY_REFUSED
    dumped = json.loads(cast(str, rendered.stdout))
    assert dumped["error"] == "CommandRefusalError"
    assert dumped["exit_code"] == int(ExitCode.POLICY_REFUSED)


def test_render_refusal_as_json_carries_null_valid_options_when_the_error_has_none() -> None:
    # Arrange — an ordinary `WeftError` with no alternatives to offer; the field is present
    # and explicitly null, never silently dropped.
    exc = WeftError("something in the library refused")

    # Act
    rendered = render.render_refusal(exc, as_json=True)

    # Assert
    dumped = json.loads(cast(str, rendered.stdout))
    assert dumped["valid_options"] is None


# --- task 3.7: init, pipeline ..., config ... --------------------------------------------


def test_render_init_names_the_file_it_wrote() -> None:
    from weft_cli.commands import InitCommandResult

    rendered = render.render_outcome(Produced(value=InitCommandResult(path="weft.toml")))

    assert rendered.stdout == "wrote weft.toml."
    assert rendered.exit_code is ExitCode.SUCCESS


def test_render_pipeline_list_joins_names_one_per_line() -> None:
    from weft_cli.pipeline_commands import PipelineListCommandResult

    rendered = render.render_outcome(
        Produced(value=PipelineListCommandResult(names=("base", "specific")))
    )

    assert rendered.stdout == "base\nspecific"


def test_render_pipeline_list_names_none_known_when_empty() -> None:
    from weft_cli.pipeline_commands import PipelineListCommandResult

    rendered = render.render_outcome(Produced(value=PipelineListCommandResult(names=())))

    assert rendered.stdout == "no pipelines known."


def test_render_pipeline_show_prints_provenance_vars_and_the_two_g2_fields() -> None:
    # `docs/03-cli.md`: a `show` that omits unapplied operators/unplaced contributions
    # fails the task — both are printed here even though both are empty, which is the
    # property this test exists to pin.
    from weft_cli.pipeline_commands import PipelineShowCommandResult
    from weft_kernel.resolution import ResolvedPipeline, ResolvedStage

    resolved = ResolvedPipeline(
        name="base",
        vars={"target_lang": "de"},
        stages=(
            ResolvedStage(
                id="chunk",
                contract="Chunker",
                use="fixed-size",
                distribution="weft-chunk",
                provenance="base",
            ),
        ),
    )

    rendered = render.render_outcome(Produced(value=PipelineShowCommandResult(resolved=resolved)))

    assert rendered.stdout is not None
    assert "pipeline: base" in rendered.stdout
    assert "target_lang = de" in rendered.stdout
    assert "chunk: Chunker:fixed-size" in rendered.stdout
    assert "distribution: weft-chunk" in rendered.stdout
    assert "provenance: base" in rendered.stdout
    assert "unapplied operators: (none)" in rendered.stdout
    assert "unplaced contributions: (none)" in rendered.stdout


def test_render_pipeline_derive_names_the_file_and_the_next_command() -> None:
    from weft_cli.pipeline_commands import PipelineDeriveCommandResult

    result = PipelineDeriveCommandResult(
        parent="base", name="specific", path="pipelines/specific.yaml"
    )
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout == (
        "wrote pipelines/specific.yaml — 'specific' extends 'base'. Run "
        "`weft pipeline validate specific` next."
    )


def test_render_pipeline_validate_reports_the_stage_count() -> None:
    from weft_cli.pipeline_commands import PipelineValidateCommandResult

    result = PipelineValidateCommandResult(name="base", stage_count=3)
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout == "'base' resolves cleanly: 3 stage(s)."


def test_render_pipeline_diff_reports_identical_when_nothing_differs() -> None:
    from weft_cli.pipeline_commands import PipelineDiffCommandResult
    from weft_cli.pipeline_diff import PipelineDiff

    diff = PipelineDiff(
        a_name="base",
        b_name="base",
        identical=True,
        added_stages=(),
        removed_stages=(),
        changed_stages=(),
        var_changes=(),
        unapplied_operators_changed=False,
        unplaced_contributions_changed=False,
    )
    rendered = render.render_outcome(Produced(value=PipelineDiffCommandResult(diff=diff)))

    assert rendered.stdout == "'base' and 'base' resolve identically."


def test_render_pipeline_diff_lists_an_added_stage() -> None:
    from weft_cli.pipeline_commands import PipelineDiffCommandResult
    from weft_cli.pipeline_diff import PipelineDiff
    from weft_kernel.resolution import ResolvedStage

    added = ResolvedStage(
        id="keywords",
        contract="Enhancer",
        use="keybert",
        distribution="weft-kw",
        provenance="specific",
    )
    diff = PipelineDiff(
        a_name="base",
        b_name="specific",
        identical=False,
        added_stages=(added,),
        removed_stages=(),
        changed_stages=(),
        var_changes=(),
        unapplied_operators_changed=False,
        unplaced_contributions_changed=False,
    )
    rendered = render.render_outcome(Produced(value=PipelineDiffCommandResult(diff=diff)))

    assert rendered.stdout is not None
    assert "'base' vs 'specific':" in rendered.stdout
    assert "+ keywords (Enhancer:keybert)" in rendered.stdout


def test_render_config_get_prints_key_equals_value_without_origin_by_default() -> None:
    from weft_cli.config_commands import ConfigGetCommandResult
    from weft_cli.config_surface import ConfigEntry, ConfigOrigin

    entries = (ConfigEntry(key="services.embed", value="hash", origin=ConfigOrigin.DEFAULT),)
    result = ConfigGetCommandResult(entries=entries, show_origin=False)
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout == "services.embed = hash"


def test_render_config_get_appends_origin_when_asked() -> None:
    from weft_cli.config_commands import ConfigGetCommandResult
    from weft_cli.config_surface import ConfigEntry, ConfigOrigin

    entries = (ConfigEntry(key="services.embed", value="hash", origin=ConfigOrigin.FILE),)
    result = ConfigGetCommandResult(entries=entries, show_origin=True)
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout == "services.embed = hash  (origin: file)"


def test_render_config_set_names_the_key_the_value_and_the_file() -> None:
    from weft_cli.config_commands import ConfigSetCommandResult

    result = ConfigSetCommandResult(key="services.embed", value="openai", path="weft.toml")
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout == "set services.embed = openai in weft.toml."


def _run_record(*, pipeline_name: str = "index", corpus_digest: str = "a" * 64):
    from weft_eval.run_record import CorpusIdentity, RunRecord
    from weft_kernel.resolution import ResolvedPipeline

    return RunRecord(
        recorded_at="2026-08-20T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name=pipeline_name),
        corpus=CorpusIdentity(name="corpus", digest=corpus_digest),
    )


def test_render_eval_run_names_the_run_id_and_the_index_summary() -> None:
    from weft_cli.eval_commands import EvalRunCommandResult

    result = EvalRunCommandResult(
        run_id="run-1",
        path="corpus",
        summary=RunSummary(produced=1, nothing_to_produce=0, failed=0),
        stored_count=1,
        record=_run_record(),
        wall_clock_seconds=0.5,
    )
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout is not None
    assert "run run-1 persisted" in rendered.stdout
    assert "produced 1, nothing to produce 0, failed 0" in rendered.stdout
    assert "wall clock: 0.50s" in rendered.stdout
    assert rendered.exit_code is ExitCode.SUCCESS


def test_render_eval_run_with_failures_exits_1() -> None:
    from weft_cli.eval_commands import EvalRunCommandResult

    result = EvalRunCommandResult(
        run_id="run-1",
        path="corpus",
        summary=RunSummary(produced=0, nothing_to_produce=0, failed=1, failed_reasons=("bad",)),
        stored_count=None,
        record=_run_record(),
        wall_clock_seconds=0.1,
    )
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stderr == "  failed: bad"
    assert rendered.exit_code is ExitCode.OPERATION_FAILED


def test_render_eval_compare_confirms_the_environment_matched_before_the_diff() -> None:
    from weft_cli.eval_commands import EvalCompareCommandResult
    from weft_cli.pipeline_diff import PipelineDiff

    diff = PipelineDiff(
        a_name="base",
        b_name="specific",
        identical=False,
        added_stages=(),
        removed_stages=(),
        changed_stages=(),
        var_changes=(),
        unapplied_operators_changed=False,
        unplaced_contributions_changed=False,
    )
    result = EvalCompareCommandResult(
        run_a="run-a",
        run_b="run-b",
        corpus_matches=True,
        model_versions_match=True,
        active_distributions_match=True,
        pipeline_diff=diff,
        metrics_comparison={},
    )
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout is not None
    assert "'run-a' vs 'run-b'" in rendered.stdout
    assert "same corpus, model versions and active distributions" in rendered.stdout
    assert "metrics: (none scored on either run" in rendered.stdout


def test_render_eval_compare_reports_a_per_metric_delta() -> None:
    # Task 4.9 — the comparison the tool generates itself: not only that the pipelines
    # differ, but what they scored.
    from weft_cli.eval_commands import EvalCompareCommandResult, MetricComparison
    from weft_cli.pipeline_diff import PipelineDiff
    from weft_eval.aggregate import MetricAggregate
    from weft_eval.run_record import NotAggregated
    from weft_kernel.payload import Produced as KernelProduced

    diff = PipelineDiff(
        a_name="base",
        b_name="specific",
        identical=True,
        added_stages=(),
        removed_stages=(),
        changed_stages=(),
        var_changes=(),
        unapplied_operators_changed=False,
        unplaced_contributions_changed=False,
    )
    result = EvalCompareCommandResult(
        run_a="run-a",
        run_b="run-b",
        corpus_matches=True,
        model_versions_match=True,
        active_distributions_match=True,
        pipeline_diff=diff,
        metrics_comparison={
            "precision@5": MetricComparison(
                a=KernelProduced(
                    value=MetricAggregate(
                        reported_name="precision@5",
                        mean=0.4,
                        n=2,
                        stdev=0.1,
                        excluded=0,
                        nothing_to_produce=0,
                    )
                ),
                b=KernelProduced(
                    value=MetricAggregate(
                        reported_name="precision@5",
                        mean=0.6,
                        n=2,
                        stdev=0.1,
                        excluded=0,
                        nothing_to_produce=0,
                    )
                ),
            ),
            "recall@5": MetricComparison(
                a=NotAggregated(reason="not measured"),
                b=KernelProduced(
                    value=MetricAggregate(
                        reported_name="recall@5",
                        mean=0.5,
                        n=1,
                        stdev=None,
                        excluded=0,
                        nothing_to_produce=0,
                    )
                ),
            ),
        },
    )
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout is not None
    assert "precision@5: 0.400 (n=2, ±0.100) vs 0.600 (n=2, ±0.100)  Δ+0.200" in rendered.stdout
    assert "recall@5: not produced (not measured) vs 0.500 (n=1, ±n/a)" in rendered.stdout


def test_render_trace_prints_every_field_the_run_record_carries() -> None:
    from weft_cli.eval_commands import TraceCommandResult

    result = TraceCommandResult(run_id="run-1", record=_run_record())
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout is not None
    assert "run run-1 — recorded 2026-08-20T00:00:00+00:00" in rendered.stdout
    assert "pipeline: index" in rendered.stdout
    assert "corpus: 'corpus'" in rendered.stdout
    assert "model versions: (none recorded)" in rendered.stdout
    assert "active distributions: (none)" in rendered.stdout
    assert "metrics: (none recorded" in rendered.stdout


def test_render_eval_metrics_names_the_gate_safe_and_gate_unsafe_metrics() -> None:
    from weft_cli.eval_commands import EvalMetricsCommandResult

    result = EvalMetricsCommandResult(gate_safe=("exact-match",), gate_unsafe=("faithfulness",))
    rendered = render.render_outcome(Produced(value=result))

    assert rendered.stdout is not None
    assert "runs in the gate (no credentials, no network): exact-match" in rendered.stdout
    assert "does not run in the gate: faithfulness" in rendered.stdout
    assert rendered.exit_code is ExitCode.SUCCESS


def test_delete_names_every_participant_and_fails_when_one_did() -> None:
    # Arrange
    result = DeleteCommandResult(
        source_id="doc-1",
        participants=(
            ParticipantOutcome(
                contract="NodeStore", plugin="pgvector", distribution="weft-store", node_count=7
            ),
            ParticipantOutcome(
                contract="GraphStore",
                plugin="graph",
                distribution="weft-kg",
                error="RuntimeError: connection refused",
            ),
        ),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.exit_code is ExitCode.OPERATION_FAILED
    assert "pgvector (weft-store): 7 node(s) removed" in (rendered.stdout or "")
    assert "graph (weft-kg) — RuntimeError: connection refused" in (rendered.stderr or "")


def test_delete_with_no_participant_says_so_and_succeeds() -> None:
    # Arrange
    result = DeleteCommandResult(source_id="doc-1", participants=())

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS
    assert rendered.stdout == "nothing installed holds data for 'doc-1'; nothing was deleted."


def test_reconcile_reports_an_interrupted_pass_as_unfinished_rather_than_as_a_failure() -> None:
    # Arrange
    result = ReconcileCommandResult(
        mode=ReconcileMode.REPAIR,
        dry_run=False,
        participants=(
            ReconcileOutcome(
                contract="GraphStore",
                plugin="graph",
                distribution="weft-kg",
                report=ReconcileReport(
                    mode=ReconcileMode.REPAIR, examined=2, removed=2, remaining=3
                ),
            ),
        ),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.exit_code is ExitCode.OPERATION_FAILED
    assert "interrupted, 3 left; run again" in (rendered.stdout or "")
    assert rendered.stderr is None


def test_reconcile_dry_run_names_the_participants_and_asks_none_of_them() -> None:
    # Arrange
    result = ReconcileCommandResult(
        mode=ReconcileMode.FULL,
        dry_run=True,
        participants=(),
        would_ask=("graph (weft-kg)",),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS
    assert "would run against 1 participant(s):\n  graph (weft-kg)" in (rendered.stdout or "")


def test_reconcile_full_states_its_cost_before_the_outcome_lines() -> None:
    # Arrange — task 5.1c's worked example: the cost line for a participant appears ahead of
    # what converging it actually did.
    result = ReconcileCommandResult(
        mode=ReconcileMode.FULL,
        dry_run=False,
        participants=(
            ReconcileOutcome(
                contract="GraphStore",
                plugin="graph",
                distribution="weft-kg",
                report=ReconcileReport(mode=ReconcileMode.FULL, examined=1, removed=0),
            ),
        ),
        estimates=(
            ReconcileEstimateOutcome(
                contract="GraphStore",
                plugin="graph",
                distribution="weft-kg",
                estimate=ReconcileEstimate(
                    mode=ReconcileMode.FULL,
                    pending=4312,
                    description="4312 nodes have no graph data",
                    model_calls=4312,
                ),
            ),
        ),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    stdout = rendered.stdout or ""
    cost_at = stdout.index("backfill will make ~4312 model calls")
    outcome_at = stdout.index("examined 1, removed 0")
    assert cost_at < outcome_at
    assert rendered.exit_code is ExitCode.SUCCESS


def test_reconcile_estimate_names_zero_model_calls_with_no_second_line() -> None:
    # Arrange — a node store's own honest floor: no backfill, so no second line to print.
    result = ReconcileCommandResult(
        mode=ReconcileMode.FULL,
        dry_run=False,
        participants=(
            ReconcileOutcome(
                contract="NodeStore",
                plugin="pgvector",
                distribution="weft-store",
                report=ReconcileReport(mode=ReconcileMode.FULL),
            ),
        ),
        estimates=(
            ReconcileEstimateOutcome(
                contract="NodeStore",
                plugin="pgvector",
                distribution="weft-store",
                estimate=ReconcileEstimate(
                    mode=ReconcileMode.FULL, description="no unfinished deletions"
                ),
            ),
        ),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    stdout = rendered.stdout or ""
    assert "pgvector (weft-store): no unfinished deletions" in stdout
    assert "model calls" not in stdout


def test_reconcile_a_failing_estimate_is_named_rather_than_silently_dropped() -> None:
    # Arrange
    result = ReconcileCommandResult(
        mode=ReconcileMode.FULL,
        dry_run=True,
        participants=(),
        would_ask=("graph (weft-kg)",),
        estimates=(
            ReconcileEstimateOutcome(
                contract="GraphStore",
                plugin="graph",
                distribution="weft-kg",
                error="RuntimeError: graph index unavailable",
            ),
        ),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert "estimate failed — RuntimeError: graph index unavailable" in (rendered.stdout or "")


def test_index_renders_the_automatic_reconcile_pass_appended_to_its_own_summary() -> None:
    # Arrange — task 5.1c: `weft index`'s own automatic pass, rendered through the identical
    # `_render_reconcile` `weft reconcile` itself uses.
    result = IndexCommandResult(
        summary=RunSummary(produced=1, nothing_to_produce=0, failed=0),
        stored_count=1,
        reconcile=ReconcileCommandResult(
            mode=ReconcileMode.REPAIR,
            dry_run=False,
            participants=(
                ReconcileOutcome(
                    contract="NodeStore",
                    plugin="pgvector",
                    distribution="weft-store",
                    report=ReconcileReport(mode=ReconcileMode.REPAIR, examined=1, removed=1),
                ),
            ),
        ),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    stdout = rendered.stdout or ""
    assert "nodes now stored: 1." in stdout
    assert "mode 'repair' — 1 participant(s):" in stdout
    assert "pgvector (weft-store): examined 1, removed 1, backfilled 0" in stdout
    assert rendered.exit_code is ExitCode.SUCCESS


def test_index_reports_failure_when_its_own_automatic_reconcile_pass_fails() -> None:
    # Arrange — an index run that itself succeeded, but whose automatic convergence did not:
    # the failure must still surface, exactly as a standalone `weft reconcile` would report it.
    result = IndexCommandResult(
        summary=RunSummary(produced=1, nothing_to_produce=0, failed=0),
        stored_count=1,
        reconcile=ReconcileCommandResult(
            mode=ReconcileMode.REPAIR,
            dry_run=False,
            participants=(
                ReconcileOutcome(
                    contract="GraphStore",
                    plugin="graph",
                    distribution="weft-kg",
                    error="RuntimeError: connection refused",
                ),
            ),
        ),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.exit_code is ExitCode.OPERATION_FAILED
    assert "failed: graph (weft-kg) — RuntimeError: connection refused" in (rendered.stderr or "")


# --- the dispatch is registered, not written down here (task 6.20, G13) ------------------


class _StrangerResult(CommandResult):
    """A pack's own result type, of a kind `weft_cli.render` has never heard of."""

    headline: str


def _render_stranger(result: CommandResult) -> render.Rendered:
    typed = cast(_StrangerResult, result)
    return render.Rendered(
        stdout=f"graph: {typed.headline}", stderr=None, exit_code=ExitCode.SUCCESS
    )


def _offer(result_type: type[CommandResult], renderer: object, *, distribution: str) -> PackReport:
    """One pack's report carrying one renderer, built through the public seam rather than by
    constructing a `RendererOffer` by hand — `PackRegistrar` is what fills in attribution.
    """
    registrar = PackRegistrar(Registry(), distribution=distribution)
    registrar.add_renderer(result_type, cast(Callable[[object], object], renderer))
    return PackReport(
        pack=distribution.removeprefix("weft-"),
        distribution=distribution,
        status=PackStatus.ACTIVE,
        renderers=registrar.renderers,
    )


def test_a_packs_result_renders_for_a_person_once_its_renderer_is_registered() -> None:
    """The property task **6.20** makes true. Before it, `weft example-graph show` printed
    `{"nodes_with_graph_data":11,...}` at a person while eighteen built-in commands printed
    for one, because the dispatch was a table matched on the CLI's own result types.
    """
    # Arrange
    render.register_renderers_from_reports(
        [_offer(_StrangerResult, _render_stranger, distribution="weft-example-graph")]
    )

    # Act
    rendered = render.render_outcome(Produced(value=_StrangerResult(headline="11 nodes")))

    # Assert
    assert rendered.stdout == "graph: 11 nodes"


def test_a_result_with_no_registered_renderer_still_gets_the_honest_dump() -> None:
    """The floor stays the floor, and stops being the ceiling: an unrendered result is a
    truthful structured dump rather than a crash or a silent blank.
    """

    # Arrange
    class _UnrenderedResult(CommandResult):
        count: int

    # Act
    rendered = render.render_outcome(Produced(value=_UnrenderedResult(count=3)))

    # Assert
    assert rendered.stdout is not None
    assert json.loads(rendered.stdout) == {"count": 3}


def test_two_packs_claiming_one_result_type_is_refused_rather_than_shadowed() -> None:
    """Two renderers for one result type is a real collision, not a repeat of one fact —
    the identical rule `weft_store.rehydrate.register_from_reports` holds a namespace to.
    """

    # Arrange
    class _ContestedResult(CommandResult):
        value: str

    render.register_renderers_from_reports(
        [_offer(_ContestedResult, _render_stranger, distribution="weft-a")]
    )

    def _other(result: CommandResult) -> render.Rendered:
        del result
        return render.Rendered(stdout="other", stderr=None, exit_code=ExitCode.SUCCESS)

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError) as raised:
        render.register_renderers_from_reports(
            [_offer(_ContestedResult, _other, distribution="weft-b")]
        )

    # Assert
    assert "weft-a" in str(raised.value)
    assert "weft-b" in str(raised.value)


def test_registering_the_same_renderer_twice_is_a_repeat_not_a_collision() -> None:
    """Discovery runs more than once in one process across this tree's own suite, and a
    report re-read is the same fact stated again — the identical idempotence
    `weft_store.rehydrate.register_from_reports` already has.
    """

    # Arrange
    class _RepeatedResult(CommandResult):
        value: str

    def _render_repeated(result: CommandResult) -> render.Rendered:
        typed = cast(_RepeatedResult, result)
        return render.Rendered(
            stdout=f"repeated: {typed.value}", stderr=None, exit_code=ExitCode.SUCCESS
        )

    report = _offer(_RepeatedResult, _render_repeated, distribution="weft-a")

    # Act
    render.register_renderers_from_reports([report])
    render.register_renderers_from_reports([report])

    # Assert — the second registration neither refused nor replaced the first.
    assert render.render_outcome(Produced(value=_RepeatedResult(value="x"))).stdout == (
        "repeated: x"
    )


def test_every_built_in_renderer_arrives_through_the_public_registration_seam() -> None:
    """Requirement 4, checked rather than asserted: **no built-in keeps a private path.**
    `weft_cli.render` holds no first-party dispatch table — the eighteen built-in renderers
    reach the dispatch by `weft-cli`'s own `register()` calling `add_renderer`, the same call
    a stranger's pack makes, so the two cannot be told apart at the seam.
    """
    # Arrange
    registrar = PackRegistrar(Registry(), distribution="weft-cli")

    # Act
    commands.register(registrar, commands.Settings())

    # Assert — the built-ins are in the report, like anyone else's.
    offered = {offer.result_type for offer in registrar.renderers}
    assert IndexCommandResult in offered
    assert DeleteCommandResult in offered
    assert AskCommandResult in offered
    assert all(offer.distribution == "weft-cli" for offer in registrar.renderers)


def test_render_holds_no_first_party_dispatch_table_of_its_own() -> None:
    """The other half of the same property, read off the module rather than off the report: if
    a private table survived anywhere in `weft_cli.render`, a built-in would render without
    ever having registered, and the seam would be decorative.
    """

    def _result_types_in(value: object, *, depth: int = 0) -> bool:
        """Whether `value` holds a `CommandResult` subclass anywhere shallow inside it.

        Recursive on purpose, and that recursion is the whole check: the table this test
        exists to forbid was a tuple of `(result type, renderer)` **pairs**, so a one-level
        scan finds only 2-tuples and passes vacuously — `docs/lessons.md` L5.19's rule, met
        by planting the real shape rather than a convenient one.
        """
        if isinstance(value, type):
            return issubclass(value, CommandResult)
        if depth >= 3:
            return False
        if isinstance(value, dict):
            keys = cast("dict[object, object]", value).keys()
            return any(_result_types_in(key, depth=depth + 1) for key in keys)
        if isinstance(value, (tuple, list, set, frozenset)):
            items = cast("Collection[object]", value)
            return any(_result_types_in(item, depth=depth + 1) for item in items)
        return False

    # Act
    tables = [
        name
        for name, value in cast("dict[str, object]", vars(render)).items()
        if isinstance(value, (tuple, list, dict, set, frozenset))
        and _result_types_in(cast("object", value))
    ]

    # Assert
    assert tables == []


def _falsification_result(*, difference: float, verdict: object, low: float, high: float) -> object:
    """An `EvalCompareCommandResult` carrying one metric's own delta and its verdict."""
    from weft_cli.eval_commands import EvalCompareCommandResult, MetricComparison
    from weft_cli.pipeline_diff import PipelineDiff
    from weft_eval.aggregate import MetricAggregate
    from weft_eval.falsify import BaselineSpread, DifferenceJudgement, Verdict
    from weft_kernel.payload import Produced as KernelProduced

    assert isinstance(verdict, Verdict)
    base = 0.400

    def _aggregate(mean: float) -> KernelProduced[MetricAggregate]:
        return KernelProduced(
            value=MetricAggregate(
                reported_name="precision@5",
                mean=mean,
                n=4,
                stdev=0.0,
                excluded=0,
                nothing_to_produce=0,
            )
        )

    spread = BaselineSpread(metric="precision@5", means=(low, high), low=low, high=high)
    return EvalCompareCommandResult(
        run_a="run-a",
        run_b="run-b",
        corpus_matches=True,
        model_versions_match=True,
        active_distributions_match=True,
        pipeline_diff=PipelineDiff(
            a_name="vector-top-k",
            b_name="hybrid",
            identical=False,
            added_stages=(),
            removed_stages=(),
            changed_stages=(),
            var_changes=(),
            unapplied_operators_changed=False,
            unplaced_contributions_changed=False,
        ),
        metrics_comparison={
            "precision@5": MetricComparison(a=_aggregate(base), b=_aggregate(base + difference))
        },
        baseline_pipeline="vector-top-k",
        baseline_runs=("base-1", "base-2"),
        falsification={
            "precision@5": DifferenceJudgement(
                metric="precision@5",
                verdict=verdict,
                difference=difference,
                spread=spread,
                reason="reason text",
            )
        },
    )


def test_render_eval_compare_marks_a_delta_inside_the_baseline_spread() -> None:
    # Task 8.8 — the falsification instrument has to reach the terminal. A positive delta
    # printed with nothing qualifying it is exactly the claim `09` §4.2 warns about, so the
    # verdict is rendered beside the delta it judges, never in a block a reader could miss.
    from weft_eval.falsify import Verdict

    result = _falsification_result(
        difference=0.020, verdict=Verdict.WITHIN_BASELINE_SPREAD, low=0.400, high=0.460
    )

    rendered = render.render_outcome(Produced(value=cast("CommandResult", result)))

    assert rendered.stdout is not None
    assert "vector-top-k" in rendered.stdout
    assert "base-1" in rendered.stdout
    assert Verdict.WITHIN_BASELINE_SPREAD.value in rendered.stdout
    assert "0.400" in rendered.stdout
    assert "0.460" in rendered.stdout


def test_render_eval_compare_marks_a_delta_outside_the_baseline_spread() -> None:
    from weft_eval.falsify import Verdict

    result = _falsification_result(
        difference=0.200, verdict=Verdict.OUTSIDE_BASELINE_SPREAD, low=0.400, high=0.420
    )

    rendered = render.render_outcome(Produced(value=cast("CommandResult", result)))

    assert rendered.stdout is not None
    assert Verdict.OUTSIDE_BASELINE_SPREAD.value in rendered.stdout


def test_render_eval_compare_prints_no_delta_for_an_unjudgeable_metric() -> None:
    # Task 8.8 — the block must never invent the measurement it exists to withhold. An
    # UNJUDGEABLE verdict carries no difference and no spread, so its line is the reason,
    # and a `Δ+0.000` standing in for "there was nothing to judge" would be exactly the
    # plausible-number failure `09` §4.2 catalogues.
    from weft_cli.eval_commands import EvalCompareCommandResult
    from weft_cli.pipeline_diff import PipelineDiff
    from weft_eval.falsify import DifferenceJudgement, Verdict

    result = EvalCompareCommandResult(
        run_a="run-a",
        run_b="run-b",
        corpus_matches=True,
        model_versions_match=True,
        active_distributions_match=True,
        pipeline_diff=PipelineDiff(
            a_name="vector-top-k",
            b_name="hybrid",
            identical=False,
            added_stages=(),
            removed_stages=(),
            changed_stages=(),
            var_changes=(),
            unapplied_operators_changed=False,
            unplaced_contributions_changed=False,
        ),
        metrics_comparison={},
        baseline_pipeline="vector-top-k",
        baseline_runs=("base-1", "base-2"),
        falsification={
            "ndcg@10": DifferenceJudgement(
                metric="ndcg@10",
                verdict=Verdict.UNJUDGEABLE,
                difference=None,
                spread=None,
                reason="the baseline never measured 'ndcg@10'",
            )
        },
    )

    rendered = render.render_outcome(Produced(value=cast("CommandResult", result)))

    assert rendered.stdout is not None
    assert "the baseline never measured 'ndcg@10'" in rendered.stdout
    assert "Δ" not in rendered.stdout


def test_render_eval_compare_says_when_a_baseline_spread_is_zero_width() -> None:
    """Ledger **8.23**, `docs/lessons.md` L8.17.

    A zero-width interval and a badly-sampled one produce an identical record, and the
    mistake runs in the over-confident direction: every later difference falls outside it.
    Task 8.8's own demonstration hit this — the same corpus, document and deterministic
    embedder scored 0.833 in one session and 0.667 in another, while each session's
    repetitions agreed exactly. So a zero-width spread is printed as the claim it actually
    is (the repetitions did not vary) rather than as a number like any other.
    """
    from weft_cli.eval_commands import EvalCompareCommandResult
    from weft_cli.pipeline_diff import PipelineDiff
    from weft_eval.falsify import BaselineSpread, DifferenceJudgement, Verdict

    result = EvalCompareCommandResult(
        run_a="run-a",
        run_b="run-b",
        corpus_matches=True,
        model_versions_match=True,
        active_distributions_match=True,
        pipeline_diff=PipelineDiff(
            a_name="base",
            b_name="rung",
            identical=False,
            added_stages=(),
            removed_stages=(),
            changed_stages=(),
            var_changes=(),
            unapplied_operators_changed=False,
            unplaced_contributions_changed=False,
        ),
        metrics_comparison={},
        baseline_pipeline="base",
        baseline_runs=("b1", "b2"),
        falsification={
            "map": DifferenceJudgement(
                metric="map",
                verdict=Verdict.OUTSIDE_BASELINE_SPREAD,
                difference=0.11,
                spread=BaselineSpread(metric="map", means=(0.5, 0.5), low=0.5, high=0.5),
                reason="whatever",
            )
        },
    )

    rendered = render.render_outcome(Produced(value=cast("CommandResult", result)))

    assert rendered.stdout is not None
    # The words are not asserted, only that the zero-width case says *something* a reader
    # can act on beyond the bare bounds — an assertion on exact prose would be a test of
    # wording rather than of the claim.
    assert "zero-width" in rendered.stdout.lower()


def test_reconcile_prints_what_nobody_could_decide_beside_what_it_did() -> None:
    """Ledger **11.9** — an abstention reaches the operator or it did not happen.

    The failure this forbids is quiet and expensive: `full` spends a model call on a pair, the
    chain reaches its end with no opinion, and the line reads `backfilled 0` — indistinguishable
    from a corpus with nothing ambiguous in it. `converged` stays true, because running the pass
    again asks the same question of the same evidence, so the exit code is `SUCCESS` and the
    count is the only thing that says anything happened.
    """
    # Arrange
    result = ReconcileCommandResult(
        mode=ReconcileMode.FULL,
        dry_run=False,
        participants=(
            ReconcileOutcome(
                contract="NodeStore",
                plugin="pgvector-graph",
                distribution="weft-rag",
                report=ReconcileReport(
                    mode=ReconcileMode.FULL, examined=0, backfilled=3, abstained=2
                ),
            ),
        ),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS
    assert "abstained 2" in (rendered.stdout or "")


def test_reconcile_says_nothing_about_abstentions_when_there_were_none() -> None:
    """The clause is conditional, on `_reconcile_line`'s own precedent for `remaining`: a count
    printed as `abstained 0` on every `repair` line is noise that trains a reader to skip the
    line the one time it says something.
    """
    # Arrange
    result = ReconcileCommandResult(
        mode=ReconcileMode.REPAIR,
        dry_run=False,
        participants=(
            ReconcileOutcome(
                contract="NodeStore",
                plugin="pgvector-graph",
                distribution="weft-rag",
                report=ReconcileReport(mode=ReconcileMode.REPAIR, examined=1, backfilled=1),
            ),
        ),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert "abstained" not in (rendered.stdout or "")
