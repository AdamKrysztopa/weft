"""Unit tests for `weft_llm.roles`.

Mirrors `packages/weft-rag/src/weft_llm/roles.py`. Covers the happy path (a mapped role
resolves to its provider and model), the edge case (an empty table is legitimate) and the
error case (an unmapped role names itself and every role that *is* mapped).

Task 2.10 moved these models here from `weft_engine.llm_roles`: the `LLM` service that consumes
them lives in `weft-llm`, and a service cannot import the CLI that assembles it.
"""

import pytest

from weft_llm.roles import LLMRoles, RoleMapping, UnmappedLLMRoleError


def test_a_mapped_role_resolves_to_its_provider_and_model() -> None:
    # Arrange
    roles = LLMRoles(roles={"generate": RoleMapping(provider="openai", model="gpt-4o-mini")})

    # Act
    mapped = roles.resolve("generate")

    # Assert
    assert (mapped.provider, mapped.model) == ("openai", "gpt-4o-mini")


def test_a_role_with_no_model_is_legitimate() -> None:
    # Arrange
    roles = LLMRoles(roles={"route": RoleMapping(provider="scripted")})

    # Act
    mapped = roles.resolve("route")

    # Assert — `scripted` reads nothing from a model string; `None` is the honest answer.
    assert mapped.model is None


def test_an_unmapped_role_names_itself_and_every_mapped_role() -> None:
    # Arrange
    roles = LLMRoles(roles={"generate": RoleMapping(provider="scripted")})

    # Act / Assert
    with pytest.raises(UnmappedLLMRoleError) as raised:
        roles.resolve("grade")
    message = str(raised.value)
    assert "grade" in message
    assert "generate" in message


# --- Repair R41.7: the line the refusal prints is one the system accepts --------------------

_INSTALLED = ("openai", "openai-compatible", "scripted")


def test_the_suggested_entry_names_an_installed_provider_that_can_answer() -> None:
    """`scripted` cannot produce a structured answer, so following it for `route` exited 4."""
    # Arrange
    roles = LLMRoles(roles={"generate": RoleMapping(provider="openai", model="m")})

    # Act
    with pytest.raises(UnmappedLLMRoleError) as raised:
        roles.resolve("route", providers=_INSTALLED)

    # Assert
    message = str(raised.value)
    assert 'route = { provider = "openai", model = "<model>" }' in message
    assert 'provider = "scripted"' not in message


def test_a_file_that_already_has_the_table_is_told_one_line_not_a_second_header() -> None:
    """Pasting a second `[llm.roles]` header into a file that has one is invalid TOML."""
    # Arrange
    roles = LLMRoles(roles={"generate": RoleMapping(provider="openai", model="m")})

    # Act
    with pytest.raises(UnmappedLLMRoleError) as raised:
        roles.resolve("route", providers=_INSTALLED)

    # Assert
    assert "\n[llm.roles]\n" not in str(raised.value)


def test_a_file_with_no_table_is_told_the_header_and_the_line() -> None:
    # Arrange
    roles = LLMRoles()

    # Act
    with pytest.raises(UnmappedLLMRoleError) as raised:
        roles.resolve("route", providers=_INSTALLED)

    # Assert
    assert '\n[llm.roles]\nroute = { provider = "openai", model = "<model>" }' in str(raised.value)


def test_with_only_scripted_installed_the_remedy_is_installing_a_provider() -> None:
    # Arrange
    roles = LLMRoles(roles={"generate": RoleMapping(provider="scripted")})

    # Act
    with pytest.raises(UnmappedLLMRoleError) as raised:
        roles.resolve("route", providers=("scripted",))

    # Assert
    message = str(raised.value)
    assert 'pip install "weft-rag[openai]"' in message
    assert 'provider = "scripted"' not in message
