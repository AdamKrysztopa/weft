"""A resumed measurement is priced on what it will still run — carried repair **R44.9**.

`run_measurement.py` refuses a run whose price passes the spend cap, and it priced every
execution the plan declares. Resuming E2 with 1,800 of 3,000 executions already recorded was
priced at 3,000 and refused against the cap left, though only 1,200 would spend. The price is
the plan's executions minus those of every arm and repetition this experiment's incomplete
invocation already recorded.
"""

from __future__ import annotations

import json
from pathlib import Path

import run_measurement

_PLAN = """\
plan for 'musique-retrieval' (8a51134dea39…)
  dense: index-openai-large → retrieve-then-generate, 1 × 600 question(s) = 600 execution(s)
  hybrid: index-openai-large → hybrid-then-generate, 1 × 600 question(s) = 600 execution(s)
  iterative: index-openai-large → iterative-retrieve, 2 × 600 question(s) = 1200 execution(s)
  index index-openai-large over ../../corpus/musique/corpus: 4084 document(s)
  total query executions: 2400
  judge calls: 2400 (openai:gpt-5.6-luna)
"""
_DIGEST = "8a51134dea39" + "0" * 52


def _record(
    runs: Path, arm: str, repetition: int, *, invocation: str, digest: str = _DIGEST
) -> None:
    runs.mkdir(parents=True, exist_ok=True)
    body = {
        "experiment": {
            "digest": digest,
            "arm": arm,
            "repetition": repetition,
            "invocation": invocation,
        }
    }
    (runs / f"{digest[:8]}-{arm}-{repetition}-{invocation}.json").write_text(json.dumps(body), encoding="utf-8")


def test_the_plan_names_each_arm_s_questions_per_repetition() -> None:
    # Act
    plan = run_measurement.plan_from_text(_PLAN)

    # Assert
    assert plan.executions == 2400
    assert plan.arms == ("dense", "hybrid", "iterative")
    assert plan.questions_per_repetition == {"dense": 600, "hybrid": 600, "iterative": 600}


def test_a_fresh_run_spends_every_execution(tmp_path: Path) -> None:
    # Act
    remaining = run_measurement.unwritten_executions(
        run_measurement.plan_from_text(_PLAN), tmp_path / "runs"
    )

    # Assert
    assert remaining == 2400


def test_a_resumed_run_spends_only_what_its_invocation_has_not_recorded(tmp_path: Path) -> None:
    # Arrange — the incomplete invocation recorded dense and hybrid, and one of iterative's two
    # repetitions; a complete earlier invocation and another experiment's record do not count.
    runs = tmp_path / "runs"
    for arm, repetition in (("dense", 1), ("hybrid", 1), ("iterative", 1)):
        _record(runs, arm, repetition, invocation="resumed")
    for arm, repetition in (("dense", 1), ("hybrid", 1), ("iterative", 1), ("iterative", 2)):
        _record(runs, arm, repetition, invocation="finished")
    _record(runs, "dense", 1, invocation="resumed", digest="f" * 64)

    # Act
    remaining = run_measurement.unwritten_executions(run_measurement.plan_from_text(_PLAN), runs)

    # Assert
    assert remaining == 600
