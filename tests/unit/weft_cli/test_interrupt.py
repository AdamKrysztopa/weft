"""Carried repair **R43.8** — Ctrl-C ends a command with one line and exit 130, not a traceback.

Found running Exit B (`43.11`): `weft index` interrupted mid-layer printed about thirty lines of
`asyncio` traceback. The records it left were right (the batch in flight `indexing`, the rest
untouched) and the next run resumed, but `main`'s own contract is that the process never speaks in
stack traces. 130 is the shell's code for a process ended by SIGINT, so scripts still see it.
"""

import sys
from pathlib import Path

import pytest

from weft_cli import cli


def test_an_interrupted_command_says_so_in_one_line_and_exits_130(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    async def interrupted(*_: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["weft", "pipeline", "list"])
    monkeypatch.setattr(cli, "run_command", interrupted)

    # Act
    with pytest.raises(SystemExit) as exited:
        cli.main()

    # Assert
    assert exited.value.code == 130
    err = capsys.readouterr().err
    assert err == "weft pipeline list: interrupted\n"
