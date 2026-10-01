"""Which token-counting requirements a role's provider satisfies — asked before a rung is offered.

A rung's `route.requires-token-counting` names an LLM role. It is satisfied when that role's
provider counts the role's model, the question `whole-corpus` asks while it runs, asked up front
and without a model call. A provider that cannot count leaves the rung out; any other failure is not
a "cannot count" and reaches the caller.
"""

from collections.abc import AsyncIterator

import pytest

from weft_cli.route_ask import satisfied_token_counting, with_satisfied_requirements
from weft_engine.llm_roles import LLMSection
from weft_engine.service_roles import RoleTable
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry
from weft_llm.contract import LLMProvider
from weft_llm.payload import Completion, Conversation
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.scripted import ScriptedProvider
from weft_retrieve.engine import token_counting_requirement_token

_KNOWN = "counted-model"


class _Counting:
    closed = False

    def __init__(self, config: object = None) -> None:
        del config

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del conv, ctx
        return Produced(value=Completion(text="", model=model, finish_reason="stop"))

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        del conv, model, ctx
        yield ""

    async def close(self) -> None:
        _Counting.closed = True

    async def count_tokens(self, text: str, *, model: str) -> int | None:
        return len(text.split()) if model == _KNOWN else None


def _registry() -> Registry:
    registry = Registry()
    registry.add(LLMProvider, "counting", _Counting, distribution="test")
    registry.add(LLMProvider, "scripted", ScriptedProvider, distribution="weft-llm")
    return registry


def _llm(provider: str, model: str | None = _KNOWN) -> LLMSection:
    return LLMSection(
        roles=LLMRoles(roles={"generate": RoleMapping(provider=provider, model=model)})
    )


def _rung(name: str, *, counting: str | None = None) -> Pipeline:
    variables: dict[str, object] = {"route.summary": f"{name} answers"}
    if counting is not None:
        variables["route.requires-token-counting"] = counting
    return Pipeline.model_validate(
        {"name": name, "vars": variables, "stages": [{"id": "retrieve", "use": "vector-top-k"}]}
    )


async def test_a_role_whose_provider_counts_its_model_is_satisfied() -> None:
    # Act
    satisfied = await satisfied_token_counting(
        frozenset({"generate"}), registry=_registry(), llm=_llm("counting")
    )

    # Assert
    assert satisfied == frozenset({token_counting_requirement_token("generate")})


async def test_a_provider_that_cannot_count_or_does_not_know_the_model_is_not_satisfied() -> None:
    # Act
    scripted = await satisfied_token_counting(
        frozenset({"generate"}), registry=_registry(), llm=_llm("scripted", "any-model")
    )
    unknown_model = await satisfied_token_counting(
        frozenset({"generate"}), registry=_registry(), llm=_llm("counting", "other-model")
    )

    # Assert
    assert scripted == frozenset()
    assert unknown_model == frozenset()


async def test_a_role_nothing_maps_is_not_satisfied_and_is_not_an_error() -> None:
    # Act — the rung is left out, and the role filter says the role is unmapped.
    satisfied = await satisfied_token_counting(
        frozenset({"grade"}), registry=_registry(), llm=_llm("counting")
    )

    # Assert
    assert satisfied == frozenset()


async def test_no_requirements_asks_nothing_and_builds_nothing() -> None:
    # Act — an empty registry would raise if a provider were built
    satisfied = await satisfied_token_counting(
        frozenset(), registry=Registry(), llm=_llm("counting")
    )

    # Assert
    assert satisfied == frozenset()


async def test_the_probe_closes_the_provider_it_built() -> None:
    # Arrange
    _Counting.closed = False

    # Act
    await satisfied_token_counting(
        frozenset({"generate"}), registry=_registry(), llm=_llm("counting")
    )

    # Assert
    assert _Counting.closed


async def test_the_ready_set_gains_the_token_only_over_a_provider_that_counts() -> None:
    # Arrange
    catalogue = {"plain": _rung("plain"), "whole": _rung("whole", counting="generate")}

    async def ready(provider: str, model: str) -> frozenset[str] | None:
        return await with_satisfied_requirements(
            frozenset({"enrich-with-questions"}),
            catalogue,
            registry=_registry(),
            services=ServiceSelection(),
            roles=RoleTable(roles={}),
            target=None,
            llm=_llm(provider, model),
        )

    # Act / Assert
    assert await ready("counting", _KNOWN) == frozenset(
        {"enrich-with-questions", token_counting_requirement_token("generate")}
    )
    assert await ready("scripted", "any-model") == frozenset({"enrich-with-questions"})


async def test_told_nothing_the_provider_is_never_asked() -> None:
    # Arrange
    catalogue = {"whole": _rung("whole", counting="generate")}

    # Act — an empty registry would raise if a provider were built
    ready = await with_satisfied_requirements(
        None,
        catalogue,
        registry=Registry(),
        services=ServiceSelection(),
        roles=RoleTable(roles={}),
        target=None,
        llm=_llm("counting"),
    )

    # Assert
    assert ready is None


async def test_a_counting_requirement_without_the_llm_section_is_a_caller_error() -> None:
    # Arrange
    catalogue = {"whole": _rung("whole", counting="generate")}

    # Act / Assert
    with pytest.raises(ValueError, match="llm"):
        await with_satisfied_requirements(
            frozenset(),
            catalogue,
            registry=_registry(),
            services=ServiceSelection(),
            roles=RoleTable(roles={}),
            target=None,
        )
