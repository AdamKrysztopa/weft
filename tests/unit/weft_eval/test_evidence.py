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


# --- Repair R38.3 — tokens per query are never a zero standing where the count is unknown.


def test_tokens_per_query_count_the_questions_a_record_timed_when_no_metric_scored_them(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment = fixture_experiment(tmp_path)
    records = [
        record.model_copy(update={"question_scores": None})
        for record in complete_records(experiment)
    ]

    # Act
    table = evidence_table(experiment, records)

    # Assert
    costs = {cost.arm: cost for cost in table.costs}
    assert costs["better"].tokens_per_query["generate"] == pytest.approx(110.0)


def test_tokens_per_query_are_absent_rather_than_zero_when_no_question_is_known(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment = fixture_experiment(tmp_path)
    records = [
        record.model_copy(update={"question_scores": None, "question_seconds": None})
        for record in complete_records(experiment)
    ]

    # Act
    table = evidence_table(experiment, records)
    markdown = render_evidence_table(table)

    # Assert
    assert all(cost.tokens_per_query == {} for cost in table.costs)
    assert "generate: 0.0" not in markdown


def test_a_verdict_against_a_zero_width_spread_says_so_and_the_effect_size_decides_nothing(
    tmp_path: Path,
) -> None:
    """Repair R38.10.

    Retrieval with no model call repeats itself exactly, so `38.5`'s dense arm recorded a zero-width
    spread and hybrid's recall@5 Δ of -0.003, a tenth of the document's minimum detectable effect,
    printed a bare `outside-baseline-spread`. `09` §4.3 keeps the strict reading; `weft eval compare
    --baseline` already prints the caveat beside it, and the table did not.
    """
    # Arrange — the base arm's two repetitions agree exactly.
    experiment = fixture_experiment(tmp_path)
    records = [
        _record(experiment, arm="base", repetition=1, scores=(0.5, 0.5, 0.5, 0.5)),
        _record(experiment, arm="base", repetition=2, scores=(0.5, 0.5, 0.5, 0.5)),
        _record(experiment, arm="better", repetition=1, scores=(0.5, 0.5, 0.5, 0.51)),
        _record(experiment, arm="better", repetition=2, scores=(0.5, 0.5, 0.5, 0.51)),
    ]

    # Act
    markdown = render_evidence_table(evidence_table(experiment, records))

    # Assert
    row = next(line for line in markdown.splitlines() if "| better | precision@5 |" in line)
    assert f"{Verdict.OUTSIDE_BASELINE_SPREAD.value} (zero-width)" in row
    header = markdown.split("| arm |", 1)[0]
    assert "zero-width" in header
    assert "not proof the system is deterministic" in header
    assert "minimum detectable effect is not applied" in header


def test_each_arms_mean_states_the_questions_it_is_over_and_how_many_were_excluded(
    tmp_path: Path,
) -> None:
    """Repair R38.12.

    A rung that fails on a question now excludes it rather than aborting the run, so two arms' means
    can be over different questions; the paired Δ stays comparable because it pairs only questions
    both arms scored, and the table's only `n` was that one.
    """
    # Arrange — the better arm's first repetition could not answer one question.
    experiment = fixture_experiment(tmp_path)
    records = complete_records(experiment)
    first = records[2]
    aggregate = first.metrics["precision@5"]
    assert isinstance(aggregate, Produced)
    records[2] = first.model_copy(
        update={
            "metrics": {
                "precision@5": Produced(
                    value=aggregate.value.model_copy(update={"n": 3, "excluded": 1})
                )
            }
        }
    )

    # Act
    markdown = render_evidence_table(evidence_table(experiment, records))

    # Assert
    row = next(line for line in markdown.splitlines() if "| better | precision@5 |" in line)
    assert "0.500 (n 4) |" in row
    assert "0.750 (n 3, 1 excluded) |" in row


# --- Task 38.13 — a baseline run once still yields a table.


def test_a_baseline_run_once_is_complete_paired_and_its_spread_verdict_unjudgeable(
    tmp_path: Path,
) -> None:
    """The paired interval over questions is the evidence for a deterministic baseline; a spread
    needs at least two repetitions, and `falsify`'s own rule for one repetition is `UNJUDGEABLE`.
    """
    # Arrange
    path = tmp_path / "experiment.toml"
    path.write_text(
        f'[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\nname = "fixture"\n'
        'questions = "questions.toml"\ncorpus = "corpus"\nrepeats = 2\ntop_k = 5\n'
        'metrics = ["precision@5"]\nminimum_detectable_effect = 0.05\n\n'
        '[[arm]]\nname = "base"\npipeline = "index"\nrepeats = 1\n\n'
        '[[arm]]\nname = "better"\npipeline = "index"\nquery_pipeline = "rung"\n',
        encoding="utf-8",
    )
    experiment = load_experiment(path)
    records = [record for record in complete_records(experiment) if not _is_base_second(record)]

    # Act
    table = evidence_table(experiment, records)

    # Assert
    (comparison,) = table.comparisons
    assert comparison.paired is not None
    assert comparison.paired.mean == pytest.approx(0.25)
    assert comparison.judgement.verdict is Verdict.UNJUDGEABLE


def _is_base_second(record: RunRecord) -> bool:
    return record.experiment is not None and (
        record.experiment.arm,
        record.experiment.repetition,
    ) == ("base", 2)


# --- Repair R38.16 — a table states the population its statistics are over.


def test_a_paired_difference_counts_the_questions_that_actually_differ(tmp_path: Path) -> None:
    """An interval resting on one question of four says so: most per-question differences are
    exactly zero, and the mean and its interval are carried by the few that are not.
    """
    # Arrange
    experiment = fixture_experiment(tmp_path)
    records = [
        _record(experiment, arm="base", repetition=1, scores=(0.5, 0.5, 0.5, 0.5)),
        _record(experiment, arm="base", repetition=2, scores=(0.5, 0.5, 0.5, 0.5)),
        _record(experiment, arm="better", repetition=1, scores=(0.5, 0.75, 0.5, 0.5)),
        _record(experiment, arm="better", repetition=2, scores=(0.5, 0.75, 0.5, 0.5)),
    ]

    # Act
    table = evidence_table(experiment, records)
    markdown = render_evidence_table(table)

    # Assert
    comparison = next(c for c in table.comparisons if c.arm == "better")
    assert comparison.paired is not None
    assert comparison.paired.n == 4
    assert comparison.paired.differing == 1
    row = next(line for line in markdown.splitlines() if "| better | precision@5 |" in line)
    assert "| 4, 1 differing |" in row


def test_the_table_names_the_corpus_its_records_were_measured_on(tmp_path: Path) -> None:
    """A table copied out of its directory still says which corpus it measured — the name and
    digest every record already carries, never the experiment document's header comment.
    """
    # Arrange
    experiment = fixture_experiment(tmp_path)

    # Act
    table = evidence_table(experiment, complete_records(experiment))
    markdown = render_evidence_table(table)

    # Assert
    assert table.corpus_name == "corpus"
    assert table.corpus_digest == "c" * 64
    assert "corpus: corpus (cccccccccccc…)" in markdown.splitlines()[2:6]
