"""The golden-path check exists, runs in CI, and can fail — carried repair **R20.8**.

`scripts/check_golden_path.py` installs the built wheels into a clean virtualenv and needs a
database of its own, so it cannot sit in the `ci-checks` composite; a check outside the composite
is one that can ship and never run (fitness function 0), so this pins the poe task and the CI job
that run it, and watches a step's verdict go both ways.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Final, cast

import check_golden_path
from check_golden_path import Step, StepResult

from .conftest import REPO_ROOT

SCRIPT: Final[Path] = REPO_ROOT / "scripts" / "check_golden_path.py"
POE_TASK: Final[str] = "golden-path"


def _poe_tasks() -> dict[str, Any]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        document = tomllib.load(handle)
    return cast("dict[str, Any]", document["tool"]["poe"]["tasks"])


def test_the_golden_path_is_a_poe_task_and_a_ci_job() -> None:
    # Arrange
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    # Act
    task = _poe_tasks().get(POE_TASK)

    # Assert
    assert SCRIPT.is_file()
    assert task is not None, f"`pyproject.toml` declares no `{POE_TASK}` task"
    assert "check_golden_path.py" in str(task)
    assert "check_golden_path.py" in workflow, "no CI job runs the golden-path check"


def test_the_path_walks_what_a_stranger_does_in_order() -> None:
    # Arrange
    before, after = check_golden_path.steps()

    # Act
    commands = [step.argv[:2] for step in (*before, *after)]

    # Assert
    assert commands == [
        ("plugins", "doctor"),
        ("index", "corpus"),
        ("ask", "which threads are held taut on the loom"),
        ("ask", "which threads are held taut on the loom"),
        ("ask", "which threads are held taut on the loom"),
        ("eval", "experiment"),
        ("eval", "table"),
    ]
    assert [step.exit_code for step in before] == [0, 0, 0, 1]


def test_the_check_can_actually_fail() -> None:
    # Arrange
    step = Step("lexical ask", ("ask", "q"), 0, "held taut")

    # Act
    verdicts = (
        StepResult(step=step, exit_code=0, output="1. held taut on the loom").passed,
        StepResult(step=step, exit_code=1, output="1. held taut on the loom").passed,
        StepResult(step=step, exit_code=0, output="1. something else").passed,
    )

    # Assert
    assert verdicts == (True, False, False)
