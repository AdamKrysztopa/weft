"""Two arms' recorded answers judged head to head — task **44.43b**.

`compare_arms` reads the answers an experiment already recorded (`RunRecord.question_answers`,
44.43a), so judging never regenerates an answer. It takes repetition 1 of each arm from one
complete invocation, judges every question both arms answered on each criterion asked for (each
pair in both orders, `judge_pair`), and summarises the arm's win rate over the baseline per
criterion. A judgement that failed is reported as failed, never as a tie.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.unit.weft_eval.replay_records import experiment_of, record_of
from weft_eval.experiment import Experiment
from weft_eval.falsify import UnpairableRecordsError
from weft_eval.pairwise import (
    COMPREHENSIVENESS,
    DIRECTNESS,
    DIVERSITY,
    EMPOWERMENT,
    Criterion,
    InvalidCriteriaError,
    PairwiseChoice,
    PairwiseRecord,
    Position,
    UnknownArmError,
    UnrecordedAnswersError,
    compare_arms,
    load_pairwise_record,
    render_pairwise_table,
    write_pairwise_record,
)
from weft_eval.run_record import RunRecord
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered

_QUESTIONS = {
    "q1": "What themes recur across the collection?",
    "q2": "Which papers disagree about redundancy?",
    "q3": "UNREADABLE which methods scale?",
}


class _JudgeLLM:
    """Prefers whichever shown answer contains `marker`; unreadable on an UNREADABLE question."""

    def __init__(self, marker: str = "BETTER") -> None:
        self._marker = marker
        self.sent: list[Rendered] = []

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> object:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(
        self, rendered: Rendered, *, role: str, ctx: Context
    ) -> Produced[Completion]:
        del role, ctx
        self.sent.append(rendered)
        text = "\n".join(message.content for message in rendered.conversation.messages)
        if "UNREADABLE" in text:
            return Produced(value=Completion(text="no json here", model="scripted"))
        better = text.find(f"{self._marker}-")
        other = text.find("PLAIN-")
        winner = Position.FIRST if better < other else Position.SECOND
        reply = PairwiseChoice(winner=winner, reasoning="scripted").model_dump_json()
        return Produced(value=Completion(text=reply, model="scripted"))

    async def close(self) -> None: ...


def _ctx(llm: _JudgeLLM) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _records(
    tmp_path: Path,
    *,
    baseline_answers: Mapping[str, str] | None,
    arm_answers: Mapping[str, str] | None,
) -> tuple[Experiment, list[RunRecord]]:
    experiment = experiment_of(tmp_path, ("dense", "wide"))
    scores = dict.fromkeys(_QUESTIONS, 0.5)
    records = [
        record_of(experiment, "dense", scores, answers=baseline_answers),
        record_of(experiment, "dense", scores, repetition=2, answers=baseline_answers),
        record_of(experiment, "wide", scores, answers=arm_answers),
        record_of(experiment, "wide", scores, repetition=2, answers=arm_answers),
    ]
    return experiment, records


_BASELINE = {"q1": "PLAIN-dense-1", "q2": "PLAIN-dense-2"}
_ARM = {"q1": "BETTER-wide-1", "q2": "BETTER-wide-2"}


async def test_an_arm_that_is_always_preferred_wins_every_question_on_every_criterion(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment, records = _records(tmp_path, baseline_answers=_BASELINE, arm_answers=_ARM)
    llm = _JudgeLLM()
    criteria = (COMPREHENSIVENESS, DIRECTNESS)

    # Act
    record = await compare_arms(
        experiment,
        records,
        questions=_QUESTIONS,
        baseline="dense",
        arm="wide",
        criteria=criteria,
        ctx=_ctx(llm),
    )

    # Assert
    assert (record.baseline, record.arm, record.invocation) == ("dense", "wide", "inv-1")
    assert [summary.criterion for summary in record.summaries] == [c.name for c in criteria]
    assert record.criteria == criteria
    for summary in record.summaries:
        assert (summary.n, summary.wins_b, summary.wins_a, summary.ties) == (2, 2, 0, 0)
        assert summary.win_rate_b == pytest.approx(1.0)
    assert len(llm.sent) == 2 * 2 * 2
    assert record.failures == ()


async def test_a_question_only_one_arm_answered_is_listed_and_not_judged(
    tmp_path: Path,
) -> None:
    # Arrange — `wide` failed q2, so it has no answer to compare.
    experiment, records = _records(
        tmp_path, baseline_answers=_BASELINE, arm_answers={"q1": "BETTER-wide-1"}
    )
    llm = _JudgeLLM()

    # Act
    record = await compare_arms(
        experiment,
        records,
        questions=_QUESTIONS,
        baseline="dense",
        arm="wide",
        criteria=(DIVERSITY,),
        ctx=_ctx(llm),
    )

    # Assert
    assert record.unpaired == ("q2",)
    assert {verdict.question_id for verdict in record.verdicts} == {"q1"}
    assert record.summaries[0].n == 1


async def test_a_limit_judges_only_the_first_paired_questions(tmp_path: Path) -> None:
    # Arrange
    experiment, records = _records(tmp_path, baseline_answers=_BASELINE, arm_answers=_ARM)
    llm = _JudgeLLM()

    # Act
    record = await compare_arms(
        experiment,
        records,
        questions=_QUESTIONS,
        baseline="dense",
        arm="wide",
        criteria=(EMPOWERMENT,),
        ctx=_ctx(llm),
        limit=1,
    )

    # Assert
    assert [verdict.question_id for verdict in record.verdicts] == ["q1"]
    assert len(llm.sent) == 2


async def test_a_judgement_that_fails_is_a_failure_not_a_tie(tmp_path: Path) -> None:
    # Arrange
    experiment, records = _records(
        tmp_path,
        baseline_answers={**_BASELINE, "q3": "PLAIN-dense-3"},
        arm_answers={**_ARM, "q3": "BETTER-wide-3"},
    )
    llm = _JudgeLLM()

    # Act
    record = await compare_arms(
        experiment,
        records,
        questions=_QUESTIONS,
        baseline="dense",
        arm="wide",
        criteria=(COMPREHENSIVENESS,),
        ctx=_ctx(llm),
    )

    # Assert
    assert [(failure.question_id, failure.criterion) for failure in record.failures] == [
        ("q3", COMPREHENSIVENESS.name)
    ]
    assert "q3" not in {verdict.question_id for verdict in record.verdicts}
    assert record.summaries[0].n == 2
    assert record.summaries[0].ties == 0


async def test_an_arm_the_document_does_not_declare_is_refused_before_any_model_call(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment, records = _records(tmp_path, baseline_answers=_BASELINE, arm_answers=_ARM)
    llm = _JudgeLLM()

    # Act / Assert
    with pytest.raises(UnknownArmError, match="widest") as refused:
        await compare_arms(
            experiment,
            records,
            questions=_QUESTIONS,
            baseline="dense",
            arm="widest",
            criteria=(DIVERSITY,),
            ctx=_ctx(llm),
        )
    assert set(refused.value.valid_options) == {"dense", "wide"}
    assert llm.sent == []


async def test_a_record_that_kept_no_answers_is_refused_naming_the_arm(tmp_path: Path) -> None:
    # Arrange — records written before 44.43a carry no answer text.
    experiment, records = _records(tmp_path, baseline_answers=_BASELINE, arm_answers=None)
    llm = _JudgeLLM()

    # Act / Assert
    with pytest.raises(UnrecordedAnswersError, match="wide"):
        await compare_arms(
            experiment,
            records,
            questions=_QUESTIONS,
            baseline="dense",
            arm="wide",
            criteria=(DIVERSITY,),
            ctx=_ctx(llm),
        )
    assert llm.sent == []


async def test_arms_over_different_questions_are_refused(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("dense", "wide"))
    scores = dict.fromkeys(_QUESTIONS, 0.5)
    records = [
        record_of(experiment, "dense", scores, answers=_BASELINE),
        record_of(experiment, "dense", scores, repetition=2, answers=_BASELINE),
        record_of(experiment, "wide", scores, answers=_ARM, question_set_digest="e" * 64),
        record_of(
            experiment, "wide", scores, repetition=2, answers=_ARM, question_set_digest="e" * 64
        ),
    ]

    # Act / Assert
    with pytest.raises(UnpairableRecordsError):
        await compare_arms(
            experiment,
            records,
            questions=_QUESTIONS,
            baseline="dense",
            arm="wide",
            criteria=(DIVERSITY,),
            ctx=_ctx(_JudgeLLM()),
        )


async def test_a_pairwise_record_round_trips_and_renders_each_criterion(tmp_path: Path) -> None:
    # Arrange
    experiment, records = _records(tmp_path, baseline_answers=_BASELINE, arm_answers=_ARM)
    record = await compare_arms(
        experiment,
        records,
        questions=_QUESTIONS,
        baseline="dense",
        arm="wide",
        criteria=(COMPREHENSIVENESS, DIVERSITY),
        ctx=_ctx(_JudgeLLM()),
    )
    path = tmp_path / "out" / "dense-vs-wide.json"

    # Act
    write_pairwise_record(record, path)
    loaded = load_pairwise_record(path)
    table = render_pairwise_table(loaded)

    # Assert
    assert isinstance(loaded, PairwiseRecord)
    assert loaded == record
    assert "comprehensiveness" in table
    assert "diversity" in table
    assert "wide" in table
    assert "dense" in table


async def test_a_criterion_whose_every_judgement_failed_reports_no_win_rate(
    tmp_path: Path,
) -> None:
    # Arrange — R44.6: the one paired question is unreadable to the judge.
    experiment, records = _records(
        tmp_path,
        baseline_answers={"q3": "PLAIN-dense-3"},
        arm_answers={"q3": "BETTER-wide-3"},
    )

    # Act
    record = await compare_arms(
        experiment,
        records,
        questions=_QUESTIONS,
        baseline="dense",
        arm="wide",
        criteria=(DIVERSITY,),
        ctx=_ctx(_JudgeLLM()),
    )

    # Assert
    [summary] = record.summaries
    assert summary.criterion == DIVERSITY.name
    assert summary.n == 0
    assert summary.win_rate_b is None
    assert "diversity" in render_pairwise_table(record)


async def test_a_criterion_named_twice_is_refused_before_any_model_call(tmp_path: Path) -> None:
    # Arrange
    experiment, records = _records(tmp_path, baseline_answers=_BASELINE, arm_answers=_ARM)
    llm = _JudgeLLM()

    # Act
    with pytest.raises(InvalidCriteriaError, match="'diversity' is named more than once"):
        await compare_arms(
            experiment,
            records,
            questions=_QUESTIONS,
            baseline="dense",
            arm="wide",
            criteria=(DIVERSITY, DIVERSITY),
            ctx=_ctx(llm),
        )

    # Assert
    assert llm.sent == []


async def test_a_pack_criterion_is_summarised_under_its_own_name_and_kept_in_the_record(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment, records = _records(tmp_path, baseline_answers=_BASELINE, arm_answers=_ARM)
    grounded = Criterion(name="groundedness", definition="supported by what was retrieved")

    # Act
    record = await compare_arms(
        experiment,
        records,
        questions=_QUESTIONS,
        baseline="dense",
        arm="wide",
        criteria=(grounded, DIVERSITY),
        ctx=_ctx(_JudgeLLM()),
    )
    path = tmp_path / "pairwise.json"
    write_pairwise_record(record, path)

    # Assert
    assert [summary.criterion for summary in record.summaries] == ["groundedness", "diversity"]
    assert load_pairwise_record(path).criteria == (grounded, DIVERSITY)


def test_a_record_written_before_criteria_were_data_still_loads(tmp_path: Path) -> None:
    # Arrange — the shape `weft eval pairwise` wrote before `criteria` existed.
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps(
            {
                "experiment": "e",
                "invocation": "inv-1",
                "baseline": "dense",
                "arm": "wide",
                "prompt_version": "1",
                "summaries": [
                    {
                        "criterion": "comprehensiveness",
                        "n": 1,
                        "wins_a": 0,
                        "wins_b": 1,
                        "ties": 0,
                        "win_rate_b": 1.0,
                        "low": None,
                        "high": None,
                    }
                ],
                "verdicts": [
                    {
                        "question_id": "q1",
                        "criterion": "comprehensiveness",
                        "first": "b",
                        "swapped": "b",
                        "outcome": "b",
                    }
                ],
                "failures": [],
                "unpaired": [],
            }
        ),
        encoding="utf-8",
    )

    # Act
    record = load_pairwise_record(path)

    # Assert
    assert record.criteria == ()
    assert record.summaries[0].criterion == "comprehensiveness"


def test_every_committed_pairwise_record_still_loads() -> None:
    # Arrange
    repository = Path(__file__).resolve().parents[3]
    committed = sorted((repository / "eval" / "experiments").glob("*/pairwise/*-vs-*.json"))

    # Act / Assert
    assert committed, "no committed pairwise record found — the control must hit"
    for path in committed:
        assert load_pairwise_record(path).summaries
