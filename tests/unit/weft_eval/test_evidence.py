"""`weft_eval.evidence` — ledger task **38.1**: an experiment's table, recomputed from its records.

The table is the claim an experiment makes, so it is never typed: each cell is derived from the
`RunRecord`s one complete invocation of the experiment wrote. Per arm against the first arm and per
metric it states two different things and says which is which — the **paired difference over
questions with its bootstrap interval**, which asks whether a difference generalises across the
questions, and the **verdict against the first arm's between-repetition spread**, which asks
whether it exceeds what the system does by repeating itself — beside latency and tokens per query.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_eval.aggregate import MetricAggregate
from weft_eval.evidence import (
    AmbiguousInvocationError,
    IncompleteExperimentError,
    evidence_table,
    regenerate,
    render_evidence_table,
)
from weft_eval.experiment import EXPERIMENT_SCHEMA_VERSION, Experiment, load_experiment
from weft_eval.falsify import Verdict
from weft_eval.run_record import (
    CorpusIdentity,
    ExperimentRun,
    PerQuestionScores,
    PerQuestionSeconds,
    QuestionKey,
    RoleTokens,
    RunRecord,
    build_run_record,
    write_run_record,
)
from weft_kernel.payload import Produced
from weft_kernel.resolution import ResolvedPipeline

_QUESTIONS = ("q-1", "q-2", "q-3", "q-4")


def fixture_experiment(directory: Path) -> Experiment:
    path = directory / "experiment.toml"
    path.write_text(
        f'[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\nname = "fixture"\n'
        'questions = "questions.toml"\ncorpus = "corpus"\nrepeats = 2\ntop_k = 5\n'
        'metrics = ["precision@5"]\nminimum_detectable_effect = 0.05\n\n'
        '[[arm]]\nname = "base"\npipeline = "index"\n\n'
        '[[arm]]\nname = "better"\npipeline = "index"\nquery_pipeline = "rung"\n',
        encoding="utf-8",
    )
    return load_experiment(path)


def _record(
    experiment: Experiment,
    *,
    arm: str,
    repetition: int,
    scores: tuple[float, ...],
    invocation: str = "inv-1",
    digest: str | None = None,
) -> RunRecord:
    mean = sum(scores) / len(scores)
    return build_run_record(
        recorded_at="2026-09-16T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index"),
        corpus=CorpusIdentity(name="corpus", digest="c" * 64),
        metrics={
            "precision@5": Produced(
                value=MetricAggregate(
                    reported_name="precision@5",
                    mean=mean,
                    n=len(scores),
                    stdev=0.1,
                    excluded=0,
                    nothing_to_produce=0,
                )
            )
        },
        question_set_digest="d" * 64,
        question_scores={
            "precision@5": PerQuestionScores(
                keyed_by=QuestionKey.QUESTION_ID,
                scores={q: Produced(value=s) for q, s in zip(_QUESTIONS, scores, strict=True)},
            )
        },
        question_seconds=PerQuestionSeconds(
            keyed_by=QuestionKey.QUESTION_ID,
            seconds={q: 0.1 * (index + 1) for index, q in enumerate(_QUESTIONS)},
        ),
        token_usage={
            "generate": RoleTokens(
                prompt_tokens=400, completion_tokens=40, calls=4, calls_not_reporting=0
            )
        },
        experiment=ExperimentRun(
            name=experiment.name,
            digest=digest if digest is not None else experiment.digest,
            invocation=invocation,
            arm=arm,
            repetition=repetition,
        ),
    )


def complete_records(experiment: Experiment, invocation: str = "inv-1") -> list[RunRecord]:
    return [
        _record(
            experiment, arm="base", repetition=1, scores=(0.5, 0.5, 0.5, 0.5), invocation=invocation
        ),
        _record(
            experiment,
            arm="base",
            repetition=2,
            scores=(0.5, 0.5, 0.5, 0.58),
            invocation=invocation,
        ),
        _record(
            experiment,
            arm="better",
            repetition=1,
            scores=(0.75, 0.75, 0.75, 0.75),
            invocation=invocation,
        ),
        _record(
            experiment,
            arm="better",
            repetition=2,
            scores=(0.75, 0.75, 0.75, 0.75),
            invocation=invocation,
        ),
    ]


def test_each_arm_is_compared_with_the_first_by_a_paired_interval_and_a_spread_verdict(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment = fixture_experiment(tmp_path)

    # Act
    table = evidence_table(experiment, complete_records(experiment))

    # Assert
    assert table.baseline_arm == "base"
    assert table.digest == experiment.digest
    assert table.invocation == "inv-1"
    (comparison,) = table.comparisons
    assert (comparison.arm, comparison.metric) == ("better", "precision@5")
    assert comparison.paired is not None
    assert comparison.paired.mean == pytest.approx(0.25)
    assert comparison.paired.n == 4
    assert comparison.judgement.verdict is Verdict.OUTSIDE_BASELINE_SPREAD


def test_each_arm_states_its_latency_and_tokens_per_query_by_role(tmp_path: Path) -> None:
    # Arrange
    experiment = fixture_experiment(tmp_path)

    # Act
    table = evidence_table(experiment, complete_records(experiment))

    # Assert
    costs = {cost.arm: cost for cost in table.costs}
    assert set(costs) == {"base", "better"}
    better = costs["better"]
    assert better.latency.samples == 8
    assert isinstance(better.latency.p50, Produced)
    assert better.latency.p50.value == pytest.approx(0.2)
    assert better.tokens_per_query["generate"] == pytest.approx(110.0)


def test_an_invocation_missing_a_repetition_is_refused_naming_what_is_missing(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment = fixture_experiment(tmp_path)
    records = complete_records(experiment)[:-1]

    # Act
    with pytest.raises(IncompleteExperimentError) as caught:
        evidence_table(experiment, records)

    # Assert
    assert "better" in str(caught.value)
    assert "2" in str(caught.value)


def test_two_complete_invocations_are_refused_unless_one_is_named(tmp_path: Path) -> None:
    # Arrange
    experiment = fixture_experiment(tmp_path)
    records = complete_records(experiment, "inv-1") + complete_records(experiment, "inv-2")

    # Act
    with pytest.raises(AmbiguousInvocationError) as caught:
        evidence_table(experiment, records)
    named = evidence_table(experiment, records, invocation="inv-2")

    # Assert
    assert "inv-1" in str(caught.value) and "inv-2" in str(caught.value)
    assert named.invocation == "inv-2"


def test_records_of_another_version_of_the_document_are_not_this_experiments(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment = fixture_experiment(tmp_path)
    stale = [
        record.model_copy(
            update={
                "experiment": record.experiment.model_copy(update={"digest": "0" * 64})
                if record.experiment
                else None
            }
        )
        for record in complete_records(experiment, "inv-old")
    ]

    # Act
    table = evidence_table(experiment, stale + complete_records(experiment))

    # Assert
    assert table.invocation == "inv-1"


def test_the_rendered_table_says_which_interval_is_which_and_carries_every_cell(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment = fixture_experiment(tmp_path)
    table = evidence_table(experiment, complete_records(experiment))

    # Act
    markdown = render_evidence_table(table)

    # Assert
    assert experiment.digest[:12] in markdown
    assert "minimum detectable effect: 0.05" in markdown
    assert "bootstrap interval over questions" in markdown
    assert "between-repetition spread of arm 'base'" in markdown
    row = next(line for line in markdown.splitlines() if "| better | precision@5 |" in line)
    assert "+0.250" in row
    assert Verdict.OUTSIDE_BASELINE_SPREAD.value in row
    assert render_evidence_table(table) == markdown


def test_regenerate_reads_the_records_on_disk_for_the_document_on_disk(tmp_path: Path) -> None:
    # Arrange
    experiment = fixture_experiment(tmp_path)
    runs = tmp_path / "runs"
    for index, record in enumerate(complete_records(experiment)):
        write_run_record(record, runs / f"run-{index}.json")

    # Act
    markdown = regenerate(tmp_path / "experiment.toml", runs)

    # Assert
    assert markdown == render_evidence_table(
        evidence_table(experiment, complete_records(experiment))
    )
