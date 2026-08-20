"""Unit tests for `weft_cli.repl`.

Mirrors `packages/weft-cli/src/weft_cli/repl.py`. Task **3.4**: "the interactive session and the
one-shot invocation are the same commands with a different renderer, not two implementations."
Drives the loop with scripted input (`monkeypatch.setattr(repl, "read_line", ...)`) and captured
output (`capsys`) — never a real terminal, per this task's own brief: a REPL is testable by
substituting the one name that ever touches stdin, the identical convention
`weft_cli.confirm.read_confirmation` already established for the same reason.
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict

from weft_cli import cli, repl
from weft_cli.exit_codes import ExitCode
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.render import Rendered
from weft_cli.services import ServiceSelection
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry


class _EchoArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str


class _EchoResult(CommandResult):
    seen: str


class _EchoCommand:
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


class _NoArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _StatusResult(CommandResult):
    reports: tuple[str, ...]


class _StatusCommand:
    """Stands in for `plugins list` — a real no-arg registered `Command`, for `/plugins`."""

    args_model: ClassVar[type[BaseModel]] = _NoArgs
    result_model: ClassVar[type[CommandResult]] = _StatusResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "report status"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del args, ctx
        return Produced(value=_StatusResult(reports=("acme-cmd: active",)))


class _ConfigGetArgs(BaseModel):
    """The one shape `/config`'s own forwarding needs to prove: an optional `key`, matching
    `weft_cli.config_commands.ConfigGetArgs`'s own `key: str | None` field closely enough to
    test `/config <key>` becoming `--key <key>`, without depending on that module directly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str | None = None


class _ConfigGetResult(CommandResult):
    key: str | None


class _ConfigLikeCommand:
    """Stands in for `config get` — a real registered `Command`, for `/config`."""

    args_model: ClassVar[type[BaseModel]] = _ConfigGetArgs
    result_model: ClassVar[type[CommandResult]] = _ConfigGetResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = "report config"

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        assert isinstance(args, _ConfigGetArgs)
        return Produced(value=_ConfigGetResult(key=args.key))


def _registry_with(*names: str) -> Registry:
    registry = Registry()
    command_classes: dict[str, type[object]] = {
        "plugins list": _StatusCommand,
        "config get": _ConfigLikeCommand,
    }
    for name in names:
        command_cls = command_classes.get(name, _EchoCommand)
        registry.add(Command, name, command_cls, distribution="acme-cmd")
    return registry


def _deps(*names: str) -> Dependencies:
    return Dependencies(registry=_registry_with(*names), reports=(), services=ServiceSelection())


def _scripted(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    """Feed `run_repl` exactly `lines`, then end the "terminal" with `EOFError`."""
    remaining = iter(lines)

    def _read_line(prompt: str) -> str:
        del prompt
        try:
            return next(remaining)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(repl, "read_line", _read_line)


async def test_run_repl_dispatches_a_registered_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — the property this task exists to build: a bare line typed at the prompt goes
    # through the identical `cli.run_command` a one-shot `weft echo hi` invocation would.
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "echo hi")

    # Act
    exit_code = await repl.run_repl(deps, parser)

    # Assert
    assert exit_code is ExitCode.SUCCESS
    assert "hi" in capsys.readouterr().out


async def test_run_repl_exits_on_slash_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/exit")

    exit_code = await repl.run_repl(deps, parser)

    assert exit_code is ExitCode.SUCCESS
    capsys.readouterr()


async def test_run_repl_exits_on_end_of_input(monkeypatch: pytest.MonkeyPatch) -> None:
    # `EOFError` (Ctrl-D on a real terminal) ends the session exactly as `/exit` does — no
    # scripted lines at all, so `read_line`'s first call raises.
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch)

    exit_code = await repl.run_repl(deps, parser)

    assert exit_code is ExitCode.SUCCESS


async def test_run_repl_help_lists_registered_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/help", "/exit")

    await repl.run_repl(deps, parser)

    assert "echo" in capsys.readouterr().out


async def test_run_repl_plugins_delegates_to_the_registered_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — `/plugins` is a slash alias for the already-registered `plugins list` `Command`,
    # not a second implementation: it goes through the same `run_command` any other name would.
    deps = _deps("plugins list")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/plugins", "/exit")

    await repl.run_repl(deps, parser)

    assert "acme-cmd: active" in capsys.readouterr().out


async def test_run_repl_plugins_reports_when_not_registered(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deps = _deps("echo")  # no "plugins list" in this registry
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/plugins", "/exit")

    await repl.run_repl(deps, parser)

    assert "not registered" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["eval"])
async def test_run_repl_names_a_deferred_slash_command_rather_than_pretending_it_works(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — `docs/03-cli.md` -> *In-session commands* names eight; task 3.4 shipped three
    # (`/help`, `/exit`, `/plugins`), task 3.5 four more (`/pipeline`, `/trace`, `/clear`, and
    # `/session` in `/config`'s place), and task 3.7 ships `/config` for real. `/eval` is the
    # one still deferred, loudly, rather than stubbed.
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, f"/{name}", "/exit")

    await repl.run_repl(deps, parser)

    assert "not shipped yet" in capsys.readouterr().err


async def test_run_repl_config_delegates_to_the_registered_config_get_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — `/config`, task 3.7: an alias for `config get`, `/plugins`'s own pattern
    # proven twice.
    deps = _deps("config get")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/config", "/exit")

    await repl.run_repl(deps, parser)

    assert '"key":null' in capsys.readouterr().out


async def test_run_repl_config_forwards_its_argument_as_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Edge case — `/config services.embed` becomes `config get --key services.embed`.
    deps = _deps("config get")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/config services.embed", "/exit")

    await repl.run_repl(deps, parser)

    assert '"key":"services.embed"' in capsys.readouterr().out


async def test_run_repl_config_reports_when_not_registered(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deps = _deps("echo")  # no "config get" in this registry
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/config", "/exit")

    await repl.run_repl(deps, parser)

    assert "not registered" in capsys.readouterr().err


async def test_run_repl_pipeline_shows_no_active_pipeline_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/pipeline", "/exit")

    await repl.run_repl(deps, parser)

    assert "no active pipeline" in capsys.readouterr().out


async def test_run_repl_pipeline_sets_and_then_shows_the_active_pipeline(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — `docs/03-cli.md`'s own task brief sanctions holding and printing a name with
    # no `pipeline` command surface to validate it against (task 3.7's own); this proves the
    # round trip a session actually needs: set it, then read the same value back.
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/pipeline graphrag", "/pipeline", "/exit")

    await repl.run_repl(deps, parser)

    out = capsys.readouterr().out
    assert "active pipeline set to 'graphrag'" in out
    assert "active pipeline: graphrag" in out


async def test_run_repl_trace_reflects_the_last_command_actually_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/trace", "echo hi", "/trace", "/exit")

    await repl.run_repl(deps, parser)

    out = capsys.readouterr().out
    assert "no command has run yet" in out
    assert "echo hi" in out


async def test_run_repl_plugins_alias_also_updates_the_trace(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # `/plugins` is a real `run_command` call (task 3.4's own note), so "the last run's trace"
    # has to reflect it exactly as a bare command would.
    deps = _deps("plugins list")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/plugins", "/trace", "/exit")

    await repl.run_repl(deps, parser)

    out = capsys.readouterr().out
    assert "plugins list" in out


async def test_run_repl_clear_resets_pipeline_and_trace(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/pipeline graphrag", "echo hi", "/clear", "/session", "/exit")

    await repl.run_repl(deps, parser)

    out = capsys.readouterr().out
    assert "session state cleared" in out
    assert "(none set)" in out
    assert "no command has run yet" in out


async def test_run_repl_session_prints_active_pipeline_and_last_trace_together(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # `/session` is this task's resolution of `docs/03-cli.md`'s `/config` collision — see
    # `weft_cli.session`'s own module docstring for the argument in full.
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/pipeline graphrag", "echo hi", "/session", "/exit")

    await repl.run_repl(deps, parser)

    out = capsys.readouterr().out
    assert "active pipeline: graphrag" in out
    assert "echo hi" in out


async def test_run_repl_reports_an_unknown_slash_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "/bogus", "/exit")

    await repl.run_repl(deps, parser)

    assert "unknown session command" in capsys.readouterr().err


async def test_run_repl_ignores_a_blank_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "   ", "/exit")

    exit_code = await repl.run_repl(deps, parser)

    assert exit_code is ExitCode.SUCCESS


async def test_run_repl_reports_a_bad_usage_line_without_crashing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — `argparse.parse_args` calls `sys.exit(2)` on a bad line; in one-shot mode that
    # ends the process, but the REPL must swallow only the `SystemExit`, print nothing extra,
    # and keep looping — proven here by a scripted line after the bad one still running.
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "bogus-command", "echo hi")

    exit_code = await repl.run_repl(deps, parser)

    assert exit_code is ExitCode.SUCCESS
    assert "hi" in capsys.readouterr().out


async def test_run_repl_reports_an_unparsable_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An unbalanced quote is a `shlex.split` `ValueError`, before argparse ever sees it.
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, 'echo "unterminated', "/exit")

    exit_code = await repl.run_repl(deps, parser)

    assert exit_code is ExitCode.SUCCESS


async def test_run_repl_keyboard_interrupt_at_the_prompt_does_not_end_the_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — Ctrl-C while idle at the prompt (nothing running) re-prompts, like a shell's
    # own `^C` handling; it must not be mistaken for `CancelledError` swallowing, which this
    # test does not exercise — that is the next test below.
    sequence: list[str | type[BaseException]] = [KeyboardInterrupt, "echo hi", EOFError]

    def _next_read_line(prompt: str) -> str:
        del prompt
        outcome = sequence.pop(0)
        if isinstance(outcome, type):
            raise outcome
        return outcome

    monkeypatch.setattr(repl, "read_line", _next_read_line)
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)

    # Act
    exit_code = await repl.run_repl(deps, parser)

    # Assert
    assert exit_code is ExitCode.SUCCESS
    assert "hi" in capsys.readouterr().out


async def test_run_repl_does_not_swallow_cancellation_from_a_running_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # G6: `CancelledError` propagates and is never swallowed — the exact rule Ctrl-C handling
    # in a REPL is where it tends to get broken. This is not a `read_line` interrupt; it is a
    # cancellation raised *while a command is running*, which must reach the caller of
    # `run_repl` untouched.
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    _scripted(monkeypatch, "echo hi")

    async def _cancel(*_args: object, **_kwargs: object) -> object:
        raise asyncio.CancelledError

    monkeypatch.setattr(repl, "run_command", _cancel)

    with pytest.raises(asyncio.CancelledError):
        await repl.run_repl(deps, parser)


async def test_repl_does_not_read_the_next_line_while_a_stream_is_in_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O2 (task 3.4's open item, resolved by task 3.6, `.phase3-design.md` §4): does a token
    now arrive while something else blocks the loop? Proven here, not asserted from reading
    the code — `read_line` sets a flag it can see the instant a "stream" (a scripted
    `run_command` that awaits real elapsed time before returning) is in flight, and the test
    fails the moment `read_line` is ever called while that flag is set. If a future task makes
    the REPL do anything else while a stream runs — polling for `Ctrl-C`, a concurrent next
    read — this is the test that catches it.
    """
    # Arrange
    deps = _deps("echo")
    parser = cli.build_parser(deps.registry)
    streaming = False
    read_line_saw_streaming = False
    lines = iter(["echo hi", "echo again"])

    def _read_line(prompt: str) -> str:
        nonlocal read_line_saw_streaming
        del prompt
        if streaming:
            read_line_saw_streaming = True
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    async def _streaming_run_command(*_args: object, **_kwargs: object) -> Rendered:
        nonlocal streaming
        streaming = True
        await asyncio.sleep(0.02)  # stands in for a token stream still in flight
        streaming = False
        return Rendered(stdout="ok", stderr=None, exit_code=ExitCode.SUCCESS)

    monkeypatch.setattr(repl, "read_line", _read_line)
    monkeypatch.setattr(repl, "run_command", _streaming_run_command)

    # Act
    exit_code = await repl.run_repl(deps, parser)

    # Assert
    assert exit_code is ExitCode.SUCCESS
    assert read_line_saw_streaming is False


def test_repl_completions_reads_registered_command_names() -> None:
    # Arrange — task 3.8's own automated proof ("a plugin's command appears in `--help` and in
    # completion") reads this function directly; this task builds the mechanism, not that test.
    registry = _registry_with("echo", "plugins list", "route")

    # Act
    matches = repl.repl_completions(registry, "pl")

    # Assert
    assert matches == ["plugins list"]


def test_repl_completions_is_empty_for_no_match() -> None:
    registry = _registry_with("echo")

    assert repl.repl_completions(registry, "zzz") == []


def test_read_line_wraps_input(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_input(prompt: str) -> str:
        return f"got: {prompt}"

    monkeypatch.setattr("builtins.input", _fake_input)

    assert repl.read_line("weft> ") == "got: weft> "


def test_main_enters_the_repl_for_bare_invocation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — "weft with no arguments enters an interactive session" — proven at `main`'s own
    # level: a bare argv reaches `run_repl`, never `parser.parse_args([])`, which `argparse`'s
    # own `required=True` subparsers would turn into a bad-usage exit instead.
    import sys as sys_module

    monkeypatch.setattr(sys_module, "argv", ["weft"])
    deps = _deps("echo")

    def _fake_build_dependencies(
        *, strict_pins: bool = True, token_sink: object = None
    ) -> Dependencies:
        del strict_pins, token_sink
        return deps

    monkeypatch.setattr(cli, "build_dependencies", _fake_build_dependencies)
    _scripted(monkeypatch, "/exit")

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == int(ExitCode.SUCCESS)
