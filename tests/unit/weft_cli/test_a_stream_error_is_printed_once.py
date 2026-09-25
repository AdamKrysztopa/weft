"""Task 43.36: a stream error reaches stdout only when a chunk a reader could see did.

A command that streamed nothing but hidden `index`-role chunks and then failed printed the
failure twice: `[stream error: …]` on stdout from `PrintingSink.close`, and the refusal on stderr.
`_EmissionTrackingSink` is role-blind by design
(`weft_cli/cli.py:363 "class _EmissionTrackingSink"`), so it counts a chunk no reader saw as a
stream that broke. The marker ends a line the reader watched grow; with nothing
shown, there is no such line and the refusal on stderr is the one account of the failure. This is
the 2026-08-20 double print, back for streams nobody sees (found writing `R43.48`'s red).
"""

from __future__ import annotations

import argparse
import io
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_cli import cli
from weft_cli.sinks import PrintingSink
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome
from weft_kernel.registry import Registry
from weft_llm.payload import TokenChunk


class _Args(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _StreamThenFail:
    """`test_cli._StreamingBoomCommand`, emitting its one chunk on the role `role` names."""

    args_model: ClassVar[type[BaseModel]] = _Args
    result_model: ClassVar[type[CommandResult]] = CommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "stream one chunk, then fail"
    role: ClassVar[str] = "index"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args
        deps = ctx.require(Dependencies)
        await deps.token_sink.emit(TokenChunk(role=type(self).role, text="partial"))
        raise WeftError("the model call broke")


class _HiddenThenFail(_StreamThenFail):
    role: ClassVar[str] = "index"


class _ShownThenFail(_StreamThenFail):
    role: ClassVar[str] = "generate"


async def _run(command: type[_StreamThenFail]) -> tuple[str, str | None]:
    registry = Registry()
    registry.add(Command, "streamer", command, distribution="acme-cmd")
    stdout = io.StringIO()
    sink = PrintingSink(stream=stdout, progress_stream=io.StringIO())
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection(), token_sink=sink)
    rendered = await cli.run_command("streamer", argparse.Namespace(), deps)
    return stdout.getvalue(), rendered.stderr


async def test_a_failure_after_only_hidden_chunks_is_reported_once_on_stderr() -> None:
    # Act
    stdout, stderr = await _run(_HiddenThenFail)

    # Assert
    assert "stream error" not in stdout
    assert stdout == ""
    assert stderr is not None
    assert "the model call broke" in stderr


async def test_a_failure_after_a_shown_chunk_still_marks_the_broken_line() -> None:
    # Act
    stdout, stderr = await _run(_ShownThenFail)

    # Assert
    assert stdout == "partial\n[stream error: the model call broke]\n"
    assert stderr is not None
    assert "the model call broke" in stderr
