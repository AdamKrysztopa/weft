"""The readers of an experiment's records name where they looked — carried repair **R20.3**.

`weft eval experiment` writes its records to `runs/` in the directory it ran from; since `R44.3`,
`weft eval table`, `replay` and `pairwise` read `<document>/runs`, where committed evidence lives.
Found running the built wheel at Phase 20b's exit: a stranger's experiment finished, and `weft eval
table` on the same document said only *"no records … were found"*, naming no directory. Each reader
now names the directory it searched and, when the writer's `runs/` holds records of that
experiment, the `--runs` that reads them. The default does not move: a reader that fell back to
another directory unannounced could print a table from records nobody meant.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.unit.weft_eval.replay_records import experiment_of, record_of
from tests.unit.weft_eval.test_evidence import complete_records, fixture_experiment
from weft_cli.eval_pairwise import EvalPairwiseArgs, EvalPairwiseCommand
from weft_cli.eval_replay import EvalReplayArgs, EvalReplayCommand
from weft_cli.eval_table import EvalTableArgs, EvalTableCommand
from weft_eval.evidence import IncompleteExperimentError
from weft_eval.run_record import write_run_record
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered

_QUESTION_SET = """[question_set]
schema = 2
absent = ["kind", "difficulty", "quote", "reference_answer", "notes"]
absent_reason = "a records-elsewhere fixture"
axes = []

[[question]]
id = "q1"
text = "What themes recur across the collection?"
language = "en"
relevant_documents = ["doc.txt"]
"""


class _NeverCalledLLM:
    """A judge the refusal must come before."""

    def __init__(self) -> None:
        self.sent: list[Rendered] = []

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> object:
        raise AssertionError("no judge is reached when there are no records to judge")

    async def complete(
        self, rendered: Rendered, *, role: str, ctx: Context
    ) -> Produced[Completion]:
        del role, ctx
        self.sent.append(rendered)
        raise AssertionError("no judge is reached when there are no records to judge")

    async def close(self) -> None: ...


def _ctx(llm: _NeverCalledLLM | None = None) -> Context:
    services = ServiceRegistry()
    if llm is not None:
        services.add(LLM, llm)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


async def test_table_names_the_writers_runs_when_they_hold_the_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    experiment = fixture_experiment(tmp_path)
    for index, record in enumerate(complete_records(experiment)):
        write_run_record(record, tmp_path / "runs" / f"run-{index}.json")

    # Act
    with pytest.raises(IncompleteExperimentError) as raised:
        await EvalTableCommand().run(
            EvalTableArgs(experiment=str(tmp_path / "experiment.toml")), _ctx()
        )

    # Assert
    message = str(raised.value)
    assert str(tmp_path / "experiment" / "runs") in message
    assert "--runs runs" in message


async def test_table_with_no_records_anywhere_names_where_it_looked_and_no_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    fixture_experiment(tmp_path)

    # Act
    with pytest.raises(IncompleteExperimentError) as raised:
        await EvalTableCommand().run(
            EvalTableArgs(experiment=str(tmp_path / "experiment.toml")), _ctx()
        )

    # Assert
    message = str(raised.value)
    assert str(tmp_path / "experiment" / "runs") in message
    assert "--runs runs" not in message


async def test_table_does_not_offer_runs_holding_only_another_experiments_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    other = experiment_of(tmp_path, ("dense", "wide"), name="another")
    write_run_record(record_of(other, "dense", {"q1": 0.5}), tmp_path / "runs" / "other.json")
    fixture_experiment(tmp_path)

    # Act
    with pytest.raises(IncompleteExperimentError) as raised:
        await EvalTableCommand().run(
            EvalTableArgs(experiment=str(tmp_path / "experiment.toml")), _ctx()
        )

    # Assert
    assert "--runs runs" not in str(raised.value)


async def test_replay_names_the_writers_runs_when_they_hold_the_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    experiment = experiment_of(tmp_path, ("dense", "wide"))
    for arm in ("dense", "wide"):
        for repetition in (1, 2):
            write_run_record(
                record_of(experiment, arm, {"q1": 0.5}, repetition=repetition),
                tmp_path / "runs" / f"{arm}-{repetition}.json",
            )

    # Act
    with pytest.raises(IncompleteExperimentError) as raised:
        await EvalReplayCommand().run(
            EvalReplayArgs(experiment=str(tmp_path / "replay-fixture.toml")), _ctx()
        )

    # Assert
    message = str(raised.value)
    assert str(tmp_path / "replay-fixture" / "runs") in message
    assert "--runs runs" in message


async def test_pairwise_refuses_before_judging_and_names_the_writers_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    (tmp_path / "questions.toml").write_text(_QUESTION_SET, encoding="utf-8")
    experiment = experiment_of(tmp_path, ("dense", "wide"))
    for arm in ("dense", "wide"):
        for repetition in (1, 2):
            record = record_of(
                experiment, arm, {"q1": 0.5}, repetition=repetition, answers={"q1": f"{arm}"}
            )
            write_run_record(record, tmp_path / "runs" / f"{arm}-{repetition}.json")
    judge = _NeverCalledLLM()

    # Act
    with pytest.raises(IncompleteExperimentError) as raised:
        await EvalPairwiseCommand().run(
            EvalPairwiseArgs(
                experiment=str(tmp_path / "replay-fixture.toml"), baseline="dense", arm="wide"
            ),
            _ctx(judge),
        )

    # Assert
    message = str(raised.value)
    assert str(tmp_path / "replay-fixture" / "runs") in message
    assert "--runs runs" in message
    assert judge.sent == []
