"""Unit tests for `weft_cli.session`.

Mirrors `packages/weft-rag/src/weft_cli/session.py`. Task **3.5**: "session state is explicit
and inspectable, so the same command does not behave differently for two people running the
same command." These cover the data half in isolation — a frozen model replaced wholesale on
each change, never mutated in place — before `tests/unit/weft_cli/test_repl.py` proves the loop
wires it in correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from weft_cli.exit_codes import ExitCode
from weft_cli.session import (
    SessionState,
    TurnTrace,
    cleared,
    with_active_pipeline,
    with_turn_recorded,
)


def test_session_state_starts_with_no_pipeline_and_no_trace() -> None:
    state = SessionState()

    assert state.active_pipeline is None
    assert state.last_trace is None


def test_with_active_pipeline_replaces_the_state_wholesale_rather_than_mutating() -> None:
    # The idiom this codebase uses for a frozen model that changes across turns —
    # `base.model_copy(update=...)` — proven directly: the original is untouched.
    original = SessionState()

    updated = with_active_pipeline(original, "graphrag")

    assert original.active_pipeline is None
    assert updated.active_pipeline == "graphrag"


def test_with_turn_recorded_carries_the_command_name_line_and_exit_code() -> None:
    state = with_turn_recorded(
        SessionState(), command_name="plugins list", line="/plugins", exit_code=ExitCode.SUCCESS
    )

    assert state.last_trace == TurnTrace(
        command_name="plugins list", line="/plugins", exit_code=ExitCode.SUCCESS
    )


def test_with_turn_recorded_overwrites_rather_than_accumulates() -> None:
    # Edge case: `03` names "the last run's trace" — singular, never a growing log. That is
    # exactly the distinction this task draws against "conversation history" — see this
    # module's own docstring for why a log is deferred rather than built here.
    first = with_turn_recorded(
        SessionState(), command_name="ask", line="ask x", exit_code=ExitCode.SUCCESS
    )

    second = with_turn_recorded(
        first, command_name="index", line="index .", exit_code=ExitCode.OPERATION_FAILED
    )

    assert second.last_trace is not None
    assert second.last_trace.command_name == "index"


def test_cleared_resets_every_field_to_its_default() -> None:
    state = with_active_pipeline(
        with_turn_recorded(
            SessionState(), command_name="ask", line="ask x", exit_code=ExitCode.SUCCESS
        ),
        "graphrag",
    )

    assert cleared(state) == SessionState()


def test_session_state_rejects_an_unknown_field() -> None:
    # Error case: `extra="forbid"` means an inspectable model cannot silently grow a field
    # nothing here declared — the same discipline every other frozen model in this package
    # follows (`weft_cli.permission_policy.PermissionPolicy`, `weft_cli.services.ServiceSelection`).
    with pytest.raises(ValidationError):
        SessionState.model_validate({"active_pipeline": "x", "bogus": True})
