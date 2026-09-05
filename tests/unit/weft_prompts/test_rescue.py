"""Unit tests for `weft_prompts.rescue`.

Mirrors `packages/weft-rag/src/weft_prompts/rescue.py`. Covers the three extraction steps
in the order the reference's *executor* used them — direct parse, fenced block, bare object — and
the case the reference's other copy got wrong: a fenced ```json reply must be read as a fence,
not clipped by a bare-object scan that runs first.
"""

from weft_prompts.rescue import rescue_json


def test_a_clean_json_document_parses_directly() -> None:
    # Arrange / Act
    found = rescue_json('{"verdict": "yes"}')

    # Assert
    assert found == {"verdict": "yes"}


def test_a_fenced_json_block_is_read_as_a_fence() -> None:
    # Arrange — the ordering bug the reference's `llm_utils` copy carried: a bare-object regex
    # placed before this branch makes the fence branch nearly unreachable, and it is the
    # commonest reply shape a chat model produces.
    # The prose deliberately contains a brace: a bare-object scan run first would span from
    # that brace to the last one and parse nothing, which is precisely the reference's other copy.
    text = 'Given {the evidence}, here you go:\n```json\n{"verdict": "no"}\n```\nHope that helps.'

    # Act
    found = rescue_json(text)

    # Assert
    assert found == {"verdict": "no"}


def test_a_bare_object_embedded_in_prose_is_the_last_resort() -> None:
    # Arrange / Act
    found = rescue_json('I think {"verdict": "maybe"} is right.')

    # Assert
    assert found == {"verdict": "maybe"}


def test_text_with_no_json_at_all_rescues_nothing() -> None:
    # Arrange / Act
    found = rescue_json("I am not able to answer in that format.")

    # Assert — `None`, never an `{"error": ...}` dict a caller has to string-match.
    assert found is None
