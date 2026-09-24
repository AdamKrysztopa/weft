"""Carried repair **R43.8** — Ctrl-C ends a command with one line and exit 130, not a traceback.

Found running Exit B (`43.11`): `weft index` interrupted mid-layer printed about thirty lines of
`asyncio` traceback. The records it left were right (the batch in flight `indexing`, the rest
untouched) and the next run resumed, but `main`'s own contract is that the process never speaks in
stack traces. 130 is the shell's code for a process ended by SIGINT, so scripts still see it.
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from weft_cli import cli
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_llm.contract import TokenSink
from weft_llm.payload import TokenChunk


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


class _NoArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Result(CommandResult):
    seen: str


class _InterruptedMidStream:
    """Emits one chunk, then delivers a real SIGINT to this process and waits to be cancelled.

    The signal rather than a raised `KeyboardInterrupt`, so `asyncio.run`'s own handler does what
    it does in the binary: cancel the running task, which reaches `run_command` as
    `CancelledError`, and only then raise `KeyboardInterrupt` to `main`.
    """

    args_model: ClassVar[type[BaseModel]] = _NoArgs
    result_model: ClassVar[type[CommandResult]] = _Result
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "stream, then be interrupted"
    role: ClassVar[str] = "index"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args
        sink = ctx.require(Dependencies).token_sink
        await sink.emit(TokenChunk(role=self.role, text=f"partial {self.role} text"))
        signal.raise_signal(signal.SIGINT)
        await asyncio.sleep(30)
        return Produced(value=_Result(seen="never"))


class _AskInterruptedMidStream(_InterruptedMidStream):
    role: ClassVar[str] = "generate"


class _BrokenMidStream(_InterruptedMidStream):
    role: ClassVar[str] = "generate"

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args
        sink = ctx.require(Dependencies).token_sink
        await sink.emit(TokenChunk(role=self.role, text="partial answer"))
        raise WeftError("the provider dropped the stream")


def _main_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, command: type[object]
) -> None:
    registry = Registry()
    registry.add(Command, name, command, distribution="acme-cmd")

    def build(*, strict_pins: bool = True, token_sink: TokenSink) -> Dependencies:
        del strict_pins
        return Dependencies(
            registry=registry, reports=(), services=ServiceSelection(), token_sink=token_sink
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["weft", name])
    monkeypatch.setattr(cli, "build_dependencies", build)


@pytest.mark.parametrize(
    ("name", "command"),
    [("index", _InterruptedMidStream), ("ask", _AskInterruptedMidStream)],
)
def test_an_interrupt_mid_stream_prints_no_stream_error_on_stdout(
    name: str,
    command: type[object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Carried repair **R43.48** — Ctrl-C during `weft index` also printed
    `[stream error: command did not complete]` on stdout, beside R43.8's one line on stderr.
    """
    # Arrange
    _main_running(monkeypatch, tmp_path, name, command)

    # Act
    with pytest.raises(SystemExit) as exited:
        cli.main()

    # Assert
    assert exited.value.code == 130
    captured = capsys.readouterr()
    assert "stream error" not in captured.out
    assert captured.err == f"weft {name}: interrupted\n"


def test_a_stream_that_breaks_without_an_interrupt_still_says_so_on_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    _main_running(monkeypatch, tmp_path, "ask", _BrokenMidStream)

    # Act
    with pytest.raises(SystemExit) as exited:
        cli.main()

    # Assert
    assert exited.value.code != 130
    out = capsys.readouterr().out
    assert "[stream error: the provider dropped the stream]" in out
