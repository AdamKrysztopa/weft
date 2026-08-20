"""Unit tests for `weft_cli.render`.

Mirrors `packages/weft-cli/src/weft_cli/render.py`. Covers the property task 3.2 promises: the
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

from weft_cli import render
from weft_cli.commands import (
    AskCommandResult,
    CommandRefusalError,
    IndexCommandResult,
    PluginsDoctorCommandResult,
    PluginsListCommandResult,
)
from weft_cli.exit_codes import ExitCode
from weft_cli.output import AskFormat
from weft_command.contract import CommandResult
from weft_generate.payload import Answer, AnswerStance, Citation
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, NothingToProduce, Produced
from weft_kernel.registry import DisplacedRegistration
from weft_kernel.runner import RunSummary
from weft_retrieve.payload import Query


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
        citations=(Citation(marker="1", node_id=node.id, uri="doc://a"),),
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
    assert rendered.stdout == "routed to: specific\nthe answer\n  [1] doc://a"


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
    assert rendered.stdout == "routed to: specific\n  [1] doc://a"
    assert "the answer" not in rendered.stdout


def test_render_plugins_list_delegates_to_the_shared_renderer() -> None:
    # Arrange
    reports = (PackReport(distribution="weft-chunk", status=PackStatus.ACTIVE),)
    result = PluginsListCommandResult(reports=reports)

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    assert rendered.stdout == "weft-chunk: active (0 contributed)"


def test_render_plugins_doctor_delegates_to_the_shared_renderer_including_displaced() -> None:
    # Arrange
    class _Chunker:
        pass

    reports = (PackReport(distribution="weft-loser", status=PackStatus.ACTIVE, contributed=1),)
    displaced = (
        DisplacedRegistration(
            contract=_Chunker,
            name="shared",
            distribution="weft-loser",
            winner="weft-winner",
            pin="_Chunker:shared",
        ),
    )
    result = PluginsDoctorCommandResult(reports=reports, displaced=displaced, unconsulted_pins=())

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
