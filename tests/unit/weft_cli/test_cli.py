"""Unit tests for `weft_cli.cli`.

Mirrors `packages/weft-cli/src/weft_cli/cli.py`. Task 3.2 replaced the hand-written
`COMMANDS`/`build_parser`/`command_key`/`handle_*` shape this file used to cover with a
registry-driven one — see `cli.py`'s own module docstring. This file now covers: the
`--version` pre-scan never needing a registry (fitness function 8(b) — the categorical,
subprocess form of that property is `tests/architecture/test_ff8_trust_model.py`, unchanged and
still green, so this tier only proves the pre-scan's own logic); `prescan_command_name`'s
heuristic; `build_parser` walking a real (but hand-populated, not discovered) `Registry` into a
grammar, including the nested `plugins` subcommand tree; `run_command`'s dispatch and error
translation; and `main`'s untranslated-exception handling, unchanged from before this task.

**Task 3.3** adds `--yes` at both parser levels and `run_command`'s call into
`weft_cli.confirm.gate` — `weft_cli.confirm`'s own test file covers `gate`'s decision tree in
full; what belongs here is the seam-level proof design question 1 asks for: a hand-registered
`destroy`-class command — `_WipeCommand`, never a real `weft-cli` built-in — is refused with no
TTY and no cooperation from its own `run()`, which flips `ran` only if it actually executed, so
"never proceeds silently" is proven by absence of a side effect, not only by an exit code.

**Task 3.6** adds three things: `global_output_flags`/`token_sink_for`'s own logic (mirroring
`wants_version`'s own pre-scan tests); `run_command` closing `deps.token_sink` exactly once,
with the right `reason`, on every one of its three exits (clean, `WeftError`, an uncaught
exception including `CancelledError`); and `main`'s corrected REPL-entry test — "no command
named", not "empty argv" — see `cli.main`'s own docstring for why that changed.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from weft_cli import cli
from weft_cli.exit_codes import ExitCode
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.render import Rendered
from weft_cli.services import ServiceSelection
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_llm.payload import TokenChunk


class _NoArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _EchoResult(CommandResult):
    seen: str


class _EchoArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str


class _EchoCommand:
    """A minimal, fake `Command` — registered by hand, never discovered, for `build_parser`
    and `run_command` tests that must not depend on the real installed packs.
    """

    args_model: ClassVar[type[BaseModel]] = _EchoArgs
    result_model: ClassVar[type[CommandResult]] = _EchoResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "echo back its one argument"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        assert isinstance(args, _EchoArgs)
        return Produced(value=_EchoResult(seen=args.text))


class _BoomCommand(_EchoCommand):
    """Raises a bare `WeftError` from `run` — for `run_command`'s error-translation test."""

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args, ctx
        raise WeftError("something in the library refused")


class _CancellingCommand(_EchoCommand):
    """Raises `asyncio.CancelledError` from `run` — G6's own proof that `run_command`'s new
    `finally` (task 3.6, closing the token sink) does not turn into a second place cancellation
    can be swallowed.
    """

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args, ctx
        raise asyncio.CancelledError()


class _StreamingBoomCommand(_EchoCommand):
    """Emits one chunk into `ctx.require(Dependencies).token_sink`, then raises a bare
    `WeftError` — the positive case the 2026-08-20 repair's `_EmissionTrackingSink` exists to
    keep true: a command that genuinely starts streaming and then fails must still close with
    the error's own message, never `None`, which is what tells `--json` (`JsonSink`) and a
    human (`PrintingSink`'s own `[stream error: ...]` line) that the stream itself broke.
    `_BoomCommand` above never touches the sink at all, which is exactly why its own close
    reason changed to `None` in the same repair — see `test_run_command_closes_the_token_sink_
    with_none_when_nothing_was_ever_streamed` below.
    """

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args
        deps = ctx.require(Dependencies)
        await deps.token_sink.emit(TokenChunk(role="generate", text="partial answer"))
        raise WeftError("the stream broke mid-flight")


class _StreamingCancellingCommand(_EchoCommand):
    """Emits one chunk, then raises `asyncio.CancelledError` — the mid-stream-cancellation
    counterpart to `_StreamingBoomCommand` above, for the generic "command did not complete"
    fallback `run_command` uses when `failure_reason` was never set (`CancelledError` is not a
    `WeftError`, so `except WeftError` never captures a message for it).
    """

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args
        deps = ctx.require(Dependencies)
        await deps.token_sink.emit(TokenChunk(role="generate", text="partial answer"))
        raise asyncio.CancelledError()


class _RecordingSink:
    """A `weft_llm.contract.TokenSink` that only records `close`'s own `reason` — task 3.6's
    own proof that `run_command` closes the run's sink exactly once, with the right reason,
    on every exit path.
    """

    def __init__(self) -> None:
        self.closed_with: list[str | None] = []

    async def emit(self, chunk: object) -> None:
        del chunk

    async def close(self, *, reason: str | None = None) -> None:
        self.closed_with.append(reason)


class _BlockingCommand(_EchoCommand):
    """Does a real synchronous filesystem read from `run` — the exact shape of `weft index`'s
    own `weft_extract.accept` walk (`.phase3-design.md` O1) that tripped the blocking-call
    guard when task 3.2 first tried running `Command.run` through `weft_kernel.seam.wrap`
    unconditionally. Proof that O1's resolution (`guard_blocking_calls=False`) actually lets
    this kind of command run, not merely that the kernel primitive accepts the keyword.
    """

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        assert isinstance(args, _EchoArgs)
        with Path(__file__).open(encoding="utf-8") as handle:
            handle.read(0)
        return Produced(value=_EchoResult(seen=args.text))


class _StatusCommand:
    """A fake no-argument command — stands in for `plugins list`/`plugins doctor`'s shape."""

    args_model: ClassVar[type[BaseModel]] = _NoArgs
    result_model: ClassVar[type[CommandResult]] = _EchoResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "report status"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args, ctx
        return Produced(value=_EchoResult(seen="status"))


class _WipeArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str


class _WipeCommand:
    """A hand-registered `destroy`-class command — proof for design question 1: it declares
    `permission_class` and nothing else. It never imports `weft_cli.confirm`, never checks a
    TTY itself, and never reads `--yes` — the whole gate is the invocation seam's job, not this
    class's. `ran` is a `ClassVar` rather than an instance attribute because `run_command`
    constructs a fresh instance from `entry.factory` on every call, so a test has no handle on
    that instance to inspect afterward; mutating the class itself is what lets a test assert the
    negative — refused means the destructive body never ran, not merely that the exit code says
    so. Reset to `False` at the top of every test that reads it.
    """

    args_model: ClassVar[type[BaseModel]] = _WipeArgs
    result_model: ClassVar[type[CommandResult]] = _EchoResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.DESTROY
    help: ClassVar[str] = "wipe a collection"
    ran: ClassVar[bool] = False

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        assert isinstance(args, _WipeArgs)
        _WipeCommand.ran = True
        return Produced(value=_EchoResult(seen=args.collection))


def _registry_with(*names: str) -> Registry:
    registry = Registry()
    for name in names:
        command_cls: type[object] = (
            _StatusCommand if name.split(" ")[-1] in {"list", "doctor"} else _EchoCommand
        )
        registry.add(Command, name, command_cls, distribution="acme-cmd")
    return registry


class _FakeDeps:
    """A `Dependencies`-shaped stand-in `main`'s own tests patch `build_dependencies` with —
    only `.registry` is ever read before `run_command` (itself patched below) would need the
    rest.
    """

    def __init__(self, registry: Registry) -> None:
        self.registry = registry


def _fake_build_dependencies(*, strict_pins: bool = True, token_sink: object = None) -> _FakeDeps:
    del strict_pins, token_sink
    return _FakeDeps(_registry_with("echo"))


def _wants_version_false(argv: list[str]) -> bool:
    del argv
    return False


def test_wants_version_true_when_the_flag_is_present() -> None:
    assert cli.wants_version(["--version"]) is True


def test_wants_version_true_alongside_other_tokens() -> None:
    # `--version` wins over any subcommand — the same priority `command_key` gave it before
    # this task, now decided before a registry ever exists to parse anything else against.
    assert cli.wants_version(["index", "./docs", "--version"]) is True


def test_wants_version_false_without_the_flag() -> None:
    assert cli.wants_version(["index", "./docs"]) is False


def test_prescan_command_name_reads_the_first_bare_token() -> None:
    assert cli.prescan_command_name(["index", "./docs"]) == "index"


def test_prescan_command_name_joins_the_plugins_subcommand() -> None:
    assert cli.prescan_command_name(["plugins", "doctor"]) == "plugins doctor"


def test_prescan_command_name_skips_leading_flags() -> None:
    assert cli.prescan_command_name(["--yes", "plugins", "list"]) == "plugins list"


def test_prescan_command_name_is_none_for_no_command() -> None:
    assert cli.prescan_command_name([]) is None
    assert cli.prescan_command_name(["--version"]) is None


def test_wants_help_true_for_the_long_flag() -> None:
    assert cli.wants_help(["--help"]) is True


def test_wants_help_true_for_the_short_flag() -> None:
    assert cli.wants_help(["-h"]) is True


def test_wants_help_false_without_the_flag() -> None:
    assert cli.wants_help(["index", "./docs"]) is False


def test_wants_help_false_for_no_argv() -> None:
    assert cli.wants_help([]) is False


def test_build_parser_parses_a_flat_command() -> None:
    # Arrange
    registry = _registry_with("echo")
    parser = cli.build_parser(registry)

    # Act
    args = parser.parse_args(["echo", "hello"])

    # Assert
    assert args.text == "hello"
    assert getattr(args, cli.COMMAND_NAME_ATTR) == "echo"


def test_build_parser_builds_a_nested_subcommand_tree() -> None:
    # Arrange — the same namespacing `weft plugins list`/`weft plugins doctor` use.
    registry = _registry_with("plugins list", "plugins doctor")
    parser = cli.build_parser(registry)

    # Act
    args = parser.parse_args(["plugins", "doctor"])

    # Assert
    assert getattr(args, cli.COMMAND_NAME_ATTR) == "plugins doctor"


def test_build_parser_accepts_yes_after_the_subcommand() -> None:
    # Arrange — task 3.3: `--yes` is declared on the leaf subparser, the position
    # `weft <command> ... --yes` puts it in, matching `apt-get install -y`/`npm install --yes`.
    registry = _registry_with("echo")
    parser = cli.build_parser(registry)

    # Act
    after = parser.parse_args(["echo", "hello", "--yes"])

    # Assert
    assert after.yes is True
    assert parser.parse_args(["echo", "hello"]).yes is False


def test_build_parser_rejects_yes_before_the_subcommand() -> None:
    # `--yes` is not declared on the top-level parser — see `cli.py`'s own module docstring for
    # why declaring it there too would silently lose the value to the leaf's own default.
    registry = _registry_with("echo")
    parser = cli.build_parser(registry)

    with pytest.raises(SystemExit):
        parser.parse_args(["--yes", "echo", "hello"])


def test_build_parser_rejects_an_unknown_command() -> None:
    # Arrange
    registry = _registry_with("echo")
    parser = cli.build_parser(registry)

    # Act / Assert
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])


def test_build_parser_requires_a_command() -> None:
    # `add_subparsers(required=True)` is what makes a bare `weft` a bad-usage exit (2),
    # dynamically, with no hand-written "a command is required" string to fall behind what
    # is actually registered.
    registry = _registry_with("echo")
    parser = cli.build_parser(registry)

    with pytest.raises(SystemExit):
        parser.parse_args([])


async def test_run_command_returns_the_rendered_success() -> None:
    # Arrange
    registry = _registry_with("echo")
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection())
    args = argparse.Namespace(text="hi")

    # Act
    rendered = await cli.run_command("echo", args, deps)

    # Assert — the fallback structured renderer, since `_EchoResult` is not one of
    # `weft_cli.render`'s five known first-party shapes.
    assert rendered.exit_code is ExitCode.SUCCESS
    assert rendered.stdout is not None
    assert "hi" in rendered.stdout


async def test_run_command_translates_a_weft_error_into_a_rendered_failure() -> None:
    # Arrange
    registry = Registry()
    registry.add(Command, "boom", _BoomCommand, distribution="acme-cmd")
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection())
    args = argparse.Namespace(text="ignored")

    # Act
    rendered = await cli.run_command("boom", args, deps)

    # Assert
    assert rendered.exit_code is ExitCode.OPERATION_FAILED
    assert rendered.stderr == "something in the library refused"


async def test_run_command_attributes_an_error_through_the_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — O1's own proof: a bare `WeftError` a `Command` raises directly gets its
    # pack/contract/plugin attribution filled in by `weft_kernel.seam.wrap`, not left `None`
    # for a caller to notice by its absence. `render_refusal` is intercepted (its own module
    # attribute, re-imported fresh inside `run_command` on every call — see that function's own
    # docstring) so the test can inspect the exception `run_command` actually caught, before it
    # is turned into text.
    from weft_cli import render as render_module

    captured: list[WeftError] = []
    real_render_refusal = render_module.render_refusal

    def _capture(exc: WeftError) -> Rendered:
        captured.append(exc)
        return real_render_refusal(exc)

    monkeypatch.setattr(render_module, "render_refusal", _capture)

    registry = Registry()
    registry.add(Command, "boom", _BoomCommand, distribution="acme-cmd")
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection())
    args = argparse.Namespace(text="ignored")

    # Act
    await cli.run_command("boom", args, deps)

    # Assert
    assert len(captured) == 1
    error = captured[0]
    assert (error.pack, error.contract, error.plugin) == ("acme-cmd", "Command", "boom")


async def test_run_command_does_not_trip_the_blocking_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — the failure `docs/build-ledger.md` 3.2 hit and reverted: a `Command` doing real
    # synchronous filesystem IO (`weft index`'s own shape) must run to completion, not raise
    # `BlockingCallError`, once `Command.run` goes through the seam again for spans and
    # attribution (O1's resolution: `guard_blocking_calls=False`).
    registry = Registry()
    registry.add(Command, "blocking", _BlockingCommand, distribution="acme-cmd")
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection())
    args = argparse.Namespace(text="hi")

    # Act
    rendered = await cli.run_command("blocking", args, deps)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS


async def test_run_command_refuses_a_destroy_class_command_with_no_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — design question 1's own proof: `_WipeCommand` cooperates with none of this,
    # it only declares `permission_class`. `weft_cli.confirm.is_interactive` is monkeypatched,
    # never the real terminal, per design question 3.
    from weft_cli import confirm

    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    _WipeCommand.ran = False
    registry = Registry()
    registry.add(Command, "wipe", _WipeCommand, distribution="acme-cmd")
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection())
    args = argparse.Namespace(collection="reports")

    # Act
    rendered = await cli.run_command("wipe", args, deps)

    # Assert — refused naming the flag, exit 3, and the destructive body never ran.
    assert rendered.exit_code is ExitCode.POLICY_REFUSED
    assert rendered.stderr is not None
    assert "--yes" in rendered.stderr
    assert _WipeCommand.ran is False


async def test_run_command_permits_a_destroy_class_command_with_yes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — `--yes` bypasses the prompt outright, even with no TTY.
    from weft_cli import confirm

    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    _WipeCommand.ran = False
    registry = Registry()
    registry.add(Command, "wipe", _WipeCommand, distribution="acme-cmd")
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection())
    args = argparse.Namespace(collection="reports", yes=True)

    # Act
    rendered = await cli.run_command("wipe", args, deps)

    # Assert
    assert rendered.exit_code is ExitCode.SUCCESS
    assert _WipeCommand.ran is True


async def test_run_command_does_not_double_print_a_gate_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for `weft init` in a genuinely empty directory (reproduced by hand, not
    caught by any existing test): exit `3` and no file written were both already correct, but
    the refusal was printed **twice** — once correctly, via `render_refusal`'s `rendered.
    stderr`, and once more by `PrintingSink.close(reason=...)`, mislabelled `[stream error:
    ...]`, because `gate` refusing *before* `instance.run` ever starts closed the token sink
    with the refusal's own message as if a stream had broken mid-flight. `_WipeCommand`
    stands in for `weft init`/any `overwrite`/`destroy`-class command here — a real `PrintingSink`
    bound to a captured stream is what proves the *complete* output, not only the exit code.
    """
    from weft_cli import confirm
    from weft_cli.sinks import PrintingSink

    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    _WipeCommand.ran = False
    registry = Registry()
    registry.add(Command, "wipe", _WipeCommand, distribution="acme-cmd")
    stream = io.StringIO()
    sink = PrintingSink(stream=stream)
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection(), token_sink=sink)
    args = argparse.Namespace(collection="reports")

    # Act
    rendered = await cli.run_command("wipe", args, deps)

    # Assert — the refusal reaches a reader exactly once, through `rendered.stderr`. The
    # sink's own stream — what `PrintingSink.close` would have written to a real terminal —
    # carries nothing: no trailing newline (nothing was ever emitted), and never a
    # `[stream error: ...]` line, because nothing ever streamed.
    assert rendered.exit_code is ExitCode.POLICY_REFUSED
    assert rendered.stderr is not None
    assert "is a destroy-class command" in rendered.stderr
    assert "stream error" not in rendered.stderr
    assert stream.getvalue() == ""


async def test_run_command_closes_the_token_sink_cleanly_on_success() -> None:
    # Arrange
    registry = _registry_with("echo")
    sink = _RecordingSink()
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection(), token_sink=sink)
    args = argparse.Namespace(text="hi")

    # Act
    await cli.run_command("echo", args, deps)

    # Assert — exactly one close, `reason=None`: G6's own DONE, never mistakable for an error.
    assert sink.closed_with == [None]


async def test_run_command_closes_the_token_sink_with_none_when_nothing_streamed() -> None:
    """Repair, 2026-08-20 — this test used to assert the **opposite**: that `_BoomCommand`'s
    own `WeftError` closed the sink with `"something in the library refused"` as `reason`.
    That was the bug (`run_command`'s own docstring, "Repaired, 2026-08-20", has the report in
    full): `_BoomCommand` never calls `token_sink.emit` at all, so under `PrintingSink` this
    closed with a `[stream error: ...]` line for a command that never streamed a single token
    — indistinguishable, to a reader, from `weft init`'s own double-print bug. The corrected
    rule is `_EmissionTrackingSink`-driven: `reason` is real only when something was actually
    emitted. See `test_run_command_attributes_a_genuine_mid_stream_failure` below for the
    positive case this repair still has to keep true.
    """
    # Arrange
    registry = Registry()
    registry.add(Command, "boom", _BoomCommand, distribution="acme-cmd")
    sink = _RecordingSink()
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection(), token_sink=sink)
    args = argparse.Namespace(text="ignored")

    # Act
    await cli.run_command("boom", args, deps)

    # Assert
    assert sink.closed_with == [None]


async def test_run_command_attributes_a_genuine_mid_stream_failure() -> None:
    # Arrange — `_StreamingBoomCommand` actually calls `token_sink.emit` before raising, unlike
    # `_BoomCommand` above — the positive case: a genuine mid-stream failure must still be
    # attributed, never silently turned into `None` alongside every non-streaming failure.
    registry = Registry()
    registry.add(Command, "streaming-boom", _StreamingBoomCommand, distribution="acme-cmd")
    sink = _RecordingSink()
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection(), token_sink=sink)
    args = argparse.Namespace(text="ignored")

    # Act
    await cli.run_command("streaming-boom", args, deps)

    # Assert — an error can never be mistaken for a clean end (`.phase3-design.md` §2.3(b)).
    assert sink.closed_with == ["the stream broke mid-flight"]


async def test_run_command_closes_the_token_sink_with_none_on_a_gate_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repair, 2026-08-20 — the counterpart to `test_run_command_closes_the_token_sink_with_
    the_weft_error_s_own_reason` above: **that** test's `WeftError` is raised from inside
    `_BoomCommand.run`, after `gate` already let the command start, so the sink genuinely may
    have had something in flight and `reason` carries the message. A `gate` refusal is
    different — `instance.run` never starts at all — and must close with `reason=None`, never
    the refusal's own text, which is what `test_run_command_does_not_double_print_a_gate_
    refusal` proves end to end through a real `PrintingSink`; this proves the same fact one
    layer down, directly against `_RecordingSink.closed_with`.
    """
    from weft_cli import confirm

    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    _WipeCommand.ran = False
    registry = Registry()
    registry.add(Command, "wipe", _WipeCommand, distribution="acme-cmd")
    sink = _RecordingSink()
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection(), token_sink=sink)
    args = argparse.Namespace(collection="reports")

    # Act
    await cli.run_command("wipe", args, deps)

    # Assert
    assert sink.closed_with == [None]


async def test_run_command_closes_the_token_sink_and_still_propagates_cancellation() -> None:
    """Repair, 2026-08-20 — this test used to assert `reason == "command did not complete"`.
    `_CancellingCommand` never calls `token_sink.emit` either, exactly `_BoomCommand`'s own
    shape above, so the corrected rule gives it `None` too — G6 itself (`CancelledError`
    propagates and is never swallowed) is unaffected: `finally` still runs, still closes the
    sink exactly once, and the exception still escapes uncaught.
    """
    # Arrange
    registry = Registry()
    registry.add(Command, "cancel", _CancellingCommand, distribution="acme-cmd")
    sink = _RecordingSink()
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection(), token_sink=sink)
    args = argparse.Namespace(text="ignored")

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await cli.run_command("cancel", args, deps)
    assert sink.closed_with == [None]


async def test_run_command_uses_the_generic_reason_on_mid_stream_cancellation() -> None:
    # Arrange — `_StreamingCancellingCommand` emits first, so cancellation this time interrupts
    # a genuine stream: `failure_reason` stays unset (`CancelledError` is not a `WeftError`, so
    # `except WeftError` never runs), and the generic "command did not complete" fallback —
    # never a fabricated cause `run_command` does not actually know — is what a reader gets.
    registry = Registry()
    registry.add(Command, "streaming-cancel", _StreamingCancellingCommand, distribution="acme-cmd")
    sink = _RecordingSink()
    deps = Dependencies(registry=registry, reports=(), services=ServiceSelection(), token_sink=sink)
    args = argparse.Namespace(text="ignored")

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await cli.run_command("streaming-cancel", args, deps)
    assert sink.closed_with == ["command did not complete"]


def test_global_output_flags_recognises_json_before_the_subcommand() -> None:
    assert cli.global_output_flags(["--json", "route", "hi"]) == (True, False)


def test_global_output_flags_recognises_quiet_before_the_subcommand() -> None:
    assert cli.global_output_flags(["--quiet", "ask", "hi"]) == (False, True)


def test_global_output_flags_defaults_to_neither() -> None:
    assert cli.global_output_flags(["ask", "hi"]) == (False, False)
    assert cli.global_output_flags([]) == (False, False)


def test_global_output_flags_refuses_both_at_once() -> None:
    # `add_mutually_exclusive_group` — a caller asking for a machine-readable stream and no
    # output in the same breath has made a mistake worth naming before discovery ever runs.
    with pytest.raises(SystemExit):
        cli.global_output_flags(["--json", "--quiet"])


def test_token_sink_for_json_is_the_json_sink() -> None:
    from weft_cli.sinks import JsonSink

    assert isinstance(cli.token_sink_for(json=True, quiet=False), JsonSink)


def test_token_sink_for_quiet_is_the_null_sink() -> None:
    from weft_llm.client import NullSink

    assert isinstance(cli.token_sink_for(json=False, quiet=True), NullSink)


def test_token_sink_for_neither_is_the_printing_sink() -> None:
    from weft_cli.sinks import PrintingSink

    assert isinstance(cli.token_sink_for(json=False, quiet=False), PrintingSink)


def test_main_enters_the_repl_when_only_a_global_flag_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — `cli.main`'s own corrected REPL-entry test: "no command named", proven by a
    # flag-only invocation that used to fail `argparse`'s own required-subparser check
    # instead of reaching the REPL. `weft_cli.repl.run_repl` is patched so this exercises only
    # `main`'s own dispatch decision, not the REPL loop itself.
    monkeypatch.setattr(sys, "argv", ["weft", "--quiet"])
    monkeypatch.setattr(cli, "wants_version", _wants_version_false)
    monkeypatch.setattr(cli, "build_dependencies", _fake_build_dependencies)

    from weft_cli import repl as repl_module

    async def _fake_run_repl(_deps: object, _parser: object) -> ExitCode:
        return ExitCode.SUCCESS

    monkeypatch.setattr(repl_module, "run_repl", _fake_run_repl)

    # Act / Assert
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == int(ExitCode.SUCCESS)


def test_main_prints_help_instead_of_entering_the_repl_for_a_bare_help_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — the defect this test reproduces: `prescan_command_name` strips every
    # `-`-prefixed token, so `argv = ["--help"]` reduces to no command name at all and used to
    # be indistinguishable from a bare `weft` — routed straight into the REPL, `--help` never
    # reaching `argparse`'s own generated help. `run_repl` is patched to blow up if `main`
    # still reaches it, so a regression fails here for the same reason the bug was found by
    # hand: the REPL banner, not a silent wrong answer.
    monkeypatch.setattr(sys, "argv", ["weft", "--help"])
    monkeypatch.setattr(cli, "wants_version", _wants_version_false)
    monkeypatch.setattr(cli, "build_dependencies", _fake_build_dependencies)

    from weft_cli import repl as repl_module

    async def _run_repl_must_not_be_reached(_deps: object, _parser: object) -> ExitCode:
        raise AssertionError("weft --help must not enter the REPL")

    monkeypatch.setattr(repl_module, "run_repl", _run_repl_must_not_be_reached)

    # Act / Assert — argparse's own help action exits 0, argparse's convention for a help
    # request (distinct from `2`, its convention for a usage error).
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 0

    # The registry-derived command list (`_registry_with("echo")`, `_fake_build_dependencies`'s
    # own fixture) is what proves this is the generated help, not a hand-written string.
    captured = capsys.readouterr()
    assert "echo" in captured.out


def test_main_prints_help_for_the_short_flag_too(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["weft", "-h"])
    monkeypatch.setattr(cli, "wants_version", _wants_version_false)
    monkeypatch.setattr(cli, "build_dependencies", _fake_build_dependencies)

    from weft_cli import repl as repl_module

    async def _run_repl_must_not_be_reached(_deps: object, _parser: object) -> ExitCode:
        raise AssertionError("weft -h must not enter the REPL")

    monkeypatch.setattr(repl_module, "run_repl", _run_repl_must_not_be_reached)

    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 0
    assert "echo" in capsys.readouterr().out


def test_main_renders_an_untranslated_exception_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A driving adapter never speaks in stack traces — unchanged property, new call site."""
    # Arrange — force `wants_version` false and short-circuit everything downstream of
    # argument parsing so this exercises only `main`'s own `asyncio.run` exception handling.
    monkeypatch.setattr(sys, "argv", ["weft", "echo", "hi"])
    monkeypatch.setattr(cli, "wants_version", _wants_version_false)
    monkeypatch.setattr(cli, "build_dependencies", _fake_build_dependencies)

    async def _boom(_command_name: str, _args: object, _deps: object) -> Rendered:
        raise RuntimeError("connection failed: port 59999")

    monkeypatch.setattr(cli, "run_command", _boom)

    # Act
    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    # Assert
    captured = capsys.readouterr()
    assert exit_info.value.code == int(ExitCode.OPERATION_FAILED)
    assert "RuntimeError: connection failed: port 59999" in captured.err
    assert "Traceback" not in captured.err
    assert "WEFT_TRACEBACK=1" in captured.err


def test_main_re_raises_when_weft_traceback_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "No traceback" is right for a user and wrong for whoever has to fix it."""
    monkeypatch.setattr(sys, "argv", ["weft", "echo", "hi"])
    monkeypatch.setattr(cli, "wants_version", _wants_version_false)
    monkeypatch.setattr(cli, "build_dependencies", _fake_build_dependencies)

    async def _boom(_command_name: str, _args: object, _deps: object) -> Rendered:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "run_command", _boom)
    monkeypatch.setenv("WEFT_TRACEBACK", "1")

    with pytest.raises(RuntimeError, match="boom"):
        cli.main()


def test_main_does_not_swallow_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    """G6: `CancelledError` propagates and is never swallowed."""
    monkeypatch.setattr(sys, "argv", ["weft", "echo", "hi"])
    monkeypatch.setattr(cli, "wants_version", _wants_version_false)
    monkeypatch.setattr(cli, "build_dependencies", _fake_build_dependencies)

    async def _boom(_command_name: str, _args: object, _deps: object) -> Rendered:
        raise asyncio.CancelledError()

    monkeypatch.setattr(cli, "run_command", _boom)

    with pytest.raises(asyncio.CancelledError):
        cli.main()


def test_main_never_builds_a_registry_for_version(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fitness function 8(b), unit-tier: `tests/architecture/test_ff8_trust_model.py` is the
    # subprocess-level, categorical proof; this is the same property asserted against the
    # in-process dispatch this module actually performs.
    def _boom(**_kwargs: object) -> _FakeDeps:
        raise AssertionError("build_dependencies must not be called for --version")

    monkeypatch.setattr(cli, "build_dependencies", _boom)
    monkeypatch.setattr(sys, "argv", ["weft", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == int(ExitCode.SUCCESS)
