"""Experiments and run records for the replay tests — task 44.6a.

The experiment goes through `load_experiment` and each record through `build_run_record`, the two
constructors a real `weft eval experiment` run uses, so a replay test pairs what a real invocation
writes. A score of `None` is a question the metric was asked and did not score (`NotScored`); a
question absent from the mapping was never asked.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from weft_eval.aggregate import MetricAggregate
from weft_eval.experiment import EXPERIMENT_SCHEMA_VERSION, Experiment, load_experiment
from weft_eval.run_record import (
    CorpusIdentity,
    ExperimentRun,
    NotScored,
    PerQuestionScores,
    QuestionKey,
    QuestionOutcome,
    RunRecord,
    build_run_record,
)
from weft_kernel.payload import Produced
from weft_kernel.resolution import ResolvedPipeline

METRIC = "answer_correctness"


def experiment_of(
    directory: Path,
    arms: Sequence[str],
    *,
    name: str = "replay-fixture",
    direction: str | None = None,
) -> Experiment:
    arm_tables = "".join(
        f'\n[[arm]]\nname = "{arm}"\npipeline = "index"\nquery_pipeline = "rung-{arm}"\n'
        for arm in arms
    )
    path = directory / f"{name}.toml"
    path.write_text(
        f'[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\nname = "{name}"\n'
        'questions = "questions.toml"\ncorpus = "corpus"\nrepeats = 2\ntop_k = 5\n'
        f'metrics = ["{METRIC}"]\nminimum_detectable_effect = 0.05\n'
        + (
            f'\n[decision]\nmetric = "{METRIC}"\nmargin = 0.05\ndirection = "{direction}"\n'
            if direction is not None
            else ""
        )
        + arm_tables,
        encoding="utf-8",
    )
    return load_experiment(path)


def _outcome(score: float | None) -> QuestionOutcome:
    if score is None:
        return NotScored(reason="the judge returned no verdict")
    return Produced(value=score)


def record_of(
    experiment: Experiment,
    arm: str,
    scores: Mapping[str, float | None],
    *,
    repetition: int = 1,
    invocation: str = "inv-1",
    question_set_digest: str = "d" * 64,
    corpus_digest: str = "c" * 64,
    answers: Mapping[str, str] | None = None,
    judge_prompts: Mapping[str, str] | None = None,
) -> RunRecord:
    produced = [score for score in scores.values() if score is not None]
    metrics = (
        {
            METRIC: Produced(
                value=MetricAggregate(
                    reported_name=METRIC,
                    mean=sum(produced) / len(produced),
                    n=len(produced),
                    stdev=0.0,
                    excluded=len(scores) - len(produced),
                    nothing_to_produce=0,
                )
            )
        }
        if produced
        else {}
    )
    return build_run_record(
        recorded_at="2026-09-28T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index"),
        corpus=CorpusIdentity(name="corpus", digest=corpus_digest),
        metrics=metrics,
        question_set_digest=question_set_digest,
        question_scores={
            METRIC: PerQuestionScores(
                keyed_by=QuestionKey.QUESTION_ID,
                scores={key: _outcome(score) for key, score in scores.items()},
            )
        },
        experiment=ExperimentRun(
            name=experiment.name,
            digest=experiment.digest,
            invocation=invocation,
            arm=arm,
            repetition=repetition,
        ),
        question_answers=answers,
        judge_prompts=judge_prompts,
    )


def records_of(
    experiment: Experiment,
    first: Mapping[str, Mapping[str, float | None]],
    *,
    second: Mapping[str, Mapping[str, float | None]] | None = None,
    invocation: str = "inv-1",
) -> list[RunRecord]:
    """Both repetitions of every arm; repetition 2 repeats repetition 1 unless `second` names it."""
    records: list[RunRecord] = []
    for arm, scores in first.items():
        again = (second or {}).get(arm, scores)
        records.append(record_of(experiment, arm, scores, invocation=invocation))
        records.append(record_of(experiment, arm, again, repetition=2, invocation=invocation))
    return records
