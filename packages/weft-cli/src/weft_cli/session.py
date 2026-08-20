"""What an interactive session carries across turns — the data half of task **3.5**.

`docs/03-cli.md` -> *In-session commands*: "The session carries state a one-shot invocation
does not: the active pipeline, the collection, conversation history, and the last run's trace.
That state is explicit and inspectable... because implicit session state is how a tool starts
behaving differently for two people running the same command." Three sentences, and the third
is the one this task is actually held to: nothing `weft_cli.repl` applies to a run may be true
of the session and absent from what printing the session shows. This module is the printable
half — `weft_cli.repl`'s own `_session_text`/`_trace_text` are the formatting half, on the
identical formatting/data split `weft_cli.render` already draws for a `Command`'s own result.

**A frozen model, replaced wholesale, never mutated in place.** `SessionState` follows the
idiom `weft_cli.confirm`/`weft_kernel.discovery`'s own merge functions already use
(`base.model_copy(update=...)`, `weft_kernel.registry_bootstrap`'s module docstring names it
directly): `with_active_pipeline`, `with_turn_recorded` and `cleared` each take a `SessionState`
and return a new one, so `weft_cli.repl.run_repl` holds exactly one local variable, reassigned
each turn — the same shape a `Context` or a `PermissionPolicy` already takes, applied to a value
that changes turn to turn instead of once per run.

**Two of `03`'s four are built here, and two are deferred, argued rather than defaulted past.**

- **The active pipeline** — held and printed as a bare name, with nothing behind it: no
  `weft pipeline` command surface exists yet to validate it against (task **3.7**'s own), and
  `docs/03-cli.md`'s own task brief for this one sanctions exactly this shape: hold and print
  the name, do not build resolution. `/pipeline <name>` sets it; `/pipeline` alone shows it.
- **The last run's trace** — one `TurnTrace`, replaced wholesale on every command that actually
  ran through `weft_cli.cli.run_command` (a bare command, or `/plugins`' own alias for one) —
  never a growing log. `/trace` shows it, `/clear` resets it.
- **Conversation history — deferred, not built.** `docs/03-cli.md` names it as a fourth,
  distinct thing from "the last run's trace" — a transcript a follow-up question could read
  back, the shape `_run_chat_loop` in the reference's `generation/chat.py:353` gestures at with a
  `chat_history` parameter it always passes `[]` for, a comment on the same line stating it is
  stateless (`.phase3-design.md` §2.5, verified at source). No contract in this repository reads
  a prior turn back into a later one: `weft_cli.commands.AskArgs` takes no history field, and
  neither `weft_llm.contract.LLMProvider` nor `weft_prompts` accepts one from a CLI caller
  today. A transcript this module accumulated for display only, with nothing downstream ever
  reading it back into a run, would be `_run_chat_loop`'s own failure shape restated rather
  than avoided: state that *looks* like it changes what happens next and does not. Building it
  waits for whichever task first gives `weft ask` something to read it for.
- **The collection — deferred, and for a sharper reason: nothing names one yet.** Unlike the
  active pipeline, no command in this repository accepts a collection argument to hold a
  session's choice of — `weft_cli.commands.IndexArgs`/`AskArgs` name no `--collection` flag, and
  `[services] store` selects *which store plugin* runs, never *which named collection inside
  it* (`weft-qdrant`'s own `collection` is a fixed `[packs.weft-qdrant]` setting, not a runtime
  choice). `docs/03-cli.md`'s *Permissions* table names "collection" only in prose describing a
  future `overwrite`/`destroy` prompt (`weft_cli.confirm`'s own module docstring, design
  question 2: no command is `overwrite`/`destroy`-class yet either). A session field with no
  setter and no reader would be exactly the same dead-state shape conversation history above is
  refused for, one step further out: there is not even a command to hold state *for* yet.

**`/config` was going to print this, and does not — `docs/03-cli.md` is corrected in the same
commit this module ships in.** `03` -> *In-session commands* named `/config` as the command
that prints session state, written before task **3.4** deferred `/config` itself to task
**3.7** (`weft config get/set`, the *project's* `weft.toml`-backed configuration). Those are two
different things sharing one name by accident of when each sentence was written: `weft.toml` is
read once, at startup, and does not change turn to turn; a session's own state changes every
turn a `/pipeline` or a run mutates it. Folding them into one `/config` would mean either
building part of 3.7's command surface early (a `weft config`-style project-value reader, to
have something to distinguish the session's values *from*) or shipping `/config` half-true —
printing session state alone under a name `03` already promised project configuration to.
Neither is honest, so this task gives the session its own command, `/session`, and `03` is
edited in the same commit to name it instead of `/config`. When task 3.7 lands, `/config` prints
`weft.toml`'s effective values; `/session` keeps printing the session's own — two different
questions, two different answers, and neither pretends to be the other.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from weft_cli.exit_codes import ExitCode


class TurnTrace(BaseModel):
    """What the session's last command actually did — `/trace`'s whole answer.

    `line` is the literal text typed at the prompt (or, for `/plugins`' own alias, the
    equivalent `"plugins list"` it constructs) — the least lossy record of what ran, cheaper
    and more honest than reconstructing a parsed-argument dict a second time from data
    `weft_cli.cli.run_command` already validated and has since discarded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The resolved registry name the line dispatched to — `"plugins list"`, not just `"list"`.
    command_name: str

    #: The verbatim prompt input that produced this run.
    line: str

    #: `weft_cli.cli.run_command`'s own `Rendered.exit_code` for this run.
    exit_code: ExitCode


class SessionState(BaseModel):
    """Every value `weft_cli.repl.run_repl` carries from one turn to the next.

    See the module docstring for which of `docs/03-cli.md`'s four this holds (two) and which
    it deliberately does not (two, each argued there). `active_pipeline` is a bare, unvalidated
    name; `last_trace` is `None` until a command has actually run this session.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    active_pipeline: str | None = None
    last_trace: TurnTrace | None = None


def with_active_pipeline(state: SessionState, name: str) -> SessionState:
    """`state`, with `active_pipeline` set to `name` — `/pipeline <name>`'s whole effect."""
    return state.model_copy(update={"active_pipeline": name})


def with_turn_recorded(
    state: SessionState, *, command_name: str, line: str, exit_code: ExitCode
) -> SessionState:
    """`state`, with `last_trace` replaced by this turn's own — never appended to a log.

    Called only for a line that actually reached `weft_cli.cli.run_command` — a bare command,
    or `/plugins`' own alias — never for a slash command that only inspects or changes the
    session itself (`/help`, `/pipeline`, `/trace`, `/clear`, `/session`), which is what keeps
    "the last run's trace" meaning a *run*, not a turn at this prompt.
    """
    trace = TurnTrace(command_name=command_name, line=line, exit_code=exit_code)
    return state.model_copy(update={"last_trace": trace})


def cleared(state: SessionState) -> SessionState:
    """A blank session — `/clear`'s whole effect.

    `docs/03-cli.md` names `/clear` beside "conversation history", which this module does not
    build (see the module docstring). What a session actually holds today — the active pipeline
    and the last run's trace — is what `/clear` resets; the day conversation history is built,
    this is also where it is reset, so `/clear` needs no second meaning added later.
    """
    del state
    return SessionState()


__all__ = [
    "SessionState",
    "TurnTrace",
    "cleared",
    "with_active_pipeline",
    "with_turn_recorded",
]
