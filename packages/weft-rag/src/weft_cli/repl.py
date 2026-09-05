"""`weft` with no arguments — the interactive session.

Task **3.4**: "the interactive session and the one-shot invocation are the same commands with a
different renderer, not two implementations." `docs/03-cli.md` -> *Two modes, one
implementation*: "Both go through the same command objects... it is the same commands with a
different renderer and a persistent context." This module *is* that persistent context; it is
deliberately not a second parser and not a second dispatch path.

**Dispatch reuses `weft_cli.cli.build_parser` and `weft_cli.cli.run_command` unchanged.** A line
typed at the prompt is tokenised with `shlex.split` — so `weft ask "what changed?"` typed as a
one-shot and `ask "what changed?"` typed at this prompt parse identically — against the *same*
registry-driven `argparse.ArgumentParser` `weft --help` is generated from (`cli.build_parser`'s
own docstring). `run_command` does the resolving, the permission gate
(`weft_cli.confirm.gate`) and the seam-wrapped run; this module never touches any of that, which
is what "not two implementations" actually means here — there is nothing for this loop to
duplicate.

**Slash commands are the session's own surface, and task 3.5 brings the count to seven.**
`docs/03-cli.md` -> *In-session commands* names eight: `/help`, `/pipeline`, `/plugins`,
`/trace`, `/eval`, `/config`, `/clear`, `/exit`. Task 3.4 shipped three; this task ships four
more:

- `/help` — reads the identical `Registry.names_for(Command)` walk `cli.build_parser` already
  performs, so it cannot list a command that is not actually installed.
- `/exit` — ends the loop. Trivial, but a session with no way out is not a session.
- `/plugins` — a slash **alias** for the already-registered `"plugins list"` `Command`, proof
  that a slash command is not required to be a second implementation: it constructs the
  identical `args` `parser.parse_args(["plugins", "list"])` would and calls `cli.run_command`,
  exactly as a bare `plugins list` typed at this same prompt already would.
- `/pipeline [name]` — task 3.5's own: shows the session's `active_pipeline` with no argument,
  sets it with one. `weft_cli.session`'s own module docstring carries the full argument for why
  this is a bare, unvalidated name (no `weft pipeline` command surface exists yet — task 3.7's).
- `/trace` — task 3.5's own: prints the `TurnTrace` `weft_cli.session.with_turn_recorded` last
  attached, or says plainly that nothing has run yet.
- `/clear` — task 3.5's own: resets the session's `SessionState` to a blank one
  (`weft_cli.session.cleared`) — see that module's own docstring for why this resets *state*,
  since there is no conversation history yet to clear specifically.
- `/session` — **new**, not one of `03`'s original eight, and it is this task's resolution of a
  naming collision `03` itself had: that document named `/config` as the command that prints
  session state, written before task 3.4 deferred `/config` itself to task 3.7's *project*
  configuration surface (`weft config get/set`, `weft.toml`). Those are two different questions
  — `weft.toml` read once at startup; a session's own state changing every turn — so this task
  gives the session its own command and edits `docs/03-cli.md` in the same commit to name it.
  `weft_cli.session`'s own module docstring carries the argument in full.

**`/config`, shipped task 3.7 — a `run_command` alias for `weft config get`, on `/plugins`'s
own precedent, never the session's own state (`/session` prints that).** `weft_cli.
config_commands.ConfigGetCommand` is registered like any other command by task 3.7; `/config`
with no argument builds `parser.parse_args(["config", "get"])` and calls `cli.run_command`
exactly as `/plugins` already does for `"plugins list"` — a second alias proving the first
was a pattern, not a special case. `/config <key>` forwards `<key>` as `--key` (`weft_cli.
argparse_gen`'s own mechanical rule turns `ConfigGetArgs.key: str | None` into a flag, never
an optional positional — see that module's own docstring), so `/config services.embed` types
the identical query `weft config get --key services.embed` would.

**Deferred, named rather than silently skipped or half-built** (`_DEFERRED_SLASH_COMMANDS`
below prints exactly which task owns each, so a user typing one is told the truth instead of
getting a stub):

- `/eval` — **still deferred as of task 4.6, for a different reason than before.** `weft eval
  run|compare` and `weft trace` are registered `Command`s now (`weft_cli.eval_commands`), and a
  **bare**, non-slash line already reaches them inside this very session — `eval run <path>
  <pipeline>`, `eval compare <a> <b>` and `trace <run-id>` all parse against the identical
  registry-driven grammar every other command here does, with nothing in this module to change
  (see this file's own top paragraph: dispatch is not duplicated). What is still missing is only
  the **slash alias** — `/plugins` and `/config` each alias to one command with at most one bare
  argument (`plugins list`, `config get [--key]`); `/eval` would have to multiplex between two
  verbs that each need two required positional arguments of their own (`run`'s `<path>
  <pipeline>`, `compare`'s `<a> <b>`), which is genuinely more than either precedent's own
  one-line `parser.parse_args([...])` call. Building that multiplexing is a small, real,
  separable piece of REPL-layer work — named here rather than invented mid-task.

**Every value the session applies is exactly what `/session` and `/trace` print — nothing
more.** `SessionState` (`weft_cli.session`) is the whole of what this loop carries between
turns; `run_repl` below holds exactly one local variable of that type, reassigned each turn
(`state = with_turn_recorded(state, ...)`, never `state.foo = ...`) on the frozen-model-
replaced-wholesale idiom that module's own docstring names. Conversation history and "the
collection" — the other two of `03`'s four — are deferred, argued, in that same module rather
than built here as dead state; see its docstring for both arguments in full, including a
stateless-chat failure mode (`.phase3-design.md` §2.5) this task is careful not to
reproduce in the opposite direction — state that *looks* consulted and is not is the same
defect as a session that looks stateful and holds nothing.

**Completion — the mechanism task 3.8's automated test will assert against, not that test
itself.** `repl_completions(registry, prefix)` is a pure function: every `Command` name
`registry` has that starts with `prefix`, walked off the identical `Registry.names_for(Command)`
`cli.build_parser` and `/help` above both already read. `docs/03-cli.md` -> *Plugin-contributed
commands*: "They appear in `weft --help`, in REPL completion" — a stranger's registered command
appears in this function's output the moment it registers, with nothing here naming it, which is
exactly the property `--help` already has. Task 3.8 is the *automated proof* that a real
installed stranger's command shows up here (`docs/build-ledger.md`'s own line for it); this
module wires it into Python's `readline` for a real interactive session (`_install_completer`)
but the pure function above is what a test — 3.8's, or this file's own — can call directly,
without a pty or a keypress.

**Reading a line is a plain blocking call (`input`, via `read_line` below), not
`asyncio.to_thread` — a stated, temporary property, not an oversight.** Nothing else is
scheduled on this loop while the prompt waits: no stage, no concurrent stream, no sibling
`Command` — the identical argument `weft_cli.cli.run_command`'s own docstring makes for why a
`Command` invocation is not wrapped under the blocking-call guard at all (`.phase3-design.md`
O1, task 3.4). **That argument stops holding the moment task 3.6 ships token streaming that has
to interleave with this loop's next prompt** — recorded in `.phase3-design.md` §4 as the
follow-on open item for 3.6, not solved here.

**Exit code.** `run_repl` returns `ExitCode.SUCCESS` whether the session ended by `/exit` or by
end-of-input (`EOFError` — Ctrl-D on a real terminal), regardless of what the *last* command run
inside it returned. A REPL is a shell, not a pipeline of one command — G8 already settled that a
script asserting an exit code uses a one-shot invocation, exactly so that code means something;
nothing in `docs/03-cli.md` -> *Output* claims a session's own process exit reflects its last
command, and inventing that claim here would be a second, undocumented exit-code contract.

**`KeyboardInterrupt` while idle at the prompt re-prompts, like a shell's own `^C` handling; a
`CancelledError` raised while a command is actually running is never caught here.** The two are
easy to conflate and this is exactly the file G6 warns Ctrl-C handling in a REPL tends to break
it in: `read_line`'s own `try`/`except KeyboardInterrupt` below is scoped to the read alone, with
nothing awaited inside it, so there is no in-flight `Command.run` for it to interrupt half-way.
`await cli.run_command(...)` below sits outside that `except` clause entirely — a `CancelledError`
raised from inside it propagates out of `run_repl` untouched, the same property
`weft_cli.cli.main`'s own `_report_unexpected` docstring requires of the one-shot path.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from typing import Final, cast

from weft_cli.cli import COMMAND_NAME_ATTR, run_command
from weft_cli.exit_codes import ExitCode
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.render import Rendered
from weft_cli.session import SessionState, cleared, with_active_pipeline, with_turn_recorded
from weft_command.contract import Command
from weft_kernel.registry import Registry, unwrap_factory

PROMPT: Final[str] = "weft> "

_SESSION_COMMANDS_TEXT: Final[str] = (
    "/help, /exit, /plugins, /pipeline, /trace, /clear, /session, /config"
)

#: `docs/03-cli.md` -> *In-session commands* names one more than this task ships — see the
#: module docstring's own paragraph on why it is deferred rather than stubbed. `/config`
#: shipped task 3.7 (below); `/eval` is registered (task 4.6) but has no slash alias yet.
_DEFERRED_SLASH_COMMANDS: Final[dict[str, str]] = {
    "eval": (
        "no slash alias yet — 'eval run <path> <pipeline>'/'eval compare <a> <b>' already "
        "work here without the leading slash, exactly like any other registered command"
    ),
}


def read_line(prompt: str) -> str:
    """`input(prompt)`, in its own name — the identical monkeypatch-ability convention
    `weft_cli.confirm.read_confirmation` already uses for the same reason: a test drives this
    with a scripted sequence, never a real terminal, which CI never is.
    """
    return input(prompt)


def repl_completions(registry: Registry, prefix: str) -> list[str]:
    """Every registered `Command` name starting with `prefix` — see the module docstring's
    *"Completion"* paragraph. Sorted, so a fixed prefix always yields a fixed order.
    """
    return sorted(name for name in registry.names_for(Command) if name.startswith(prefix))


def _install_completer(registry: Registry) -> None:
    """Wire `repl_completions` into `readline`'s own Tab-completion protocol, best-effort.

    `readline` is not available on every platform CPython ships for (notably stock Windows
    builds) — caught narrowly by `ImportError` and skipped, since a session with no Tab
    completion is still a working session, unlike any of this module's other failure modes.
    """
    try:
        import readline
    except ImportError:
        return

    def _complete(text: str, state: int) -> str | None:
        matches = repl_completions(registry, text)
        return matches[state] if state < len(matches) else None

    readline.set_completer(_complete)
    readline.parse_and_bind("tab: complete")


def _help_text(registry: Registry) -> str:
    lines = [
        f"session commands: {_SESSION_COMMANDS_TEXT}",
        "(docs/03-cli.md -> In-session commands names more; the rest are not shipped yet)",
        "",
        "commands:",
    ]
    for name in sorted(registry.names_for(Command)):
        factory = unwrap_factory(registry.entry(Command, name).factory)
        # The same defensive `getattr` `cli._add_command_level` already uses to read `help`
        # off an unwrapped factory — see that function's own docstring.
        help_text = cast(str, getattr(factory, "help", ""))
        lines.append(f"  {name:<24} {help_text}")
    return "\n".join(lines)


def _trace_text(state: SessionState) -> str:
    """`/trace`'s whole answer — see `weft_cli.session.TurnTrace`'s own docstring for the shape."""
    trace = state.last_trace
    if trace is None:
        return "no command has run yet this session."
    return f"last run: '{trace.command_name}' ({trace.line!r}) -> exit {int(trace.exit_code)}"


def _session_text(state: SessionState) -> str:
    """`/session`'s whole answer — every value `state` carries, nothing more and nothing less.

    This is the print `weft_cli.session`'s own module docstring calls the whole point of task
    3.5: if a value influences a run and does not appear here, the property has failed
    regardless of what any test says — so this function is deliberately every field
    `SessionState` declares, in one place, rather than assembled piecemeal by callers.
    """
    pipeline = state.active_pipeline if state.active_pipeline is not None else "(none set)"
    lines = [
        f"active pipeline: {pipeline}",
        _trace_text(state),
        "conversation history: not tracked this session — weft_cli.session's own module "
        "docstring carries why.",
    ]
    return "\n".join(lines)


async def _dispatch_config(
    rest: str, *, parser: argparse.ArgumentParser, deps: Dependencies, state: SessionState
) -> tuple[Rendered, bool, SessionState]:
    """`/config [key]` — task 3.7: an alias for `config get`, `/plugins`'s own pattern
    proven a second time. Split out of `_dispatch_slash` on its own, not because the logic
    is complex, but because it is the eighth branch that function's own `ruff` complexity
    budget refused to grow past — the same reason `_help_text`/`_trace_text`/`_session_text`
    already live outside it.

    `/config` prints the *project's* effective `weft.toml`, never the session's own state
    (`/session` prints that — see this module's own docstring resolution note). `rest`, if
    given, is forwarded as `--key` — `/config services.embed` types the identical query
    `weft config get --key services.embed` would.
    """
    if "config get" not in deps.registry.names_for(Command):
        return (
            Rendered(
                stdout=None,
                stderr="'config get' is not registered in this session.",
                exit_code=ExitCode.SUCCESS,
            ),
            True,
            state,
        )
    tokens = ["config", "get", *(["--key", rest] if rest else [])]
    args = parser.parse_args(tokens)
    rendered = await run_command("config get", args, deps)
    state = with_turn_recorded(
        state, command_name="config get", line=" ".join(tokens), exit_code=rendered.exit_code
    )
    return rendered, True, state


async def _dispatch_slash(
    line: str, *, parser: argparse.ArgumentParser, deps: Dependencies, state: SessionState
) -> tuple[Rendered, bool, SessionState]:
    """One line beginning with `/`, handled or refused. Returns what to print, whether the
    session keeps running, and `state` — unchanged, or replaced wholesale by whichever of
    `weft_cli.session`'s pure functions this turn's command calls — see the module docstring
    for which of `docs/03-cli.md`'s eight this handles and which it names as deferred.
    """
    body = line[1:].strip()
    name, _, rest = body.partition(" ")
    rest = rest.strip()

    if name == "exit":
        return Rendered(stdout=None, stderr=None, exit_code=ExitCode.SUCCESS), False, state
    if name == "help":
        text = _help_text(deps.registry)
        return Rendered(stdout=text, stderr=None, exit_code=ExitCode.SUCCESS), True, state
    if name == "plugins":
        if "plugins list" not in deps.registry.names_for(Command):
            return (
                Rendered(
                    stdout=None,
                    stderr="'plugins list' is not registered in this session.",
                    exit_code=ExitCode.SUCCESS,
                ),
                True,
                state,
            )
        # `parser.parse_args` — the identical registry-driven grammar a bare `plugins list`
        # typed at this prompt would resolve against — builds the real `argparse.Namespace`
        # `run_command` expects, rather than this module guessing at `Command.args_model`'s
        # shape a second time.
        args = parser.parse_args(["plugins", "list"])
        rendered = await run_command("plugins list", args, deps)
        # `/plugins` is a real `run_command` call, so it updates "the last run's trace" exactly
        # as a bare command would — see `weft_cli.session.with_turn_recorded`'s own docstring.
        state = with_turn_recorded(
            state, command_name="plugins list", line="plugins list", exit_code=rendered.exit_code
        )
        return rendered, True, state
    if name == "config":
        return await _dispatch_config(rest, parser=parser, deps=deps, state=state)
    if name == "pipeline":
        if rest:
            state = with_active_pipeline(state, rest)
            return (
                Rendered(
                    stdout=f"active pipeline set to '{rest}'.",
                    stderr=None,
                    exit_code=ExitCode.SUCCESS,
                ),
                True,
                state,
            )
        pipeline_text = (
            f"active pipeline: {state.active_pipeline}"
            if state.active_pipeline is not None
            else "no active pipeline set. usage: /pipeline <name>."
        )
        return Rendered(stdout=pipeline_text, stderr=None, exit_code=ExitCode.SUCCESS), True, state
    if name == "trace":
        return (
            Rendered(stdout=_trace_text(state), stderr=None, exit_code=ExitCode.SUCCESS),
            True,
            state,
        )
    if name == "clear":
        state = cleared(state)
        return (
            Rendered(stdout="session state cleared.", stderr=None, exit_code=ExitCode.SUCCESS),
            True,
            state,
        )
    if name == "session":
        return (
            Rendered(stdout=_session_text(state), stderr=None, exit_code=ExitCode.SUCCESS),
            True,
            state,
        )
    if name in _DEFERRED_SLASH_COMMANDS:
        return (
            Rendered(
                stdout=None,
                stderr=(
                    f"/{name} is named in docs/03-cli.md but not shipped yet — "
                    f"{_DEFERRED_SLASH_COMMANDS[name]}."
                ),
                exit_code=ExitCode.SUCCESS,
            ),
            True,
            state,
        )
    return (
        Rendered(
            stdout=None,
            stderr=f"unknown session command: /{name}. /help for the list.",
            exit_code=ExitCode.SUCCESS,
        ),
        True,
        state,
    )


async def run_repl(deps: Dependencies, parser: argparse.ArgumentParser) -> ExitCode:
    """Read a line, resolve it against `parser` — the same registry-driven grammar `--help` is
    generated from — run it through `weft_cli.cli.run_command`, and render what comes back.
    Loops until `/exit`, end-of-input, or an uncaught exception (`CancelledError` included; see
    the module docstring's own paragraph). Returns the session's own exit code, always `SUCCESS`
    on a clean end — see the module docstring's *"Exit code"* paragraph for why.
    """
    _install_completer(deps.registry)
    print("weft -- interactive session. /help for commands, /exit to leave.")
    # `state` is the whole of what this session carries between turns — see the module
    # docstring's own paragraph and `weft_cli.session`'s: one local variable, reassigned
    # wholesale each turn, never mutated in place.
    state = SessionState()
    while True:
        try:
            line = read_line(PROMPT)
        except EOFError:
            return ExitCode.SUCCESS
        except KeyboardInterrupt:
            print()
            continue

        line = line.strip()
        if not line:
            continue

        if line.startswith("/"):
            rendered, keep_running, state = await _dispatch_slash(
                line, parser=parser, deps=deps, state=state
            )
        else:
            try:
                tokens = shlex.split(line)
            except ValueError as exc:
                print(f"could not parse: {exc}", file=sys.stderr)
                continue
            try:
                args = parser.parse_args(tokens)
            except SystemExit:
                # `argparse` already printed its own usage/error to stderr — a bad line in a
                # session re-prompts, unlike a bad line in a one-shot invocation, which is
                # exactly the property that makes this a session rather than a batch of one.
                continue
            command_name = cast(str, getattr(args, COMMAND_NAME_ATTR))
            rendered = await run_command(command_name, args, deps)
            state = with_turn_recorded(
                state, command_name=command_name, line=line, exit_code=rendered.exit_code
            )
            keep_running = True

        if rendered.stdout is not None:
            print(rendered.stdout)
        if rendered.stderr is not None:
            print(rendered.stderr, file=sys.stderr)
        if not keep_running:
            return ExitCode.SUCCESS


__all__ = ["PROMPT", "read_line", "repl_completions", "run_repl"]
