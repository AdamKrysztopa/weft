"""An experiment arm may be a router — task 44.5.

An arm names either the query pipeline it answers through or the router that chooses one per
question, never both. A router arm's record says which pipeline answered each question, so a routed
experiment can be read question by question against the fixed arms beside it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_cli.answer_envelope import RouteView as EnvelopeRouteView
from weft_eval.experiment import EXPERIMENT_SCHEMA_VERSION, ExperimentDocumentError, load_experiment
from weft_eval.run_record import (
    CorpusIdentity,
    build_run_record,
    load_run_record,
    write_run_record,
)
from weft_kernel.resolution import ResolvedPipeline
from weft_retrieve.payload import RouteView, RuleOutcome

REPO_ROOT = Path(__file__).resolve().parents[3]

_HEAD = (
    f'[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\nname = "routed"\n'
    'questions = "questions.toml"\ncorpus = "corpus"\nrepeats = 2\ntop_k = 5\n'
    'metrics = ["answer_correctness"]\nminimum_detectable_effect = 0.05\n\n'
    '[[arm]]\nname = "fixed"\npipeline = "index"\nquery_pipeline = "retrieve-then-generate"\n\n'
)


def _document(tmp_path: Path, second_arm: str) -> Path:
    path = tmp_path / "routed.toml"
    path.write_text(_HEAD + second_arm, encoding="utf-8")
    return path


def test_an_arm_may_name_a_router_instead_of_a_query_pipeline(tmp_path: Path) -> None:
    # Act
    experiment = load_experiment(
        _document(tmp_path, '[[arm]]\nname = "routed"\npipeline = "index"\nrouter = "route"\n')
    )

    # Assert
    routed = experiment.arms[1]
    assert routed.router == "route"
    assert routed.query_pipeline is None
    assert experiment.arms[0].router is None


def test_an_arm_naming_both_a_router_and_a_query_pipeline_is_refused(tmp_path: Path) -> None:
    # Arrange
    path = _document(
        tmp_path,
        '[[arm]]\nname = "both"\npipeline = "index"\nrouter = "route"\n'
        'query_pipeline = "retrieve-then-generate"\n',
    )

    # Act
    with pytest.raises(ExperimentDocumentError, match="router") as refused:
        load_experiment(path)

    # Assert
    assert "query_pipeline" in str(refused.value)
    assert "both" in str(refused.value)


def test_a_router_arm_s_routes_survive_a_write_and_a_read(tmp_path: Path) -> None:
    # Arrange
    route = RouteView(pipeline="retrieve-then-generate", outcome=RuleOutcome.MATCHED, rule="always")
    record = build_run_record(
        recorded_at="2026-09-28T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index"),
        corpus=CorpusIdentity(name="corpus", digest="c" * 64),
        question_routes={"q-1": route},
    )

    # Act
    write_run_record(record, tmp_path / "run.json")
    loaded = load_run_record(tmp_path / "run.json")

    # Assert
    assert loaded == record
    assert loaded.question_routes is not None
    assert loaded.question_routes["q-1"].outcome is RuleOutcome.MATCHED


def test_a_record_written_before_this_task_carries_no_routes() -> None:
    # Act
    record = load_run_record(
        REPO_ROOT
        / "eval"
        / "experiments"
        / "whole-corpus-en"
        / "runs"
        / "2f9667c5-1cfa-4b51-b67b-9e69a0bf2cfb.json"
    )

    # Assert
    assert record.question_routes is None


def test_the_answer_envelope_s_route_is_the_same_model() -> None:
    # Assert — `--json` and a run record must not describe one route with two shapes.
    assert EnvelopeRouteView is RouteView
