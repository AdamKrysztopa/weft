"""Repair **R43.35**: every registered config field named like a model role is declared one.

The role walk reads `LLMRole` from field metadata and ignores names, so a field spelt `role` or
`<x>_role` without the marker is a role the routed ask never checks, and its rung refuses after a
paid call. The population is what discovery registers here, the `examples/` packs included, plus
each pack's own `[packs.*]` settings model.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Iterable
from importlib import metadata
from typing import Annotated, ClassVar, Final, get_type_hints

from pydantic import BaseModel, ConfigDict, Field

from tests.discovery import (
    CANARY,
    ENTRY_POINT_GROUP,
    discover_for_tests,
    example_pack_dirs,
    register_out_of_tree_examples,
)
from weft_kernel.registry import Registry, unwrap_factory
from weft_llm import LLMRole
from weft_retrieve.contract import Reranker

_NAMED_LIKE_A_ROLE: Final[re.Pattern[str]] = re.compile(r"(^|_)role$")


def _config_models(registry: Registry) -> set[type[BaseModel]]:
    models: set[type[BaseModel]] = set()
    for contract in registry.contracts():
        for name in registry.names_for(contract):
            plugin = unwrap_factory(registry.entry(contract, name).factory)
            model = getattr(plugin, "config_model", None)
            if isinstance(model, type) and issubclass(model, BaseModel):
                models.add(model)
    return models


def _settings_model(register: Callable[..., None]) -> type[BaseModel] | None:
    hints = get_type_hints(register)
    model = hints.get("settings")
    return model if isinstance(model, type) and issubclass(model, BaseModel) else None


def _pack_settings_models() -> set[type[BaseModel]]:
    registers: list[Callable[..., None]] = [
        entry_point.load()
        for entry_point in metadata.entry_points(group=ENTRY_POINT_GROUP)
        if entry_point.dist is not None and entry_point.dist.name != CANARY
    ]
    for example_dir in example_pack_dirs():
        module_name = next(p.name for p in sorted((example_dir / "src").iterdir()) if p.is_dir())
        registers.append(sys.modules[module_name].register)
    return {model for register in registers if (model := _settings_model(register)) is not None}


def _named_like_a_role(models: Iterable[type[BaseModel]]) -> dict[str, bool]:
    return {
        f"{model.__module__}.{model.__qualname__}.{field}": any(
            isinstance(item, LLMRole) for item in info.metadata
        )
        for model in models
        for field, info in model.model_fields.items()
        if _NAMED_LIKE_A_ROLE.search(field)
    }


def _unmarked(fields: dict[str, bool]) -> list[str]:
    return sorted(name for name, marked in fields.items() if not marked)


def test_every_registered_config_field_named_like_a_role_carries_the_marker() -> None:
    # Arrange
    registry = discover_for_tests()
    register_out_of_tree_examples(registry)

    # Act
    fields = _named_like_a_role(_config_models(registry) | _pack_settings_models())

    # Assert
    assert _unmarked(fields) == []
    assert {name.rsplit(".", 1)[1] for name in fields} >= {
        "role",
        "critic_role",
        "answer_role",
        "adjudication_role",
        "judge_role",
    }


class _PlantedConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    foo_role: str = Field(default="foo", min_length=1)
    bar_role: Annotated[str, LLMRole()] = Field(default="bar", min_length=1)


class _Planted:
    config_model: ClassVar[type[_PlantedConfig]] = _PlantedConfig

    def __init__(self, config: object = None) -> None:
        self.config = config


def test_the_check_can_actually_fail() -> None:
    # Arrange
    registry = Registry()
    registry.add(Reranker, "planted", _Planted, distribution="weft-planted")

    # Act
    fields = _named_like_a_role(_config_models(registry))

    # Assert
    assert _unmarked(fields) == [f"{__name__}._PlantedConfig.foo_role"]
    assert fields[f"{__name__}._PlantedConfig.bar_role"] is True
