"""`check_sdists.py --run-tests` installs the capability libraries `weft-rag[all]` names.

It kept its own copy of that list, which drifted twice: `qdrant-client` lost its `<1.14` bound,
and `tiktoken` (ledger `32.6`) never arrived, so CI's sdist suite failed at collection on
`import tiktoken`. The list is now read from the `all` extra itself.
"""

import subprocess
import tomllib
from pathlib import Path

import check_sdists
import pytest

_REPO = Path(__file__).resolve().parents[3]


def _all_extra() -> list[str]:
    pyproject = tomllib.loads((_REPO / "packages/weft-rag/pyproject.toml").read_text())
    return pyproject["project"]["optional-dependencies"]["all"]


def test_the_suite_installs_exactly_what_the_all_extra_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    captured: list[list[str]] = []

    def _run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(check_sdists.subprocess, "run", _run)

    # Act
    check_sdists.run_tests_against_sdists([], _REPO)

    # Assert
    command = captured[0]
    installed = {command[i + 1] for i, part in enumerate(command) if part == "--with"}
    assert set(_all_extra()) <= installed
