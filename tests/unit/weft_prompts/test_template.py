"""Unit tests for `weft_prompts.template`.

Mirrors `packages/weft-prompts/src/weft_prompts/template.py`. Covers the happy path (a
placeholder is filled from a validated model), the property the renderer exists for (a JSON
example passes through with its braces untouched), and both directions of the validator — a
placeholder no field supplies, and a field no placeholder consumes.
"""

import pytest
from pydantic import BaseModel

from weft_prompts.errors import TemplateVariableError, UnusedTemplateFieldError
from weft_prompts.template import placeholders, render_template, validate_template


class _Question(BaseModel):
    question: str
    evidence: str


def test_a_placeholder_is_filled_from_the_model() -> None:
    # Arrange
    values = _Question(question="why?", evidence="because")

    # Act
    text = render_template("Q: ${question}\nE: ${evidence}", values)

    # Assert
    assert text == "Q: why?\nE: because"


def test_a_json_example_survives_with_its_braces_intact() -> None:
    # Arrange — the whole reason this renderer is not `str.format`: the reference's prompts had
    # to escape every `{{`/`}}` in a JSON example, and one that forgot produced garbage.
    class _Empty(BaseModel):
        pass

    template = 'Answer with {"verdict": "yes", "score": 0.5}'

    # Act
    text = render_template(template, _Empty())

    # Assert
    assert text == 'Answer with {"verdict": "yes", "score": 0.5}'


def test_the_placeholders_of_a_template_are_reported_in_order_of_first_use() -> None:
    # Arrange / Act
    found = placeholders("${evidence} then ${question} then ${evidence}")

    # Assert
    assert found == ("evidence", "question")


def test_a_placeholder_no_field_supplies_is_refused_naming_the_fields() -> None:
    # Act / Assert
    with pytest.raises(TemplateVariableError) as raised:
        validate_template("${question} ${citation}", _Question, where="test:en")
    message = str(raised.value)
    assert "citation" in message
    assert "evidence" in message


def test_a_field_no_placeholder_consumes_is_refused_too() -> None:
    # Act / Assert — the second direction. A field nothing renders is dead configuration, and
    # a translator who dropped a variable has silently changed what the model is told.
    with pytest.raises(UnusedTemplateFieldError) as raised:
        validate_template("${question}", _Question, where="test:pl")
    assert "evidence" in str(raised.value)


def test_a_lone_dollar_that_is_not_a_placeholder_is_refused_at_validation() -> None:
    # Act / Assert — `string.Template` would raise at render time, which is a failure that
    # arrives on a user's question rather than on the commit that introduced it.
    with pytest.raises(TemplateVariableError):
        validate_template("costs $ 5 ${question} ${evidence}", _Question, where="test:en")
