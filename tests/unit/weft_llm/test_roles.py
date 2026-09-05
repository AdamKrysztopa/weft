"""Unit tests for `weft_llm.roles`.

Mirrors `packages/weft-rag/src/weft_llm/roles.py`. Covers the happy path (a mapped role
resolves to its provider and model), the edge case (an empty table is legitimate) and the
error case (an unmapped role names itself and every role that *is* mapped).

Task 2.10 moved these models here from `weft_cli.llm_roles`: the `LLM` service that consumes
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
