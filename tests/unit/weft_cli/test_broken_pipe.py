"""A command whose reader goes away exits quietly, with its own exit code — repair **R38.15**.

Found at `38.7`'s exit by running the installed wheel: `weft trace <id> | head -14` printed its
fourteen lines and then a `BrokenPipeError` traceback, which reads as a failure of the command
rather than of the pipe. Measured again 2026-09-21 on `weft pipeline list` with the read end
closed: `Exception ignored in: <_io.TextIOWrapper name='<stdout>' …> BrokenPipeError` on stderr
and exit **120**, the interpreter's code for a failed flush at shutdown — a number `docs/03-cli.md`
→ *Output* does not define. Unpiped, the same command exits 0.

**The exit code is the command's own.** The reader closing early says nothing about whether the
command succeeded — `head` asked for fewer lines — so a finished command keeps the exit code it
would have had with a reader, and the `--json` refusal below keeps its `4`.

A subprocess, because the property is what somebody's shell sees; the read end is closed before the
child starts, so every write it makes meets a broken pipe regardless of buffer sizes.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
from pathlib import Path

import pytest

from weft_cli import cli
from weft_cli.sinks import JsonSink, PrintingSink, ReaderGoneError
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.registry import Registry
from weft_llm.client import llm_service
from weft_llm.contract import LLMProvider, TokenSink
from weft_llm.payload import Conversation, Message, MessageRole, Rendered, TokenChunk
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.scripted import ScriptedProvider


async def _run(cwd: Path, argv: tuple[str, ...], *, stdout: int) -> tuple[int, str]:
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "weft_cli.cli",
        *argv,
        cwd=cwd,
        stdout=stdout,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await child.communicate()
    return await child.wait(), stderr.decode()


async def _run_into_a_closed_pipe(cwd: Path, argv: tuple[str, ...]) -> tuple[int, str]:
    read_end, write_end = os.pipe()
    os.close(read_end)
    try:
        return await _run(cwd, argv, stdout=write_end)
    finally:
        os.close(write_end)


@pytest.mark.parametrize(
    ("argv", "own_exit_code"),
    [
        (("pipeline", "list"), 0),
        (("--json", "pipeline", "show", "no-such-pipeline"), 4),
    ],
)
async def test_a_closed_reader_ends_the_command_quietly_with_its_own_exit_code(
    tmp_path: Path, argv: tuple[str, ...], own_exit_code: int
) -> None:
    # Act
    returncode, stderr = await _run_into_a_closed_pipe(tmp_path, argv)

    # Assert
    assert "BrokenPipeError" not in stderr, stderr[-600:]
    assert "Traceback (most recent call last)" not in stderr, stderr[-600:]
    assert "Exception ignored" not in stderr, stderr[-600:]
    assert returncode == own_exit_code


async def test_an_open_reader_still_receives_the_output(tmp_path: Path) -> None:
    """The control: whatever silences the closed pipe must not silence an open one."""
    # Arrange
    read_end, write_end = os.pipe()

    # Act
    try:
        returncode, _ = await _run(tmp_path, ("pipeline", "list"), stdout=write_end)
    finally:
        os.close(write_end)
    with os.fdopen(read_end, encoding="utf-8") as reader:
        received = reader.read()

    # Assert
    assert returncode == 0
    assert "\n" in received.strip()


class _ClosedPipe(io.StringIO):
    def write(self, s: str, /) -> int:
        raise BrokenPipeError(32, "Broken pipe")


@pytest.mark.parametrize("sink_class", [PrintingSink, JsonSink])
async def test_a_sink_closes_quietly_when_its_reader_has_gone(
    sink_class: type[PrintingSink] | type[JsonSink],
) -> None:
    """The `--json` refusal above broke here: the sink's closing event is written in
    `run_command`'s `finally`, and the exception replaced the refusal the command had returned.
    A closing event is for a reader, and there is none left to tell."""
    # Arrange
    sink = sink_class(stream=_ClosedPipe())

    # Act / Assert — no exception
    await sink.close(reason="command did not complete")
    await sink.close()


@pytest.mark.parametrize("sink_class", [PrintingSink, JsonSink])
async def test_a_chunk_written_to_a_gone_reader_still_stops_the_command(
    sink_class: type[PrintingSink] | type[JsonSink],
) -> None:
    """A command whose output nobody reads is stopped rather than left spending model calls on
    it — so a chunk's write lets the broken pipe through, and only the closing event is quiet."""
    # Arrange
    sink = sink_class(stream=_ClosedPipe())

    # Act / Assert
    with pytest.raises(BrokenPipeError):
        await sink.emit(TokenChunk(role="generate", text="an answer"))


def test_a_broken_socket_is_still_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dropped connection to a database or a provider raises the same class as a closed
    reader; only the sink's own `ReaderGoneError` is the reader leaving, and anything else is a
    failure the operator is told about."""

    # Arrange
    async def a_socket_breaks(*_: object) -> object:
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["weft", "pipeline", "list"])
    monkeypatch.setattr(cli, "run_command", a_socket_breaks)

    # Act
    with pytest.raises(SystemExit) as exited:
        cli.main()

    # Assert
    assert exited.value.code == 1
    assert "BrokenPipeError" in capsys.readouterr().err


async def test_a_streamed_answer_whose_reader_has_gone_stops_as_the_reader_leaving() -> None:
    """Repair **R38.17**: every chunk of a model's answer reaches the sink from inside
    `LLMClient`'s stream loop, whose catch-all re-raised the sink's `ReaderGoneError` as
    `LLMProviderFaultError` — so `weft ask … | head -1` blamed the provider adapter. The tests
    above call `sink.emit` directly and never went through the client that wraps it."""
    # Arrange
    registry = Registry()
    registry.add(LLMProvider, "scripted", ScriptedProvider, distribution="weft-llm")
    client = llm_service(
        registry=registry, roles=LLMRoles(roles={"generate": RoleMapping(provider="scripted")})
    )
    services = ServiceRegistry()
    services.add(TokenSink, PrintingSink(stream=_ClosedPipe()))
    ctx = Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=services)
    rendered = Rendered(
        conversation=Conversation(messages=(Message(role=MessageRole.USER, content="why?"),))
    )

    # Act / Assert
    with pytest.raises(ReaderGoneError):
        await client.complete(rendered, role="generate", ctx=ctx)


_STAGE_FAILS = """
import sys
from weft_cli import cli
from weft_cli.sinks import ReaderGoneError
from weft_kernel.errors import WeftError

async def a_stage_fails(**_):
    raise WeftError("'generate' failed", stage="generate") from {cause}(32, "Broken pipe")

cli.invoke = a_stage_fails
sys.argv = ["weft", "pipeline", "list"]
cli.main()
"""


@pytest.mark.parametrize(
    ("cause", "quiet"),
    [("ReaderGoneError", True), ("BrokenPipeError", False)],
    ids=["reader-gone", "socket"],
)
async def test_a_stage_that_failed_because_its_reader_left_exits_quietly(
    cause: str, quiet: bool, tmp_path: Path
) -> None:
    """Repair **R38.17**, found by running the wheel: `weft ask …` into a closed pipe printed
    `'generate' failed: ReaderGoneError: [Errno 32] Broken pipe` and exited 1, because the kernel
    seam wraps anything a stage raises in a `WeftError`, so the reader leaving arrived wrapped.
    A subprocess, because the quiet exit silences the process's own stdout descriptor."""
    # Arrange
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _STAGE_FAILS.format(cause=cause),
        cwd=tmp_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    # Act
    _, stderr = await child.communicate()

    # Assert
    assert await child.wait() == 1
    assert (stderr.decode() == "") is quiet
