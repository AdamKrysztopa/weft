"""Unit tests for `weft_cli.llm_roles`.

Mirrors `packages/weft-cli/src/weft_cli/llm_roles.py`. Covers the happy path (a role
resolves to the provider and model `[llm.roles]` named), the edge case (no `[llm]` table at
all is a legitimate, empty mapping — a retrieval-only project need not have one), and the
error case (a role nothing mapped is refused, naming every role that is).
"""

import pytest

from weft_cli.llm_roles import (
    LLMRoles,
    RoleMapping,
    UnknownLLMKeyError,
    UnmappedLLMRoleError,
    llm_roles_from_config,
    llm_section_from_config,
)
from weft_kernel.errors import WeftError
from weft_llm.loop_guard import LoopGuardConfig
from weft_llm.retry import RetryPolicy


def test_a_mapped_role_resolves_to_its_provider_and_model() -> None:
    # Arrange
    document: dict[str, object] = {
        "llm": {
            "roles": {
                "generate": {"provider": "openai", "model": "gpt-4o-mini"},
                "route": {"provider": "scripted"},
            }
        }
    }

    # Act
    roles = llm_roles_from_config(document)

    # Assert
    assert roles.resolve("generate") == RoleMapping(provider="openai", model="gpt-4o-mini")
    assert roles.resolve("route") == RoleMapping(provider="scripted", model=None)


def test_no_llm_table_at_all_is_a_legitimate_empty_mapping() -> None:
    # Act
    roles = llm_roles_from_config(None)

    # Assert
    assert roles == LLMRoles()


def test_an_unmapped_role_is_refused_naming_every_role_that_is_mapped() -> None:
    # Arrange
    document: dict[str, object] = {"llm": {"roles": {"generate": {"provider": "openai"}}}}
    roles = llm_roles_from_config(document)

    # Act / Assert
    with pytest.raises(UnmappedLLMRoleError) as raised:
        roles.resolve("grade")
    assert "'grade'" in str(raised.value)
    assert "generate" in str(raised.value)


def test_an_unknown_llm_key_is_refused_by_name() -> None:
    # Arrange — `[llm]` accepts `roles` and, since task 2.10 built the retry wrapper, `retry`.
    # A third key is a typo a run would otherwise ignore.
    document: dict[str, object] = {"llm": {"rules": {"attempts": 3}}}

    # Act / Assert
    with pytest.raises(WeftError, match="rules"):
        llm_roles_from_config(document)


def test_an_unknown_llm_key_carries_the_known_keys_as_a_typed_field() -> None:
    # Arrange — repair, 2026-08-20: the message already named the keys, but only inside the
    # string, never as a typed field fitness function 12's family walk can see. `weft_cli.
    # config_surface.UnknownConfigKeyError` is the same-phase precedent this now matches.
    document: dict[str, object] = {"llm": {"rules": {"attempts": 3}}}

    # Act / Assert
    with pytest.raises(UnknownLLMKeyError) as raised:
        llm_roles_from_config(document)
    assert raised.value.valid_options == ("loop_guard", "retry", "roles")


def test_llm_roles_is_absent_from_a_document_with_only_services() -> None:
    # The floor: a document naming a different top-level table must not be mistaken for one
    # naming [llm.roles].
    roles = llm_roles_from_config({"services": {"embed": "openai"}})
    assert roles == LLMRoles()


# --- `[llm.retry]`, added by task 2.10 alongside the retry wrapper it configures ----------


def test_a_retry_block_is_parsed_into_the_policy_the_wrapper_takes() -> None:
    # Arrange
    document: dict[str, object] = {"llm": {"retry": {"attempts": 5, "base_delay_ms": 10}}}

    # Act
    section = llm_section_from_config(document)

    # Assert
    assert (section.retry.attempts, section.retry.base_delay_ms) == (5, 10)


def test_no_retry_block_still_yields_a_usable_policy() -> None:
    # Arrange / Act — every field carries a default, so a `weft.toml` that says nothing about
    # retry still assembles a run rather than making the assembler raise.
    section = llm_section_from_config({"llm": {"roles": {"g": {"provider": "scripted"}}}})

    # Assert
    assert section.retry == RetryPolicy()


def test_a_retry_block_that_is_not_a_table_is_refused() -> None:
    # Arrange / Act / Assert
    with pytest.raises(WeftError):
        llm_section_from_config({"llm": {"retry": 3}})


# --- `[llm.loop_guard]`, added by task 3.10 alongside the degenerate-loop guard it configures


def test_a_loop_guard_block_is_parsed_into_the_config_the_client_reads() -> None:
    # Arrange
    document: dict[str, object] = {"llm": {"loop_guard": {"min_period": 20, "max_period": 200}}}

    # Act
    section = llm_section_from_config(document)

    # Assert
    assert (section.loop_guard.min_period, section.loop_guard.max_period) == (20, 200)


def test_no_loop_guard_block_still_yields_the_measured_defaults() -> None:
    # Arrange / Act — every field carries the value `reference/study/08-salvage.md` §T1.12
    # measured, so a `weft.toml` that says nothing about it still assembles a run.
    section = llm_section_from_config({"llm": {"roles": {"g": {"provider": "scripted"}}}})

    # Assert
    assert section.loop_guard == LoopGuardConfig()


def test_a_loop_guard_block_that_is_not_a_table_is_refused() -> None:
    # Arrange / Act / Assert
    with pytest.raises(WeftError):
        llm_section_from_config({"llm": {"loop_guard": 3}})


def test_loop_guard_is_a_known_llm_key_alongside_retry_and_roles() -> None:
    # Arrange — the same refusal `test_an_unknown_llm_key_is_refused_by_name` proves for a
    # typo, from the other side: `loop_guard` itself must not be treated as unknown.
    document: dict[str, object] = {"llm": {"loop_guard": {"min_period": 30}}}

    # Act / Assert — raises nothing.
    llm_section_from_config(document)
