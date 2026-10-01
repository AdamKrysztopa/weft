"""A rung that reads under a token bound is offered only when its role's provider can count tokens.

`whole-corpus` counts every leaf against its bound with the `generate` role's provider. A provider
that cannot count raised `TokenCountUnavailableError` only after the router had chosen the rung and
the question was running. A rung writes `route.requires-token-counting: <role>`, and the caller adds
that role's token to the ready set only when the provider counts (`weft_cli.route_ask`), so the
rung is left out before routing, with the reason kept for the route to say.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from weft_kernel.pipeline import Pipeline
from weft_retrieve.engine import (
    MalformedRouteRequirementError,
    route_catalogue,
    token_counting_requirement_token,
    token_counting_requirements,
)

_WHOLE_CORPUS_RUNG = (
    Path(__file__).resolve().parents[3]
    / "packages/weft-rag/src/weft_retrieve/pipelines/whole-corpus-wide-then-generate.yaml"
)


def _document(name: str, *, counting: Any = None) -> Pipeline:
    variables: dict[str, Any] = {"route.summary": f"{name} answers", "route.cost": "one search"}
    if counting is not None:
        variables["route.requires-token-counting"] = counting
    return Pipeline.model_validate(
        {"name": name, "vars": variables, "stages": [{"id": "retrieve", "use": "vector-top-k"}]}
    )


_CATALOGUE = {"plain": _document("plain"), "whole": _document("whole", counting="generate")}


def test_a_counting_rung_is_offered_only_once_its_roles_token_is_ready() -> None:
    # Act
    withheld = route_catalogue(_CATALOGUE, ready_layers=frozenset()).names()
    offered = route_catalogue(
        _CATALOGUE, ready_layers=frozenset({token_counting_requirement_token("generate")})
    ).names()

    # Assert
    assert withheld == frozenset({"plain"})
    assert offered == frozenset({"plain", "whole"})


def test_a_withheld_rung_says_why_in_terms_of_the_role_and_the_missing_count() -> None:
    # Act
    catalogue = route_catalogue(_CATALOGUE, ready_layers=frozenset())

    # Assert
    reason = catalogue.withheld_reason("whole")
    assert reason is not None
    assert "'generate'" in reason
    assert "count tokens" in reason
    assert catalogue.withheld_reason("plain") is None


def test_an_offered_rung_has_no_reason_and_told_nothing_withholds_nothing() -> None:
    # Act
    offered = route_catalogue(
        _CATALOGUE, ready_layers=frozenset({token_counting_requirement_token("generate")})
    )
    told_nothing = route_catalogue(_CATALOGUE)

    # Assert
    assert offered.withheld_reason("whole") is None
    assert told_nothing.names() == frozenset(_CATALOGUE)
    assert told_nothing.withheld_reason("whole") is None


def test_a_ready_set_spelling_the_role_but_not_its_token_does_not_offer_the_rung() -> None:
    # Act
    offered = route_catalogue(_CATALOGUE, ready_layers=frozenset({"generate"})).names()

    # Assert
    assert offered == frozenset({"plain"})


def test_counting_requirements_are_every_distinct_role_the_catalogue_names() -> None:
    # Arrange
    catalogue = {**_CATALOGUE, "also": _document("also", counting="generate")}

    # Act / Assert
    assert token_counting_requirements(catalogue) == frozenset({"generate"})
    assert token_counting_requirements({"plain": _CATALOGUE["plain"]}) == frozenset()


@pytest.mark.parametrize("value", ["", "  ", 3, True])
def test_a_counting_requirement_that_is_not_a_role_key_is_refused(value: object) -> None:
    # Act / Assert
    with pytest.raises(MalformedRouteRequirementError):
        token_counting_requirements({"bad": _document("bad", counting=value)})


def test_the_shipped_whole_corpus_rung_asks_for_counting_under_generate() -> None:
    # Arrange
    document = yaml.safe_load(_WHOLE_CORPUS_RUNG.read_text(encoding="utf-8"))

    # Act / Assert
    assert document["vars"]["route.requires-token-counting"] == "generate"
