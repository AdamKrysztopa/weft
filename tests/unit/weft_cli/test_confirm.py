"""Unit tests for `weft_cli.confirm`.

Mirrors `packages/weft-cli/src/weft_cli/confirm.py`. Task **3.3**: "a destructive operation with
no TTY fails naming the flag that would permit it, and never proceeds silently." Covers `gate`'s
whole decision tree — a `read`/`write`-class command is never gated at all, `--yes` bypasses an
`overwrite`/`destroy`-class command outright, `[permissions]`'s own `allow` override bypasses it
the identical way, and the two branches design question 3 asks a test to prove without depending
on the developer's terminal: no TTY refuses naming `--yes`, and a TTY prompts and honours both a
confirmed and a declined answer. `is_interactive`/`read_confirmation` are monkeypatched directly —
see the module docstring's own paragraph on why each is its own name rather than an inline
`sys.stdin.isatty()`/`input()` call.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from weft_cli import confirm
from weft_cli.exit_codes import ExitCode
from weft_cli.permission_policy import PermissionPolicy
from weft_command.permission import PermissionClass
from weft_kernel.context import Context


class _Args(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str = "reports"


class _FakeCommand:
    """`gate` reads `instance` through `getattr` alone (see its own docstring) — this stand-in
    carries only `permission_class`, never the rest of `weft_command.contract.Command`'s shape,
    which is exactly the point being proven: `gate` needs nothing more.
    """

    def __init__(self, permission_class: PermissionClass) -> None:
        self.permission_class = permission_class


def test_a_read_class_command_is_never_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — no TTY, no --yes; a read/write-class command must not even ask.
    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    command = _FakeCommand(PermissionClass.READ)

    # Act / Assert — no exception
    confirm.gate(command, "ask", _Args(), yes=False, policy=PermissionPolicy())


def test_a_write_class_command_is_never_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — repair, 2026-08-20: `init`/`pipeline derive`/`config set` moved from
    # `overwrite` to `write` (`docs/build-ledger.md`'s dated paragraph for 3.3/3.6/3.7), so
    # this is no longer only a hypothetical case `read` alone covered.
    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    command = _FakeCommand(PermissionClass.WRITE)

    # Act / Assert — no exception
    confirm.gate(command, "init", _Args(), yes=False, policy=PermissionPolicy())


def test_no_tty_refusal_uses_the_correct_article_for_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — repair, 2026-08-20: the message used to read "is a overwrite-class command"
    # unconditionally (`weft_cli.confirm._article`'s own docstring has the report).
    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    command = _FakeCommand(PermissionClass.OVERWRITE)

    # Act / Assert
    with pytest.raises(confirm.CommandRefusalError) as raised:
        confirm.gate(command, "reindex", _Args(), yes=False, policy=PermissionPolicy())
    assert "is an overwrite-class command" in str(raised.value)
    assert "is a overwrite-class command" not in str(raised.value)


def test_no_tty_refusal_uses_the_correct_article_for_destroy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — the other of the two `_ASK_CLASSES` values, which already read correctly
    # ("is a destroy-class command") — proven explicitly so a future third class cannot
    # regress the rule silently in the other direction.
    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    command = _FakeCommand(PermissionClass.DESTROY)

    # Act / Assert
    with pytest.raises(confirm.CommandRefusalError) as raised:
        confirm.gate(command, "graph destroy", _Args(), yes=False, policy=PermissionPolicy())
    assert "is a destroy-class command" in str(raised.value)


def test_yes_bypasses_a_destroy_class_command_with_no_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    command = _FakeCommand(PermissionClass.DESTROY)

    # Act / Assert — no exception
    confirm.gate(command, "graph destroy", _Args(), yes=True, policy=PermissionPolicy())


def test_permissions_allow_bypasses_a_destroy_class_command_with_no_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — `[permissions] destroy = "allow"`, design question 4's own override.
    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    command = _FakeCommand(PermissionClass.DESTROY)
    policy = PermissionPolicy.model_validate({"destroy": "allow"})

    # Act / Assert — no exception
    confirm.gate(command, "graph destroy", _Args(), yes=False, policy=policy)


def test_no_tty_refuses_naming_the_yes_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — design question 3: proven without depending on the developer's terminal by
    # monkeypatching `is_interactive` directly, never the real `sys.stdin`.
    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    command = _FakeCommand(PermissionClass.DESTROY)

    # Act / Assert — never proceeds silently: it raises, naming the flag that would permit it.
    with pytest.raises(confirm.CommandRefusalError) as raised:
        confirm.gate(command, "graph destroy", _Args(), yes=False, policy=PermissionPolicy())
    assert raised.value.exit_code is ExitCode.POLICY_REFUSED
    assert "--yes" in str(raised.value)
    assert "graph destroy" in str(raised.value)


def test_a_tty_prompts_and_honours_a_confirmed_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    def _confirmed(_prompt: str) -> str:
        return "y"

    monkeypatch.setattr(confirm, "is_interactive", lambda: True)
    monkeypatch.setattr(confirm, "read_confirmation", _confirmed)
    command = _FakeCommand(PermissionClass.OVERWRITE)

    # Act / Assert — no exception; the prompt was answered affirmatively.
    confirm.gate(command, "reindex", _Args(), yes=False, policy=PermissionPolicy())


def test_a_tty_prompts_and_refuses_a_declined_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    def _declined(_prompt: str) -> str:
        return "n"

    monkeypatch.setattr(confirm, "is_interactive", lambda: True)
    monkeypatch.setattr(confirm, "read_confirmation", _declined)
    command = _FakeCommand(PermissionClass.OVERWRITE)

    # Act / Assert
    with pytest.raises(confirm.CommandRefusalError) as raised:
        confirm.gate(command, "reindex", _Args(), yes=False, policy=PermissionPolicy())
    assert raised.value.exit_code is ExitCode.POLICY_REFUSED
    assert "not confirmed" in str(raised.value)


def test_read_confirmation_treats_end_of_input_as_a_decline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — a piped, non-interactive-in-spirit stdin that still reports `isatty()` True
    # (rare, but `input()` still raises `EOFError` the moment it runs dry) must not crash the
    # process; CLAUDE.md refuses a silent fallback, but an unhandled `EOFError` here is not
    # silent, it is a traceback for a case this module already has an honest answer for.
    def _boom(_prompt: str) -> str:
        raise EOFError

    # `input` is a builtin, never assigned in this module's own namespace, so `monkeypatch`
    # needs `raising=False` to add it rather than refuse to override a name that "does not
    # exist" on the module — name resolution inside `read_confirmation` still finds it, since
    # Python checks a module's globals before falling back to builtins.
    monkeypatch.setattr(confirm, "input", _boom, raising=False)

    # Act
    answer = confirm.read_confirmation("proceed? ")

    # Assert
    assert answer == ""


class _DescribingCommand(_FakeCommand):
    """A command that has an optional `describe_impact` — task **5.1a**'s own addition.

    Nothing about it is registered, declared or type-checked as a contract member; `gate`
    finds it with `getattr` or it does not, which is the whole property under test.
    """

    def describe_impact(self, args: BaseModel, ctx: Context) -> str:
        del ctx
        return f"'{args.model_dump()['collection']}' will be removed from 2 participant(s)."


def test_describe_impact_reaches_the_no_tty_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    command = _DescribingCommand(PermissionClass.DESTROY)

    # Act
    with pytest.raises(confirm.CommandRefusalError) as raised:
        confirm.gate(
            command,
            "delete",
            _Args(),
            yes=False,
            policy=PermissionPolicy(),
            ctx=Context(tenant_id="t", run_id="r", trace_id="tr", locale="en"),
        )

    # Assert
    assert "will be removed from 2 participant(s)." in str(raised.value)


def test_describe_impact_reaches_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    seen: list[str] = []
    monkeypatch.setattr(confirm, "is_interactive", lambda: True)

    def _record(prompt: str) -> str:
        seen.append(prompt)
        return "y"

    monkeypatch.setattr(confirm, "read_confirmation", _record)
    command = _DescribingCommand(PermissionClass.DESTROY)

    # Act
    confirm.gate(
        command,
        "delete",
        _Args(),
        yes=False,
        policy=PermissionPolicy(),
        ctx=Context(tenant_id="t", run_id="r", trace_id="tr", locale="en"),
    )

    # Assert
    assert "will be removed from 2 participant(s)." in seen[0]


def test_a_command_with_no_describe_impact_keeps_the_floor_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(confirm, "is_interactive", lambda: False)
    command = _FakeCommand(PermissionClass.DESTROY)

    # Act
    with pytest.raises(confirm.CommandRefusalError) as raised:
        confirm.gate(
            command,
            "wipe",
            _Args(),
            yes=False,
            policy=PermissionPolicy(),
            ctx=Context(tenant_id="t", run_id="r", trace_id="tr", locale="en"),
        )

    # Assert
    assert "called with {'collection': 'reports'}. It refuses to run" in str(raised.value)


def test_an_enum_argument_is_rendered_as_its_value_not_as_its_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task **5.1b**, found by running `weft reconcile`: a bare `model_dump()` left the
    `ReconcileMode` member as an object, so the refusal read `{'mode': <ReconcileMode.FULL:
    'full'>}` — Phase 3's fourth repair recurring one raise site over.
    """

    # Arrange
    class _EnumArgs(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

        mode: PermissionClass = PermissionClass.DESTROY

    monkeypatch.setattr(confirm, "is_interactive", lambda: False)

    # Act
    with pytest.raises(confirm.CommandRefusalError) as raised:
        confirm.gate(
            _FakeCommand(PermissionClass.DESTROY),
            "wipe",
            _EnumArgs(),
            yes=False,
            policy=PermissionPolicy(),
        )

    # Assert
    assert "called with {'mode': 'destroy'}" in str(raised.value)
