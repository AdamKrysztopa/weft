"""Carried repair **R44.13e** — which role requirements the selected service satisfies.

A rung's `route.requires-role` names a `[services]` role. It is satisfied when a plugin is selected
for that role and the built service answers `holds_data()` with `True`: the question the rung's own
retrieval will ask of that service, asked before the rung is offered. A role nothing selects holds
nothing to read; a selected service that cannot say whether it holds data is refused, never guessed
at in either direction.
"""

import pytest

from weft_cli.route_ask import (
    RoleNotProbeableError,
    satisfied_role_requirements,
    with_satisfied_requirements,
)
from weft_engine.service_roles import RoleTable
from weft_engine.services import ServiceSelection, UnknownServiceKeyError
from weft_kernel.context import ServiceRole
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry
from weft_retrieve.engine import role_requirement_token


class _Walker:
    """The contract the `graph` role selects, standing in for a graph traversal."""

    def __init__(self, config: object = None) -> None:
        del config


class _Holding(_Walker):
    closed = False

    async def holds_data(self) -> bool:
        return True

    async def aclose(self) -> None:
        _Holding.closed = True


class _Empty(_Walker):
    async def holds_data(self) -> bool:
        return False


class _Mute(_Walker):
    """A selected service with no way to say whether it holds anything."""


_ROLES = RoleTable(roles={"graph": ServiceRole(key="graph", contract=_Walker)})


def _registry() -> Registry:
    registry = Registry()
    registry.add(_Walker, "holding", _Holding, distribution="weft-example")
    registry.add(_Walker, "empty", _Empty, distribution="weft-example")
    registry.add(_Walker, "mute", _Mute, distribution="weft-example")
    return registry


def _selecting(plugin: str | None) -> ServiceSelection:
    return ServiceSelection(roles={} if plugin is None else {"graph": plugin})


async def test_a_selected_service_that_holds_data_satisfies_the_role() -> None:
    # Act
    satisfied = await satisfied_role_requirements(
        frozenset({"graph"}), registry=_registry(), services=_selecting("holding"), roles=_ROLES
    )

    # Assert
    assert satisfied == frozenset({role_requirement_token("graph")})


async def test_a_selected_service_that_holds_nothing_satisfies_none() -> None:
    # Act
    satisfied = await satisfied_role_requirements(
        frozenset({"graph"}), registry=_registry(), services=_selecting("empty"), roles=_ROLES
    )

    # Assert
    assert satisfied == frozenset()


async def test_a_role_nothing_selects_satisfies_none_without_building_anything() -> None:
    # Act — an empty registry proves nothing was looked up
    satisfied = await satisfied_role_requirements(
        frozenset({"graph"}), registry=Registry(), services=_selecting(None), roles=_ROLES
    )

    # Assert
    assert satisfied == frozenset()


async def test_a_selected_service_that_cannot_say_is_refused_naming_it() -> None:
    # Act
    with pytest.raises(RoleNotProbeableError) as refused:
        await satisfied_role_requirements(
            frozenset({"graph"}), registry=_registry(), services=_selecting("mute"), roles=_ROLES
        )

    # Assert
    assert "'mute'" in str(refused.value)
    assert "holds_data" in str(refused.value)


async def test_a_role_no_installed_pack_declares_is_refused_naming_the_valid_keys() -> None:
    # Act
    with pytest.raises(UnknownServiceKeyError) as refused:
        await satisfied_role_requirements(
            frozenset({"graf"}), registry=_registry(), services=_selecting("holding"), roles=_ROLES
        )

    # Assert
    assert refused.value.valid_options == ("graph",)
    assert "'graf'" in str(refused.value)


async def test_the_probed_service_is_closed_again() -> None:
    # Arrange
    _Holding.closed = False

    # Act
    await satisfied_role_requirements(
        frozenset({"graph"}), registry=_registry(), services=_selecting("holding"), roles=_ROLES
    )

    # Assert
    assert _Holding.closed


async def test_no_requirement_asks_nothing() -> None:
    # Act / Assert
    assert (
        await satisfied_role_requirements(
            frozenset(), registry=Registry(), services=_selecting("holding"), roles=_ROLES
        )
        == frozenset()
    )


def _rung(name: str, *, requires_role: str | None = None) -> Pipeline:
    variables = {"route.summary": f"{name} answers"}
    if requires_role is not None:
        variables["route.requires-role"] = requires_role
    return Pipeline.model_validate(
        {"name": name, "vars": variables, "stages": [{"id": "retrieve", "use": "vector-top-k"}]}
    )


async def test_the_ready_set_gains_a_role_token_only_over_a_service_that_holds_data() -> None:
    # Arrange
    catalogue = {"plain": _rung("plain"), "graphy": _rung("graphy", requires_role="graph")}

    # Act
    holding = await with_satisfied_requirements(
        frozenset({"enrich-with-questions"}),
        catalogue,
        registry=_registry(),
        services=_selecting("holding"),
        roles=_ROLES,
        target=None,
    )
    empty = await with_satisfied_requirements(
        frozenset({"enrich-with-questions"}),
        catalogue,
        registry=_registry(),
        services=_selecting("empty"),
        roles=_ROLES,
        target=None,
    )

    # Assert
    assert holding == frozenset({"enrich-with-questions", role_requirement_token("graph")})
    assert empty == frozenset({"enrich-with-questions"})


async def test_told_nothing_the_service_is_never_asked() -> None:
    # Arrange
    catalogue = {"graphy": _rung("graphy", requires_role="graph")}

    # Act — an empty registry would raise if the role were looked up
    ready = await with_satisfied_requirements(
        None,
        catalogue,
        registry=Registry(),
        services=_selecting("holding"),
        roles=_ROLES,
        target=None,
    )

    # Assert
    assert ready is None
