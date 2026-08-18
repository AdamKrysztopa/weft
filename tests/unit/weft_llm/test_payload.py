"""Unit tests for `weft_llm.payload`.

Mirrors `packages/weft-llm/src/weft_llm/payload.py`. The one property worth a test of its
own: a `Conversation` with nothing said is refused at construction rather than reaching a
provider that would have to guess what to answer.

`OnFailure`'s own test asserts the one thing ledger 2.15 depends on: `FAIL` exists and is
constructible as a `str`-comparable member, the same way every other `StrEnum` in this tree
is used as a config field default — not that a second member exists, because none does yet.
"""

import pytest
from pydantic import ValidationError

from weft_llm.payload import Completion, Conversation, Message, MessageRole, OnFailure


def test_a_conversation_carries_at_least_one_message() -> None:
    # Act
    conv = Conversation(messages=(Message(role=MessageRole.USER, content="hello"),))

    # Assert
    assert conv.messages[0].content == "hello"


def test_an_empty_conversation_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Conversation(messages=())


def test_completion_carries_the_model_that_actually_answered() -> None:
    # Act
    completion = Completion(text="an answer", model="gpt-4o-mini", finish_reason="stop")

    # Assert
    assert completion.model == "gpt-4o-mini"
    assert completion.finish_reason == "stop"


def test_on_failure_fail_is_a_string_the_same_way_every_config_default_here_is() -> None:
    # Act / Assert — `on_failure: OnFailure = OnFailure.FAIL` is how ledger 2.15's
    # `contextual-query-rewrite` (and every later task naming this field) types its default;
    # this is what makes that constructible and comparable rather than a name in a docstring.
    assert OnFailure.FAIL == "fail"
    assert isinstance(OnFailure.FAIL, str)
