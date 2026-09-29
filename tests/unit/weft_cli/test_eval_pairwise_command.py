"""`weft eval pairwise <experiment> --baseline A --arm B` — task **44.43b**.

The verb over `weft_eval.pairwise.compare_arms`: it reads the experiment document, the question
text from the document's own question set and the records beside the document, judges through the
command path's `LLM`, writes a pairwise record under `<experiment>/pairwise/`, and prints the table.
It calls a model and writes a file, so its permission class is `write`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.unit.weft_eval.replay_records import experiment_of, record_of
from weft_cli.eval_pairwise import EvalPairwiseArgs, EvalPairwiseCommand
from weft_cli.exit_codes import ExitCode, exit_code_for
from weft_cli.render import render_outcome
from weft_command.permission import PermissionClass
from weft_eval.pairwise import (
    PairwiseChoice,
    PairwiseCriterion,
    Position,
    UnknownArmError,
    load_pairwise_record,
)
from weft_eval.run_record import write_run_record
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered

_QUESTION_SET = """\
[question_set]
schema = 2
absent = ["kind", "difficulty", "quote", "reference_answer", "notes"]
absent_reason = "a pairwise fixture: corpus-wide questions have no single gold"
axes = []

[[question]]
id = "q1"
text = "What themes recur across the collection?"
language = "en"
relevant_documents = ["doc.txt"]

[[question]]
id = "q2"
text = "Which papers disagree about redundancy?"
language = "en"
relevant_documents = ["doc.txt"]
"""


class _JudgeLLM:
    """Prefers whichever shown answer starts with BETTER-, whatever order it is shown in."""

    def __init__(self) -> None:
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
        winner = Position.FIRST if text.find("BETTER-") < text.find("PLAIN-") else Position.SECOND
        reply = PairwiseChoice(winner=winner, reasoning="scripted").model_dump_json()
        return Produced(value=Completion(text=reply, model="scripted"))

    async def close(self) -> None: ...


def _ctx(llm: _JudgeLLM) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _document(tmp_path: Path) -> Path:
    (tmp_path / "questions.toml").write_text(_QUESTION_SET, encoding="utf-8")
    experiment = experiment_of(tmp_path, ("dense", "wide"))
    scores = {"q1": 0.5, "q2": 0.5}
    answers = {
        "dense": {"q1": "PLAIN-dense-1", "q2": "PLAIN-dense-2"},
        "wide": {"q1": "BETTER-wide-1", "q2": "BETTER-wide-2"},
    }
    runs = tmp_path / "replay-fixture" / "runs"
    for arm, arm_answers in answers.items():
        for repetition in (1, 2):
            record = record_of(experiment, arm, scores, repetition=repetition, answers=arm_answers)
            write_run_record(record, runs / f"{arm}-{repetition}.json")
    return tmp_path / "replay-fixture.toml"


async def test_the_command_judges_writes_a_record_beside_the_document_and_prints_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    document = _document(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    llm = _JudgeLLM()

    # Act
    outcome = await EvalPairwiseCommand().run(
        EvalPairwiseArgs(
            experiment=str(document),
            baseline="dense",
            arm="wide",
            criterion=PairwiseCriterion.COMPREHENSIVENESS,
        ),
        _ctx(llm),
    )
    rendered = render_outcome(outcome)

    # Assert
    assert isinstance(outcome, Produced)
    [written] = sorted((tmp_path / "replay-fixture" / "pairwise").glob("*.json"))
    assert written.name.startswith("dense-vs-wide")
    record = load_pairwise_record(written)
    assert record.summaries[0].wins_b == 2
    assert rendered.exit_code is ExitCode.SUCCESS
    assert "comprehensiveness" in (rendered.stdout or "")
    assert str(written) in (rendered.stdout or "")
    assert len(llm.sent) == 2 * 2


async def test_every_criterion_is_judged_when_none_is_named(tmp_path: Path) -> None:
    # Arrange
    document = _document(tmp_path)
    llm = _JudgeLLM()

    # Act
    outcome = await EvalPairwiseCommand().run(
        EvalPairwiseArgs(experiment=str(document), baseline="dense", arm="wide", limit=1),
        _ctx(llm),
    )

    # Assert
    assert isinstance(outcome, Produced)
    [written] = sorted((tmp_path / "replay-fixture" / "pairwise").glob("*.json"))
    record = load_pairwise_record(written)
    assert {summary.criterion for summary in record.summaries} == set(PairwiseCriterion)
    assert len(llm.sent) == len(PairwiseCriterion) * 2


async def test_an_unknown_arm_is_a_resolution_failure(tmp_path: Path) -> None:
    # Arrange
    document = _document(tmp_path)

    # Act
    with pytest.raises(UnknownArmError) as refused:
        await EvalPairwiseCommand().run(
            EvalPairwiseArgs(experiment=str(document), baseline="dense", arm="widest"),
            _ctx(_JudgeLLM()),
        )

    # Assert
    assert exit_code_for(refused.value) is ExitCode.RESOLUTION_FAILED


def test_an_arm_compared_with_itself_is_refused_as_arguments() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="dense"):
        EvalPairwiseArgs(experiment="e.toml", baseline="dense", arm="dense")


def test_the_command_calls_a_model_and_writes() -> None:
    # Assert
    assert EvalPairwiseCommand.permission_class is PermissionClass.WRITE
    assert EvalPairwiseCommand.help


async def test_only_judges_the_questions_named_in_the_file(tmp_path: Path) -> None:
    # Arrange — 44.43b's gold-referee calibration judges chosen questions, not the first N.
    document = _document(tmp_path)
    only = tmp_path / "only.txt"
    only.write_text("q2\n", encoding="utf-8")
    llm = _JudgeLLM()

    # Act
    outcome = await EvalPairwiseCommand().run(
        EvalPairwiseArgs(
            experiment=str(document),
            baseline="dense",
            arm="wide",
            criterion=PairwiseCriterion.COMPREHENSIVENESS,
            only=str(only),
        ),
        _ctx(llm),
    )

    # Assert
    assert isinstance(outcome, Produced)
    [written] = sorted((tmp_path / "replay-fixture" / "pairwise").glob("*.json"))
    record = load_pairwise_record(written)
    assert [verdict.question_id for verdict in record.verdicts] == ["q2"]
    assert len(llm.sent) == 2
