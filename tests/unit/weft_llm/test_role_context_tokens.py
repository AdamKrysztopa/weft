"""A role declares its model's context size — task 44.14, gate G30 position 1.

Nothing in Weft knows a model's context window, and a table of model names would drift with every
release. So an `[llm.roles]` entry states it, and a role that does not is *unknown*: the corpus
profile then cannot say the corpus fits, and no rule treats unknown as fitting.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from weft_engine.llm_roles import llm_section_from_config
from weft_llm.roles import RoleMapping


def test_a_role_states_its_context_size() -> None:
    # Act
    role = RoleMapping.model_validate(
        {"provider": "openai", "model": "a-model", "context_tokens": 272000}
    )

    # Assert
    assert role.context_tokens == 272000


def test_a_role_that_states_none_is_unknown() -> None:
    # Act
    role = RoleMapping.model_validate({"provider": "openai", "model": "a-model"})

    # Assert
    assert role.context_tokens is None


@pytest.mark.parametrize("value", [0, -1, "large", 1.5])
def test_a_size_that_is_not_a_positive_whole_number_is_refused(value: object) -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="context_tokens"):
        RoleMapping.model_validate({"provider": "openai", "context_tokens": value})


def test_the_size_is_read_from_the_llm_roles_table() -> None:
    # Act
    section = llm_section_from_config(
        {
            "llm": {
                "roles": {
                    "generate": {"provider": "openai", "model": "m", "context_tokens": 128000}
                }
            }
        }
    )

    # Assert
    assert section.roles.roles["generate"].context_tokens == 128000
