"""`weft` — the command line. This module holds the library's only `asyncio.run`.

Task **3.2**: "`weft --help` cannot drift from what is installed, because core has no command
list to edit." Before this task, `COMMANDS` was a hand-written `dict[str, CliCommand]` of six
built-ins and `build_parser` a hand-written argparse grammar — exactly the "list of commands to
edit" the task line refuses. Neither exists any more: every built-in command is now a plugin
registered under `weft_command.contract.Command` (`weft_cli.commands`, the same seam a
third-party pack uses), and this module's job shrinks to three things a driving adapter still has
to do that no registry entry can do for it — decide whether `--version` needs the registry at
all, walk `Registry.names_for(Command)` into an argparse grammar, and run the one `asyncio.run`.

**Fitness function 8(b) — no pack code runs for `weft --version`.** `docs/02-extension-model.md`
§2: "`weft --version`... complete[s] with zero pack code executed. `weft --help` *does* need
[discovery]... That cost is accepted." Generating the parser from the registry means *every other*
command — `--help` included — now needs discovery before a single argument is even validated,
which was not true of the old hand-written grammar. `--version` is the one exemption this module
must still hold categorically, and it cannot be held by *building the registry-driven parser and
then checking a flag on it*, because building that parser is itself the pack code FF8(b) forbids.
`wants_version` is the pre-scan that keeps the two facts compatible: a throwaway,
`--version`-only `argparse.ArgumentParser` (`add_help=False`, one flag, `parse_known_args` so it
tolerates whatever else is on the command line) that never touches `weft_kernel.discovery` at
all. `main` checks it before anything else, and only *that* branch is the one this task promises
stays pack-code-free — `tests/architecture/test_ff8_trust_model.py` is unweakened and still
exercises the real `cli.main()` in a subprocess to prove it.

**`prescan_command_name` is a second, smaller pre-scan, and it is not FF8(b)'s.** `weft plugins
list`/`weft plugins doctor` still need `discover(strict_pins=False)` — the diagnostic exemption
`docs/build-ledger.md` 0.9's own repair added, letting those two commands survive an inert
`[plugins]` pin that would otherwise stop `build_dependencies` from returning a registry at all,
before either command gets the chance to report on it. Which command is about to run has to be
known *before* `build_dependencies` runs (it decides `strict_pins`), and the registry-driven
parser cannot exist yet at that point either — so this is a second, approximate, argv-only guess
at the leading command name, good enough to place one boolean and nothing else. The *real* parse,
against the real registry, happens afterward and is authoritative for everything else.

**No import-time side effect.** Checked for this task's own addendum on the
`load_dotenv(override=True)`-at-import scar: neither this module nor `weft_cli.commands` reads
an environment variable, opens a file or touches the filesystem at module scope — every read
(`weft.toml`, `WEFT_DATABASE_URL`) happens inside a function, called from `main()`, never from an
`import weft_cli.cli` alone. `weft_cli.commands.register` is the one *new* module that discovery
imports (`entry_point.load()`) whenever `build_dependencies` runs at all — its own module
docstring carries the identical check for itself.

**One entry point.** `weft-cli`'s `pyproject.toml` still declares exactly one
`[project.scripts]` line, `weft = "weft_cli.cli:main"` — a `rag-index`/`rag-chat`/`rag-query`
split is the shape `docs/01-high-level-plan.md` → Phase 3 **Lift** names as the one to avoid,
and nothing in this task's own generation layer needs a second surface: every
subcommand this module now discovers still arrives through the one script, the one parser, the
one `asyncio.run` below.

**Task 3.3 adds `--yes`, on every leaf subparser, and `run_command` gains a fourth job: the
permission gate.** `weft_cli.confirm.gate` — see that module's own docstring for the whole
design — needs to know whether `--yes` was passed. `--yes` is declared once per leaf, in
`_add_command_level`, deliberately *not* on the top-level parser here: `argparse`'s own
`_SubParsersAction` parses a subcommand's own remaining tokens into a **fresh** namespace and
then copies every one of its attributes onto the shared one, unconditionally overwriting
whatever a same-named top-level flag had already set — so a `--yes` declared on both levels
would silently lose a `weft --yes <command> ...` spelling back to `False` the moment the
subparser's own default copied over it. One declaration, at the level the value actually has to
survive, is correct where two would be a race the leaf always wins; the convention this leaves —
`weft <command> ... --yes`, the flag following the subcommand — also matches how the destructive
commands this guards `weft` is closest to in spirit (`apt-get install -y`, `npm install --yes`)
already put it. `run_command` reads `args.yes` generically, the same `getattr`-with-default
convention `_add_command_level` already uses for `help`/`args_model`, and calls `confirm.gate`
immediately before `instance.run(...)` — no change to this module's three other jobs.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import os
import sys
import uuid
from collections.abc import Awaitable, Callable
from importlib import metadata
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict

from weft_cli.argparse_gen import add_model_arguments
from weft_cli.exit_codes import ExitCode
from weft_cli.registry_bootstrap import Dependencies, build_dependencies
from weft_cli.sinks import JsonSink, PrintingSink
from weft_command.contract import Command, CommandResult
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome
from weft_kernel.registry import Registry, unwrap_factory
from weft_kernel.seam import wrap
from weft_llm.client import NullSink
from weft_llm.contract import TokenSink
from weft_llm.payload import TokenChunk

if TYPE_CHECKING:
    # `weft_cli.render` imports `weft_cli.commands`, which imports `weft_extract`,
    # `weft_chunk`, `weft_embed` and `weft_store` at its own module scope — see
    # `weft_cli.commands`'s own module docstring. A module-level import here would pull all
    # of that in for `weft --version` too, exactly what fitness function 8(b) refuses; see
    # `run_command`'s and `main`'s own local imports below, and the module docstring's FF8(b)
    # paragraph. `TYPE_CHECKING`-only here so the return-type annotations below still resolve
    # for a type checker without costing `--version` a single import at runtime.
    from weft_cli.render import Rendered

#: `weft_llm.contract.TokenSink` and `weft_llm.client.NullSink` cost nothing at import time
#: — `weft-llm` is already one of `weft-cli`'s own dependencies, publishes no pack of its
#: own to discover, and neither name touches the filesystem or a registry at module scope
#: (checked directly: `weft_llm.client`'s own module-level code is class/function
#: definitions only). Importing them here, unconditionally, costs `weft --version` nothing
#: FF8(b) would notice — unlike `weft_cli.render`/`weft_cli.commands` just above, which pull
#: in `weft_extract`/`weft_chunk`/`weft_embed`/`weft_store` and stay local-import-only.

#: This module, spelled the way an entry point spells it. `own_distribution` finds the
#: distribution that ships `weft` by looking for the `console_scripts` entry point pointing
#: here — a constant rather than `__name__`, which is `"__main__"` when this file is run as a
#: script and would then match nothing.
_CONSOLE_SCRIPT_MODULE = "weft_cli.cli"

#: The two commands whose registry-needing discovery must tolerate an inert `[plugins]` pin —
#: see the module docstring's `prescan_command_name` paragraph. A narrow, unchanged-since-0.9
#: behavioural policy, not the command *list* `03` → *Plugin-contributed commands* is about:
#: that list is entirely the registry's now.
_PIN_DIAGNOSTIC_COMMANDS = frozenset({"plugins list", "plugins doctor"})

#: The attribute `_add_command_level` stamps onto the leaf subparser that matched — the parsed
#: command's own registry name (`"plugins doctor"`, not just `"doctor"`), read back in `main`.
#: Public (no leading underscore), the same convention every other name this module exposes
#: purely so its own tests can call it directly follows — `build_parser`, `run_command`.
COMMAND_NAME_ATTR = "_weft_command_name"

#: Shared between the top-level parser and every leaf subparser — see the module docstring's
#: task-3.3 paragraph on why `--yes` is declared twice rather than once.
_YES_HELP = (
    "permit one overwrite/destroy-class command to run without an interactive confirmation, "
    "for this invocation only (docs/03-cli.md -> Permissions)"
)


class _EmptyArgs(BaseModel):
    """The `getattr(..., "args_model", ...)` default in `_add_command_level` below — never
    actually reached in practice, since `Command.required_declarations` and the protocol's own
    required members mean a real registered command always carries both attributes; it exists
    only so a static type checker has a concrete fallback type to reason about, on the same
    defensive footing `weft_kernel.registry.unwrap_factory`'s own callers already take.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


def wants_version(argv: list[str]) -> bool:
    """Whether `--version` is anywhere in `argv` — see the module docstring's FF8(b) paragraph.

    Never the full, registry-driven parser: building that one already requires discovery, which
    is exactly the pack code this check exists to rule out for `--version`.
    """
    mini = argparse.ArgumentParser(add_help=False)
    mini.add_argument("--version", action="store_true")
    known, _ = mini.parse_known_args(argv)
    return cast(bool, known.version)


def wants_help(argv: list[str]) -> bool:
    """Whether `-h`/`--help` is anywhere in `argv` — `wants_version`'s own pre-scan, repeated
    for the second flag `main` must decide about before it can pick a routing branch.

    **Repaired, 2026-08-20, from a review of `4aeba88`.** `prescan_command_name` answers "which
    command was named", not "was help asked for" — it drops every `-`-prefixed token on the way
    to that answer, so `argv = ["--help"]` reduced to no tokens at all and was indistinguishable
    from a bare `weft`, which task 3.4's own rule (`docs/03-cli.md` -> *Two modes, one
    implementation*) routes to the REPL. `-h`/`--help` never reached `build_parser`'s generated
    help. This function does not change `prescan_command_name` — that function's own job (guess
    the command name, to decide `_PIN_DIAGNOSTIC_COMMANDS`' `strict_pins`) is unaffected by
    whether help was also asked for — it gives `main` a second, independent fact to route on,
    the same shape `wants_version` already established: a throwaway, `add_help=False`,
    `parse_known_args` mini-parser that tolerates whatever else is on the command line and never
    touches `weft_kernel.discovery`. Unlike `wants_version`, this fact does *not* let `main`
    skip discovery — `docs/02-extension-model.md` §2's own paragraph is explicit that `weft
    --help` needs the registry, deliberately, so the command list cannot drift from what is
    installed; it only decides which branch runs *after* the registry-driven parser already
    exists: `parser.parse_args(argv)`, whose own `-h`/`--help` action (`add_help=True`, the
    parser's default) prints the generated help and calls `sys.exit(0)` before `argparse`'s
    required-subparsers check ever runs — the same convention every argparse-based CLI already
    uses for a help request, distinct from `2`, its convention for a genuine usage error.
    """
    mini = argparse.ArgumentParser(add_help=False)
    mini.add_argument("-h", "--help", action="store_true")
    known, _ = mini.parse_known_args(argv)
    return cast(bool, known.help)


def global_output_flags(argv: list[str]) -> tuple[bool, bool]:
    """`(--json present, --quiet present)` — task 3.6's own pre-scan, on `wants_version`'s
    exact pattern: a throwaway, `parse_known_args` mini-parser that never touches
    `weft_kernel.discovery`.

    **Why this cannot wait for the real, registry-driven parser.** `docs/03-cli.md` ->
    *Output* (G6): "the CLI registers a `TokenSink` implementation" — and `main` has to
    decide *which* one before `build_dependencies` runs, because the choice is carried on
    `Dependencies.token_sink`, not read back out of `argparse.Namespace` afterward. For a
    one-shot invocation that would still be reachable by declaring the flags on `build_
    parser`'s own top-level parser and reading `args.json`/`args.quiet` post-hoc — but a
    bare `weft` (task 3.4's REPL entry) never calls `parser.parse_args(argv)` at all, so a
    flag that only the real parser recognised would be invisible to `weft --json` with no
    following subcommand. This function is argv-only and unconditional in both modes for
    exactly that reason — the same one `wants_version` is unconditional for `--version`.

    **Declared a second time, on `build_parser`'s own top-level parser, deliberately.**
    `wants_version` already establishes the precedent this follows: `--version` is a mini-
    parser flag *and* a real one, because a one-shot invocation's dispatch parse
    (`weft_cli.cli.main`'s `parser.parse_args(argv)`) still has to recognise every token in
    `argv` or fail with "unrecognized arguments" — this module never strips a flag out of
    `argv` before that second parse runs. `--json`/`--quiet` therefore have to precede the
    subcommand name (`weft --json ask ...`, never `weft ask --json ...`) for the identical
    reason task 3.3's own module docstring gives for `--yes` sitting on the *opposite* side
    of the subcommand: a flag declared on both the top-level parser and a leaf subparser
    would have the leaf's own default silently overwrite it once `argparse`'s
    `_SubParsersAction` copies the leaf namespace onto the shared one — `--json`/`--quiet`
    are genuinely top-level-only (they are not a per-command choice the way `--yes` is), so
    the leaf never declares them at all and the trap does not apply.

    Mutually exclusive, checked here rather than left for the real parser to catch first:
    a caller asking for a machine-readable stream and no output in the same breath has
    made a mistake worth naming before any discovery runs, not part way through it.
    """
    mini = argparse.ArgumentParser(add_help=False)
    group = mini.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true")
    group.add_argument("--quiet", action="store_true")
    known, _ = mini.parse_known_args(argv)
    return cast(bool, known.json), cast(bool, known.quiet)


def token_sink_for(*, json: bool, quiet: bool) -> TokenSink:
    """`global_output_flags`'s answer, turned into the sink `Dependencies.token_sink` carries.

    `json` and `quiet` cannot both be `True` — `global_output_flags`'s own mutually
    exclusive group already refuses that combination with a usage error before this
    function is ever called, so it is not re-checked here.
    """
    if json:
        return JsonSink()
    if quiet:
        return NullSink()
    return PrintingSink()


def prescan_command_name(argv: list[str]) -> str | None:
    """The first one or two non-flag tokens in `argv`, joined — see the module docstring's
    second paragraph. `None` when `argv` names no command at all (bare `weft`, or only flags).
    """
    tokens = [token for token in argv if not token.startswith("-")]
    if not tokens:
        return None
    if tokens[0] == "plugins" and len(tokens) > 1:
        return f"plugins {tokens[1]}"
    return tokens[0]


def build_parser(registry: Registry) -> argparse.ArgumentParser:
    """The argument grammar for every `Command` `registry` has registered.

    `docs/03-cli.md` → *Plugin-contributed commands*: "Core has no list of commands to edit.
    The help text is generated from the registry." Walks `registry.names_for(Command)`,
    grouping multi-word names (`"plugins doctor"`) into nested subparsers by their shared first
    token — the same namespacing convention `docs/03-cli.md`'s own `weft graph build` example
    uses — so a pack registering `Command` under any depth of dotted-space name gets exactly
    the subcommand tree its own registered names describe, with no second declaration of shape.

    **`--json`/`--quiet`, task 3.6 — declared here too, on `--version`'s own precedent.**
    `global_output_flags` already decided which sink `main` built, before this parser or the
    registry it walks even exist; these two are declared here as well purely so a one-shot
    invocation's real dispatch parse (`parser.parse_args(argv)`) recognises them instead of
    failing with "unrecognized arguments", and so `weft --help` documents them. Neither is
    read back off the parsed `argparse.Namespace` anywhere — `main` already knows the answer.
    """
    parser = argparse.ArgumentParser(prog="weft", description="Weft — a microkernel RAG engine.")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        help=(
            "swap the token sink for one that writes newline-delimited events "
            "(docs/03-cli.md -> Output). Before the subcommand: `weft --json ask ...`."
        ),
    )
    output_group.add_argument(
        "--quiet",
        action="store_true",
        help=(
            "swap the token sink for a no-op — suppresses streamed progress, keeps the "
            "result (docs/03-cli.md -> Output). Before the subcommand, like --json."
        ),
    )
    _add_command_level(parser, sorted(registry.names_for(Command)), registry=registry, depth=0)
    return parser


def _add_command_level(
    parser: argparse.ArgumentParser,
    names: list[str],
    *,
    registry: Registry,
    depth: int,
) -> None:
    """One level of the namespaced-name tree `names` describes, walked recursively.

    `names` are already-registered `Command` names sharing the same prefix through `depth`
    tokens — the top-level call passes every registered name; a recursive call passes only the
    names one group ("plugins ...") shares. A name with exactly `depth + 1` tokens and no
    sibling with more is a leaf: one subparser, its arguments generated from that command's own
    `args_model` (`weft_cli.argparse_gen`). A head with children instead becomes an intermediate
    subparser that recurses one token deeper — arbitrarily, so a pack naming `"graph entity
    delete"` gets a three-level tree with no extra code here.
    """
    if not names:
        return
    subparsers = parser.add_subparsers(
        dest=f"_weft_level_{depth}", required=True, metavar="command"
    )
    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(name.split(" ")[depth], []).append(name)

    for head in sorted(groups):
        members = groups[head]
        leaf = next((member for member in members if len(member.split(" ")) == depth + 1), None)
        children = [member for member in members if len(member.split(" ")) > depth + 1]
        if leaf is not None and not children:
            factory = unwrap_factory(registry.entry(Command, leaf).factory)
            # `unwrap_factory` answers `object` — a registered factory is ordinarily the
            # plugin class itself, sometimes a `functools.partial` binding pack settings
            # ahead of it (see that function's own docstring) — so `help`/`args_model` are
            # read the same defensive way `weft_cli.run_services._needs_store_of` reads a
            # declaration off an unwrapped factory: `getattr` with a default, then a cast,
            # never a bare attribute access pyright could statically resolve on `object`.
            help_text = cast(str, getattr(factory, "help", ""))
            sub = subparsers.add_parser(head, help=help_text, description=help_text)
            sub.set_defaults(**{COMMAND_NAME_ATTR: leaf})
            args_model = cast("type[BaseModel]", getattr(factory, "args_model", _EmptyArgs))
            add_model_arguments(sub, args_model)
            # `--yes` a second time, so `weft <command> ... --yes` parses identically to
            # `weft --yes <command> ...` — see the module docstring's task-3.3 paragraph.
            sub.add_argument("--yes", action="store_true", help=_YES_HELP)
        else:
            sub = subparsers.add_parser(head, help=f"'{head}' subcommands")
            _add_command_level(sub, members, registry=registry, depth=depth + 1)


def _context() -> Context:
    """One `Context` per invocation. Phase 0 has no multi-tenancy surface, so `tenant_id`
    is a fixed default rather than a flag — see `docs/01-high-level-plan.md` → *The least-
    architecture check*, "carry a tenant identifier... build no isolation machinery until
    it is real."
    """
    return Context(
        tenant_id="default", run_id=str(uuid.uuid4()), trace_id=str(uuid.uuid4()), locale="en"
    )


class _EmissionTrackingSink:
    """Wraps a real `TokenSink` for the duration of one `run_command` call, and remembers
    whether `emit` was ever called — `run_command`'s own repaired `finally` block reads
    `.emitted` to decide whether a caught failure is a genuine stream error, without
    `weft_llm.contract.TokenSink` growing a method every implementation would need, and
    without every non-streaming `Command` remembering to report it themselves. See
    `run_command`'s own docstring, "Repaired, 2026-08-20", for the bug this closes.

    Structural, not a `TokenSink` subclass — it satisfies the Protocol the identical way
    `PrintingSink`/`JsonSink` already do, by shape alone. `close` forwards, for full Protocol
    compliance, but nothing in this tree ever calls it on this wrapper: `run_command`'s own
    `finally` closes `deps.token_sink` — the real one, not this wrapper — exactly once, with
    the reason `.emitted` helped it decide (see that function's own docstring, "Repaired,
    2026-08-20"), and no `Command.run` anywhere in this repository closes its own sink.
    """

    def __init__(self, sink: TokenSink) -> None:
        self._sink = sink
        self.emitted = False

    async def emit(self, chunk: TokenChunk) -> None:
        self.emitted = True
        await self._sink.emit(chunk)

    async def close(self, *, reason: str | None = None) -> None:
        await self._sink.close(reason=reason)


async def run_command(command_name: str, args: argparse.Namespace, deps: Dependencies) -> Rendered:
    """Resolve `command_name`, run it against `args`, and render whatever comes back.

    Replaces every retired `handle_*` function: build one `Context`, hand it this run's
    `Dependencies` (`weft_cli.commands`'s own module docstring explains why `ctx.services` is
    where a `Command` reaches them), run the plugin, and render the result. A `WeftError`
    raised anywhere in that call — a `CommandRefusalError` from a policy check, or anything
    `run_index`/`run_ask`/`run_routed_ask` themselves raise — is caught once, here, exactly
    where `dispatch` used to catch it per handler. Task **3.4** is what makes this the REPL's
    own dispatch too, unchanged: `weft_cli.repl.run_repl` calls this exact function once per
    turn — "the same commands with a different renderer", per `docs/03-cli.md` → *Two modes,
    one implementation* — so this function has no reason to know or care which mode called it.

    **Runs through `weft_kernel.seam.wrap` again, with the blocking-call guard turned off —
    task 3.4's resolution of the open item task 3.2 left (`.phase3-design.md` O1).** 3.2 tried
    running `Command.run` through `wrap` unchanged, on `Prompt.render`'s own precedent, and
    reverted it: `weft index`'s own orchestration — `weft_extract.accept.present_suffixes`/
    `discover_source_docs`, plain synchronous filesystem walks — tripped the blocking-call
    detector, which exists to catch a `Stage` starving an event loop *other stages share*. A
    `Command` shares no loop with a sibling — it is CLI orchestration invoked once per
    invocation or once per REPL turn, the only thing running — so the guard was a false
    positive for it, not a caught defect; but the revert as shipped also cost every `Command`
    invocation its span and its error attribution, which is the rule-an-author-must-remember
    shape CLAUDE.md refuses for a cross-cutting concern. The fix is not a second, hand-written
    attribution wrapper living beside `weft_kernel.seam` (a second implementation of the same
    concern, free to drift from it) — it is `weft_kernel.seam.wrap`'s own new
    `guard_blocking_calls` keyword, which this is the one caller in the whole tree that passes
    `False`. Spans, attribution and `Produced` post-processing run exactly as they do for a
    `Stage`; `CommandResult` is not a `Node` (or a list/tuple of them), so `_strip_transient`
    and the NUL sanitiser both pass it through untouched — a non-question for this contract,
    checked at `weft_kernel.seam` source rather than assumed. `entry.distribution` is the pack
    that registered `command_name`, the identical field `weft_prompts.registry.PromptRegistry`
    already reads for the same reason. **O2, resolved by task 3.6 (`.phase3-design.md` §4):**
    the argument above ("nothing else shares this loop with a `Command`'s own run") was flagged
    as needing re-examination once streaming shipped, because the REPL keeps reading a next
    line on the same loop a stream runs on. It still holds, and not by accident: the call below
    is `await sealed_run(...)` — a single await that only returns once the whole command,
    including any token stream inside it, has finished — so `weft_cli.repl.run_repl`'s own
    `read_line()` is provably never reached until a stream from the *previous* turn is
    completely over (`tests/unit/weft_cli/test_repl.py::
    test_repl_does_not_read_the_next_line_while_a_stream_is_in_flight` drives this with a
    provider that streams for real elapsed time and asserts `read_line` never observes it in
    flight, rather than asserting the code shape by inspection alone). `weft_extract.accept`'s
    synchronous walk needs no change for the identical reason: it and a token stream can never
    be the same `Command.run` call, and no two `Command.run` calls ever overlap on this loop —
    Weft's whole execution model keeps exactly one batch in flight (`docs/01-high-level-plan.md`
    → *Colour*) and makes exactly one `asyncio.run` call in the entire tree. **What would make
    this break**, named rather than left implicit: a future task that lets the REPL do anything
    else while a stream is in flight — `asyncio.create_task`-ing a stream so the loop can poll
    for `Ctrl-C` or accept a next line concurrently, say. Nothing built here does that.

    **Task 3.3's fourth job**: `weft_cli.confirm.gate` runs immediately before the wrapped
    `run`, for every registered `Command` alike — see that module's own docstring for the whole
    design. A refusal there raises the identical `CommandRefusalError` `require_active`/
    `require_plugin` already raise, so it is caught by the same `except WeftError` below with
    no second branch.

    **Task 3.6's fifth job: closing the run's own `TokenSink` exactly once, always.**
    `weft_llm.contract.TokenSink`'s own docstring: "one per run, and never absent" — "run" here
    is one `run_command` call, one-shot or one REPL turn alike, so this is the one place to
    close it, rather than a rule every streaming `Command` author has to remember (CLAUDE.md:
    cross-cutting concerns live at the seam). `close(reason=None)` on a clean return;
    `close(reason=...)` naming what happened otherwise — a caught `WeftError`'s own message, or,
    for anything else (a plain bug, `CancelledError`) that escapes uncaught below, a generic
    "command did not complete" rather than fabricating a cause this function does not know. The
    `finally` below runs on every exit from the `try`, `CancelledError` included, and does not
    catch it — it closes the sink and lets propagation continue untouched (G6): closing a
    resource in `finally` during cancellation is ordinary asyncio cleanup, not a second
    exception swallowing the first. This is also `.phase3-design.md` §2.3(b)'s own answer for
    how a `--json` consumer tells an error from a clean end: `weft_cli.sinks.JsonSink.close`
    emits a structurally different event for `reason=None` versus any other `reason`, never a
    plain-text difference a consumer would have to string-match.

    **Repaired, 2026-08-20, from a review of 3.3/3.6/3.7's landed `f201e70`.** The `finally`
    above used to close the sink with `close_reason or "command did not complete"` whenever
    `succeeded` was `False`, with no check for whether anything had actually been streamed —
    so *any* failing command that never touches `TokenSink.emit` (which is every built-in but
    `weft_cli.commands.RouteCommand`: a `gate` refusal before `instance.run` even starts, or
    an ordinary `WeftError` a non-streaming command's own `run()` raises, `weft init`'s
    `TargetAlreadyExistsError` included) closed the sink with that error's own message as
    `reason` — and `PrintingSink.close` printed it a second time, wrongly labelled `[stream
    error: ...]`, on top of the correct copy `render_refusal` already sends to stderr below.
    Re-running the reproduction that opened this review by hand (`weft init` in an empty
    directory, then again once `weft.toml` existed) is what showed the bug is not only
    `gate`'s own refusal path — the *second* `weft init`, refused by `TargetAlreadyExistsError`
    from inside `InitCommand.run` itself, printed the identical double, proving a fix scoped to
    `gate` alone would have shipped the same defect back one raise site over.

    The corrected rule: `reason` is real only when `TokenSink.emit` was actually called during
    this run — `_EmissionTrackingSink` below wraps `deps.token_sink` for exactly the duration of
    `sealed_run` and remembers whether that happened, without either `TokenSink` (`weft-llm`'s
    own contract) growing a method every implementation would need, or every non-streaming
    `Command` author remembering to report it themselves (CLAUDE.md: cross-cutting concerns
    live at the registration seam, never a rule an author must remember). The *real* sink —
    never the wrapper — is what `finally` closes, exactly once, on every exit, unchanged; only
    the *reason* passed to it changed. This does **not** touch `weft_cli.commands.RouteCommand`'s
    own separate double-print of a *successful* streamed answer (flagged in task 3.6's own
    report, assigned to task 3.11): that bug lives entirely in the `succeeded`-branch return
    value `_render_route` builds, on a `succeeded=True` exit this repair's `reason` branching
    already forced to `None` before and after — see `docs/build-ledger.md`'s dated repair
    paragraph for the boundary stated explicitly.

    **Fixed by task 3.11**, on the identical shape this repair already established for the
    `finally` branch above: a second fact read off the *real* sink, `wrote_anything`
    (`weft_cli.sinks.PrintingSink`/`JsonSink`'s own new attribute, `weft_cli.render`'s own
    module docstring has the full argument), threaded into `render_outcome`'s new `streamed`
    keyword below rather than a second, parallel double-print fix reusing `tracked_sink.
    emitted` — which this function's own `_EmissionTrackingSink` deliberately does *not*
    track per-role, and is therefore the wrong fact for "did the generated text specifically
    already reach a reader" (a router's own `role="route"` scoring call would set it long
    before generation ever starts). `RouteCommand` itself is retired into `AskCommand` in the
    same task — see `weft_cli.commands`'s own module docstring.

    **Task 5.2d's own sixth job: deciding whether a caught `WeftError` reaches `render_refusal`
    as prose or as `weft_cli.error_envelope.ErrorEnvelope`.** `deps.token_sink` — the real sink
    this function was handed as a parameter, never `tracked_sink` above, whose whole purpose is
    the `finally` block's own close-`reason` decision and which carries no opinion about output
    format — decides it: `isinstance(deps.token_sink, JsonSink)` is the identical global `--json`
    flag `docs/03-cli.md` -> *Output* already used to build that sink in the first place, so
    there is no second, independently-set flag for the two to disagree about. See `render_
    refusal`'s own docstring for what the envelope carries and why.
    """
    # Local imports — see the module docstring's FF8(b) paragraph and the `TYPE_CHECKING`
    # import above: `run_command` is only ever reached for a command that already needed
    # discovery, so this costs nothing beyond a `sys.modules` lookup by the time it runs.
    from weft_cli.confirm import gate
    from weft_cli.render import render_outcome, render_refusal

    ctx = _context()
    tracked_sink = _EmissionTrackingSink(deps.token_sink)
    # `dataclasses.replace`, never a mutation of the caller's own `deps` (frozen, and — across
    # REPL turns — shared): a `Command` that reads `ctx.require(Dependencies).token_sink` sees
    # the tracking wrapper for this run only; `deps.token_sink` itself, the one `finally`
    # closes below, is untouched.
    ctx.services.add(Dependencies, dataclasses.replace(deps, token_sink=tracked_sink))

    entry = deps.registry.entry(Command, command_name)
    instance = cast(Command, entry.factory(None))
    args_model = instance.args_model
    payload = {field: getattr(args, field) for field in args_model.model_fields}
    args_instance = args_model(**payload)
    yes = cast(bool, getattr(args, "yes", False))

    sealed_run: Callable[[BaseModel, Context], Awaitable[Outcome[CommandResult]]] = wrap(
        instance.run,
        distribution=entry.distribution,
        contract="Command",
        plugin=command_name,
        stage=f"command:{command_name}",
        guard_blocking_calls=False,
    )

    succeeded = False
    failure_reason: str | None = None
    try:
        gate(instance, command_name, args_instance, yes=yes, policy=deps.permissions, ctx=ctx)
        outcome = await sealed_run(args_instance, ctx)
        succeeded = True
    except WeftError as exc:
        failure_reason = str(exc)
        # Task 5.2d — see this function's own docstring, sixth job.
        return render_refusal(exc, as_json=isinstance(deps.token_sink, JsonSink))
    finally:
        if succeeded or not tracked_sink.emitted:
            reason = None
        else:
            reason = failure_reason or "command did not complete"
        await deps.token_sink.close(reason=reason)
    # Task **3.11**'s own fix for `weft route`'s inherited double-print: `deps.token_sink` is
    # the *real* sink here, never `tracked_sink` (which tracks emission for the close-reason
    # decision above and is deliberately role-blind — see that class's own docstring) —
    # `wrote_anything` is `PrintingSink`/`JsonSink`'s own fact about whether a chunk a reader
    # would actually see was ever written, `getattr`-read with a `False` default so `NullSink`
    # (which carries no such attribute) always answers "nothing streamed", the correct reading
    # for `--quiet`. `weft_cli.render._render_ask` is the one renderer that reads it.
    return render_outcome(outcome, streamed=getattr(deps.token_sink, "wrote_anything", False))


class OwnDistributionError(WeftError):
    """Nothing installed, or more than one thing installed, provides the `weft` command.

    `weft --version` is the one command that has to answer without touching a registry
    (fitness function 8(b)), so it cannot ask discovery where it came from — but it must not
    assert an answer either. Both halves are real states: no claimant means `weft_cli` is on
    `sys.path` with no installed metadata behind it (a bare `PYTHONPATH`, a half-built
    wheel), and two claimants means two distributions both install a `weft` script pointing
    here, which is an environment that will misbehave far past a version string. Neither is
    guessed at.
    """


def own_distribution() -> str:
    """Which installed distribution provides the `weft` command, asked rather than asserted.

    This was `_DISTRIBUTION = "weft-cli"` fed straight to `metadata.version`, which was true
    right up until something repackaged: `weft-rag` bundles `weft_cli` along with eleven
    other packs, and inside that wheel there is no `weft-cli` distribution at all — so
    `weft --version`, the first thing anyone runs, would have died with
    `PackageNotFoundError`.

    Derived from the **`console_scripts` entry point that points at this module**, which is
    exactly the thing that put `weft` on the reader's PATH, so the version reported is the
    version of what they actually ran. `importlib.metadata.packages_distributions()` is the
    obvious alternative and is wrong here: it maps import packages to distributions by reading
    installed file records, and an editable install records only a `.pth` file — so it answers
    `None` for `weft_cli` in this repository's own development environment, which is where
    `weft --version` is run most often. Entry-point metadata is written for an editable
    install and a wheel alike.

    Reading metadata imports no pack, so fitness function 8(b) is unaffected.

    Ambiguity is refused, never resolved by taking the first: see `OwnDistributionError`.
    """
    claimants = sorted(
        {
            entry_point.dist.name
            for entry_point in metadata.entry_points(group="console_scripts")
            if entry_point.module == _CONSOLE_SCRIPT_MODULE and entry_point.dist is not None
        }
    )
    if len(claimants) == 1:
        return claimants[0]
    if not claimants:
        raise OwnDistributionError(
            f"weft cannot report its version: no installed distribution declares a console "
            f"script pointing at '{_CONSOLE_SCRIPT_MODULE}'. Install weft-rag (or weft-cli) "
            f"rather than putting its source directory on PYTHONPATH."
        )
    named = ", ".join(f"'{name}'" for name in claimants)
    raise OwnDistributionError(
        f"weft cannot report its version: {len(claimants)} installed distributions each "
        f"provide a console script pointing at '{_CONSOLE_SCRIPT_MODULE}' ({named}). "
        f"Uninstall all but one."
    )


def own_version() -> str:
    """The installed version of whichever distribution provides the `weft` command."""
    return metadata.version(own_distribution())


def main() -> None:
    """The one entry point. The one `asyncio.run`. Fitness function 7(a)'s subject.

    **Task 3.4: a bare `weft` — no command named — enters the REPL instead of parsing.**
    `wants_version` above still short-circuits *first*, so `weft --version` never reaches
    discovery — the property FF8(b) requires stays true regardless of what follows. Discovery
    itself is needed either way, exactly as `weft --help` already needs it
    (`docs/02-extension-model.md` §2): `build_dependencies`/`build_parser` run unconditionally,
    once, before either branch below — a REPL turn resolves commands against the identical
    registry a one-shot invocation would, so there is no world where the REPL sees a different
    surface than `--help` does. `weft_cli.repl` is imported locally, after that discovery has
    already happened, on the same FF8(b) discipline `run_command`'s own local imports use — see
    this function's `except WeftError` branch just below for why `build_parser` has to be in the
    same `try` as `build_dependencies`.

    **Task 3.6: which `TokenSink` this run gets is decided here, before discovery — and REPL
    entry is "no command named", not "empty `argv`", because of it.** `global_output_flags`/
    `token_sink_for` — see their own docstrings — turn `--json`/`--quiet` into a real sink
    *before* `build_dependencies` runs, so it can be carried on `Dependencies.token_sink` from
    the moment `Dependencies` exists rather than patched on afterward. That only matters for
    the REPL branch if `weft --json` (flags, no subcommand) actually *reaches* it — under
    3.4's own `not argv` condition it would not: `argv = ["--json"]` is not empty, so it fell
    through to the one-shot dispatch parse and failed with `argparse`'s own "the following
    arguments are required" (`add_subparsers(required=True)`), a confusing way to be told
    "there is no command here yet, so this must be the REPL." `command_hint is None` —
    `prescan_command_name` already strips every `-`-prefixed token before deciding whether a
    command was named — is the same REPL-entry test 3.4 wrote, corrected to say what it always
    meant: `weft --json` and a bare `weft` are both "no command", and both now enter the REPL
    with the sink `--json` asked for already selected, exactly as `weft --json route "..."`
    selects it for a one-shot invocation.

    **Repaired, 2026-08-20, from a review of `4aeba88`: a lone `-h`/`--help` used to enter the
    REPL instead of printing help.** `command_hint is None` alone used to be the whole REPL-entry
    test — correct for a bare `weft` and for `weft --json`/`weft --quiet` (`global_output_flags`'s
    own two flags carry no command either), wrong for `weft --help`, whose only token
    `prescan_command_name` strips on the way to deciding a command name, exactly as it strips
    `--json`/`--quiet`/`--yes`. The REPL-entry test below is now `command_hint is None and not
    wants_help(argv)` — `wants_help` is the new fact, decided the same argv-only,
    discovery-free way `wants_version` already is. Discovery itself is unaffected: `weft --help`
    still needs it, deliberately (`docs/02-extension-model.md` §2, the paragraph two above), so
    `build_dependencies`/`build_parser` still run unconditionally before this check, exactly as
    they did before this repair — only the routing decision made from their result changed. Once
    routed away from the REPL, `weft --help`/`weft -h` falls through to the same
    `parser.parse_args(argv)` a named command already used: `argparse`'s own `-h`/`--help` action
    (`build_parser`'s parser keeps `add_help=True`, its default) fires during parsing, before the
    required-subparsers check, prints the registry-generated help and calls `sys.exit(0)` —
    argparse's own convention for a help request, distinct from `2`, its convention for a usage
    error. No second help-printing path was written; `weft <name> --help` already reached this
    exact mechanism through the identical parser, unchanged by this repair.
    """
    argv = sys.argv[1:]
    if wants_version(argv):
        try:
            print(f"weft {own_version()}")
        except OwnDistributionError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(int(ExitCode.OPERATION_FAILED))
        sys.exit(int(ExitCode.SUCCESS))

    command_hint = prescan_command_name(argv)
    strict_pins = command_hint not in _PIN_DIAGNOSTIC_COMMANDS
    json_flag, quiet_flag = global_output_flags(argv)
    sink = token_sink_for(json=json_flag, quiet=quiet_flag)
    try:
        deps = build_dependencies(strict_pins=strict_pins, token_sink=sink)
        parser = build_parser(deps.registry)
    except WeftError as exc:
        # Discovery itself failed to build a registry at all, before a single Command is even
        # known to exist — `weft.toml` is not valid TOML, `[packs] allow`/`[plugins]` is
        # malformed (`weft_cli.registry_bootstrap.build_dependencies`'s own docstring) — or
        # discovery succeeded but a registered `Command`'s own `args_model` has a field type
        # `weft_cli.argparse_gen` cannot turn into an argument (`UnsupportedArgumentTypeError`,
        # a pack author's bug, never a user's). None of these is a policy refusal any specific
        # distribution earned, so all three are resolution failure (4) — the fixed code
        # `dispatch` always returned here, never `weft_cli.exit_codes.exit_code_for`'s
        # per-exception mapping, which is for a *chosen* command's own run, not for building
        # the surface a command is chosen from.
        #
        # Task 5.2d: no `Command` was ever chosen here, so `weft_cli.render.render_refusal`'s
        # own `CommandRefusalError` branch could never apply — this site builds the identical
        # envelope directly, from `json_flag` (already known, computed above `build_
        # dependencies` itself ran) rather than a sink that never got the chance to exist.
        if json_flag:
            from weft_cli.error_envelope import build_error_envelope

            envelope = build_error_envelope(exc, exit_code=ExitCode.RESOLUTION_FAILED)
            print(envelope.model_dump_json())
        else:
            print(str(exc), file=sys.stderr)
        sys.exit(int(ExitCode.RESOLUTION_FAILED))

    if command_hint is None and not wants_help(argv):
        from weft_cli.repl import run_repl

        try:
            repl_exit_code = asyncio.run(run_repl(deps, parser))
        except Exception as exc:  # noqa: BLE001 — see `_report_unexpected`
            _report_unexpected("<repl>", exc)
            sys.exit(int(ExitCode.OPERATION_FAILED))
        sys.exit(int(repl_exit_code))

    args = parser.parse_args(argv)
    command_name = cast(str, getattr(args, COMMAND_NAME_ATTR))

    try:
        rendered = asyncio.run(run_command(command_name, args, deps))
    except Exception as exc:  # noqa: BLE001 — see `_report_unexpected`; this is the last resort
        _report_unexpected(command_name, exc)
        sys.exit(int(ExitCode.OPERATION_FAILED))

    if rendered.stdout is not None:
        print(rendered.stdout)
    if rendered.stderr is not None:
        print(rendered.stderr, file=sys.stderr)
    sys.exit(int(rendered.exit_code))


def _report_unexpected(command_name: str, exc: Exception) -> None:
    """Render an exception no handler translated, loudly and without a traceback.

    **Why this exists.** `weft index` and `weft ask` failed differently against the same
    unreachable database: `index` printed one line and exited 1, because every stage runs
    through the registration seam, which attributes the failure. `ask` resolves its store
    directly — there is no stage to attribute — so a `psycopg.OperationalError` travelled all
    the way out of `asyncio.run` and printed twelve lines of traceback at a user whose actual
    mistake was a typo in a port number. `docs/03-cli.md` -> *Output* offers no third
    behaviour for "the library raised something weft has no translation for".

    **Why it catches `Exception` rather than a list.** A driving adapter's job is that the
    process never speaks in stack traces, and the set of exception types a *pack* can raise is
    unbounded by construction — that is what the plugin model means. Enumerating them here
    would be a list that goes stale the first time someone installs a pack this repository has
    never seen. This is the opposite of a silent fallback: nothing is swallowed, the type and
    message are printed, and the exit code is non-zero.

    `BaseException` is deliberately not caught, so `CancelledError` propagates untouched (G6)
    and `KeyboardInterrupt` still ends the process the way a user expects.

    `WEFT_TRACEBACK=1` re-raises instead, because "no traceback" is right for a user and wrong
    for whoever has to fix it.
    """
    if os.environ.get("WEFT_TRACEBACK") == "1":
        raise exc

    print(f"weft {command_name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    print(
        "This is an error weft did not translate — the message above comes from the library "
        "that raised it. Re-run with WEFT_TRACEBACK=1 for the full traceback.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
