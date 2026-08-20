"""The invocation-seam gate for `overwrite`/`destroy`-class commands.

Task **3.3**: "a destructive operation with no TTY fails naming the flag that would permit it,
and never proceeds silently." `docs/03-cli.md` -> *Permissions*: "Non-interactive means
non-guessing. With no TTY, an `ask` operation fails with a message naming the flag that would
permit it. It never proceeds silently." `--yes` permits it for one invocation; per-class defaults
live in `weft.toml` (`weft_cli.permission_policy`, design question 4).

**Design question 1 — where the check goes, and why here.** `gate` is called from exactly one
place, `weft_cli.cli.run_command`, immediately before `instance.run(...)` — the identical seam
`weft_cli.commands.IndexCommand`/`AskCommand` already use for `require_active`/`require_plugin`,
generalised one level further out so it applies to *every* registered `Command`, not only the
five built-ins that call those two functions themselves. `permission_class` is already a mandatory
declaration (`weft_command.contract.Command.required_declarations`), read here generically off
the constructed instance — a pack's `overwrite`/`destroy` command is refused with **no
cooperation from its author**: a plugin class that only declares `permission_class` and `run`,
never importing this module or anything like it, is refused exactly the same way `weft-cli`'s own
built-ins are — proven in `tests/unit/weft_cli/test_cli.py` against a hand-registered `Command`
that does nothing but declare the class.

**Design question 2 — the smaller, honest version, and why it stops here.** `docs/03-cli.md` also
asks for a prompt stating "what will be destroyed and how much of it — collection name and
document count." Naming a *count* means the command has already looked, which no generic seam can
do without either running part of the command early (indistinguishable from actually doing the
destructive thing) or a new `Command.describe_impact`-style contract method every registered
`Command` — built-in and stranger alike — would have to implement, since `required_declarations`
has no mechanism for "mandatory only for `overwrite`/`destroy`" without a kernel change this task's
own budget refuses (CLI work, zero kernel lines). With **no first-party command declaring
`overwrite` or `destroy` yet** (`weft_cli.commands`' own five are `write`/`read` only), forcing
that method onto every existing implementation, in this repository and out of it, today would be
churn for a need nothing yet has — so this task ships the honest floor instead: the command's own
registered name and its own already-validated, already-typed `args` (`model_dump()`), which *is*
more than "are you sure?" (a collection name passed as an argument shows up in it) without
inventing data the seam cannot truthfully have. A `describe_impact` contract addition is left to
whichever later task first ships a real `overwrite`/`destroy` command and needs the count —
recorded as an open item rather than pretended away.

**Design question 3 — how "no TTY" is detected, and how a test proves both branches.**
`is_interactive`/`read_confirmation` each wrap one `sys`/builtin call in a module-level name for
exactly one reason: `tests/unit/weft_cli/test_confirm.py` monkeypatches each name directly,
proving the no-TTY refusal, the TTY-confirmed path and the TTY-declined path without depending on
whether the process running the suite happens to be attached to a real terminal — which CI never
is, and a developer's own shell usually is, so a check that read `sys.stdin.isatty()` inline could
never prove the branch CI actually needs proven.

**The reference has nothing here** (`.phase3-design.md` §2.5): a whole-tree search of `a prior project` for
`typer.confirm`/`Confirm.ask`/any "are you sure" text returns zero matches, and its own most
destructive command, `rebuild --force`, runs immediately with no TTY check and no `--yes`
equivalent. This module has no scar to avoid inheriting, only a rule to build from `docs/03-cli.md`
directly.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, cast

from weft_cli.exit_codes import ExitCode
from weft_cli.permission_policy import PermissionAction, PermissionPolicy
from weft_command.permission import PermissionClass

if TYPE_CHECKING:
    from pydantic import BaseModel

# Module-level, not a local import inside `gate` — `weft_cli.confirm` is itself only ever
# imported locally, inside `weft_cli.cli.run_command` (see that module's own FF8(b) paragraph),
# so by the time this import runs, `weft --version`'s exemption has already been decided and
# nothing here can leak a pack import into it — the identical reasoning `weft_cli.render`'s own
# module-scope import of `weft_cli.commands` already relies on.
from weft_cli.commands import CommandRefusalError

#: The two classes `docs/03-cli.md` -> *Permissions* defaults to `ask` — `read`/`write` are
#: unconditionally `allow` and never reach this module's own decision at all.
_ASK_CLASSES = (PermissionClass.OVERWRITE, PermissionClass.DESTROY)


def _article(word: str) -> str:
    """ "a" or "an", by `word`'s own first letter.

    **Repair, 2026-08-20, from a review of task 3.7's `f201e70`.** Both messages below used
    to hardcode "is a {permission_class.value}-class command" unconditionally, which reads
    "is a overwrite-class command" — an article-agreement bug in the first message a
    no-TTY `weft init` ever prints (`docs/build-ledger.md` 3.3's own repair paragraph has the
    full report). `_ASK_CLASSES` is two values today (`overwrite`, `destroy`) and only the
    first needs "an", but computing the rule from the word itself, once, here, is what keeps
    a third value this module has to phrase a sentence about from needing a second place
    taught it — the identical "fix it once at the source" instinct `weft_kernel.registry.
    _require_declarations_present`'s own generalisation over `destroys` already used.
    """
    return "an" if word[:1].lower() in "aeiou" else "a"


def is_interactive() -> bool:
    """Whether stdin is a real terminal a confirmation prompt could read an answer from.

    See the module docstring's design-question-3 paragraph for why this is its own name
    rather than an inline `sys.stdin.isatty()` at the call site below.
    """
    return sys.stdin.isatty()


def read_confirmation(prompt: str) -> str:
    """`input(prompt)`, in its own name for the identical monkeypatch-ability reason, with one
    correction: `EOFError` — stdin running dry mid-prompt, a real if rare shape for a TTY that
    is attached but not actually being typed into — becomes an empty string, which `gate`'s own
    decline check already treats as "not confirmed", rather than an unhandled traceback. This is
    not the silent fallback CLAUDE.md refuses: the caller still gets exactly the same loud
    `CommandRefusalError` a typed "n" produces, nothing is swallowed, only the crash is.
    """
    try:
        return input(prompt)
    except EOFError:
        return ""


def gate(
    instance: object,
    command_name: str,
    args: BaseModel,
    *,
    yes: bool,
    policy: PermissionPolicy,
) -> None:
    """Refuse, prompt, or permit `instance`'s run — see the module docstring in full.

    `instance` is typed `object`, not `weft_command.contract.Command`, on purpose: everything
    this function reads off it goes through `getattr` regardless (see the paragraph below), so
    typing it as the Protocol would buy nothing and would force every caller — including a test
    double that only needs to carry `permission_class` — to satisfy `Command`'s full structural
    shape just to be handed to a function that never calls `run` on it.

    A no-op for every class but `overwrite`/`destroy`. For those two: `yes` or
    `[permissions]`'s own `allow` override permits the run outright; otherwise a TTY is
    prompted and its answer decides; with no TTY, this raises `CommandRefusalError` naming
    `--yes`, which `weft_cli.render.render_refusal` already reads `.exit_code` off directly —
    the same vehicle `weft_cli.commands`' own `require_active`/`require_plugin` refusals use.
    """
    # Not part of the Protocol body (see `weft_command.contract.Command`'s own docstring on why
    # `permission_class` is a `required_declarations` name, never an `isinstance` member), so
    # this reads it the same defensive way `weft_cli.cli._add_command_level` reads `help` off an
    # unwrapped factory — a default even though `required_declarations` makes it structurally
    # unreachable, and the safest possible default: fail toward asking, never toward skipping.
    permission_class = cast(
        PermissionClass, getattr(instance, "permission_class", PermissionClass.DESTROY)
    )
    if permission_class not in _ASK_CLASSES:
        return

    action = policy.destroy if permission_class is PermissionClass.DESTROY else policy.overwrite
    if yes or action is PermissionAction.ALLOW:
        return

    called_with = args.model_dump()
    article = _article(permission_class.value)
    if not is_interactive():
        raise CommandRefusalError(
            f"'{command_name}' is {article} {permission_class.value}-class command, called "
            f"with {called_with}. It refuses to run with no terminal to confirm in, and "
            f"never proceeds silently. Pass --yes to permit it for this invocation.",
            exit_code=ExitCode.POLICY_REFUSED,
        )

    prompt = (
        f"'{command_name}' is {article} {permission_class.value}-class command, called with "
        f"{called_with}. Proceed? [y/N] "
    )
    answer = read_confirmation(prompt).strip().lower()
    if answer not in {"y", "yes"}:
        raise CommandRefusalError(
            f"'{command_name}' was not confirmed; nothing was done.",
            exit_code=ExitCode.POLICY_REFUSED,
        )


__all__ = ["CommandRefusalError", "gate", "is_interactive", "read_confirmation"]
