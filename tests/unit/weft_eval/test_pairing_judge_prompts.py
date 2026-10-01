"""R44.18 — records judged under different prompts do not pair.

`RunRecord.judge_prompts` digests each judge's prompt so two records can be told to have been
judged by different questions of the model. It was recorded and never read, so a table, a replay or
a pairwise comparison pooled scores a different prompt had produced and reported one number.
"""

from pathlib import Path

import pytest

from tests.unit.weft_eval.replay_records import METRIC, experiment_of, record_of, records_of
from weft_eval.falsify import UnpairableRecordsError, pairing_reasons
from weft_eval.replay import replay
from weft_eval.run_record import RunRecord

_SCORES = {"q1": 1.0, "q2": 0.0}


def _record(tmp_path: Path, arm: str, prompts: dict[str, str] | None) -> RunRecord:
    return record_of(experiment_of(tmp_path, ("a", "b")), arm, _SCORES, judge_prompts=prompts)


def test_two_records_judged_under_different_prompts_do_not_pair(tmp_path: Path) -> None:
    # Arrange
    one = _record(tmp_path, "a", {METRIC: "a" * 64})
    other = _record(tmp_path, "b", {METRIC: "b" * 64})

    # Act
    reasons = pairing_reasons(one, other)

    # Assert
    assert any(f"judge prompt for '{METRIC}' differs" in reason for reason in reasons)


def test_the_same_prompt_pairs(tmp_path: Path) -> None:
    # Arrange
    one = _record(tmp_path, "a", {METRIC: "a" * 64})
    other = _record(tmp_path, "b", {METRIC: "a" * 64})

    # Act / Assert
    assert pairing_reasons(one, other) == ()


@pytest.mark.parametrize("recorded", [None, {}, {"another_judge": "c" * 64}])
def test_a_record_that_lacks_the_digest_is_not_a_disagreement(
    tmp_path: Path, recorded: dict[str, str] | None
) -> None:
    # Arrange — an older record, or one that judged a different metric, says nothing either way.
    one = _record(tmp_path, "a", {METRIC: "a" * 64})
    other = _record(tmp_path, "b", recorded)

    # Act / Assert
    assert pairing_reasons(one, other) == ()
    assert pairing_reasons(other, one) == ()


def test_replay_refuses_arms_judged_under_different_prompts(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = [
        *records_of(experiment, {"a": _SCORES}),
        record_of(experiment, "b", _SCORES, judge_prompts={METRIC: "b" * 64}),
        record_of(experiment, "b", _SCORES, repetition=2, judge_prompts={METRIC: "b" * 64}),
    ]
    records[0] = record_of(experiment, "a", _SCORES, judge_prompts={METRIC: "a" * 64})
    records[1] = record_of(experiment, "a", _SCORES, repetition=2, judge_prompts={METRIC: "a" * 64})

    # Act / Assert
    with pytest.raises(UnpairableRecordsError, match="judge prompt"):
        replay(experiment, records, metric=METRIC)
