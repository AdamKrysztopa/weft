"""Repairs **R43.35** and **R43.42**: every registered config field named like a model role, or
like a sub-plugin reference, is declared one, in a spelling pydantic keeps.

The role walk reads `LLMRole` from field metadata and ignores names, so a field spelt `role` or
`<x>_role` without the marker is a role the routed ask never checks, and its rung refuses after a
paid call. The population is what discovery registers here, the `examples/` packs included, plus
each pack's own `[packs.*]` settings model, and every model nested in either (`RetrieverArm`
inside `multi-retriever`'s `arms`). R43.42 adds the sub-plugin references the walk follows, and the
`Annotated[str, LLMRole()] | None` spelling, whose marker pydantic drops from `FieldInfo.metadata`.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Iterable
from importlib import metadata
from typing import Annotated, ClassVar, Final, get_args, get_origin, get_type_hints

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
from weft_retrieve import SubPlugin
from weft_retrieve.contract import Reranker

_NAMED_LIKE_A_ROLE: Final[re.Pattern[str]] = re.compile(r"(^|_)role$")
_SUB_CONFIG_SUFFIX: Final[str] = "_config"


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


def _nested(annotation: object, found: set[type[BaseModel]]) -> None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation not in found:
            found.add(annotation)
            for info in annotation.model_fields.values():
                _nested(info.annotation, found)
        return
    for argument in get_args(annotation):
        _nested(argument, found)


def _with_nested(models: Iterable[type[BaseModel]]) -> set[type[BaseModel]]:
    found: set[type[BaseModel]] = set()
    for model in models:
        _nested(model, found)
    return found


def _mentions(annotation: object, marker: type[object]) -> bool:
    arguments = get_args(annotation)
    if get_origin(annotation) is Annotated and any(
        isinstance(item, marker) for item in arguments[1:]
    ):
        return True
    return any(_mentions(argument, marker) for argument in arguments)


def _dropped_markers(models: Iterable[type[BaseModel]]) -> list[str]:
    return sorted(
        f"{model.__module__}.{model.__qualname__}.{field}"
        for model in models
        for field, info in model.model_fields.items()
        for marker in (LLMRole, SubPlugin)
        if _mentions(info.annotation, marker)
        and not any(isinstance(item, marker) for item in info.metadata)
    )


def _sibling_of(field: str, fields: Iterable[str]) -> str | None:
    names = set(fields)
    if f"{field}{_SUB_CONFIG_SUFFIX}" in names:
        return f"{field}{_SUB_CONFIG_SUFFIX}"
    if field == "use" and "config" in names:
        return "config"
    return None


def _references(models: Iterable[type[BaseModel]]) -> dict[str, str | None]:
    """Each field spelt like a sub-plugin reference, to the `config` its `SubPlugin` names, or to
    `None` when it carries no marker."""
    found: dict[str, str | None] = {}
    for model in models:
        fields = model.model_fields
        for field, info in fields.items():
            if _sibling_of(field, fields) is None:
                continue
            markers = [item for item in info.metadata if isinstance(item, SubPlugin)]
            found[f"{model.__qualname__}.{field}"] = markers[0].config if markers else None
    return found


def _unpaired(models: Iterable[type[BaseModel]]) -> list[str]:
    """Every reference that is unmarked or names the wrong sibling, and every `SubPlugin` whose
    `config` names no field of its model."""
    problems: list[str] = []
    for model in models:
        fields = model.model_fields
        for field, info in fields.items():
            sibling = _sibling_of(field, fields)
            for marker in (item for item in info.metadata if isinstance(item, SubPlugin)):
                if marker.config is not None and marker.config not in fields:
                    problems.append(f"{model.__qualname__}.{field}: names no field {marker.config}")
                elif sibling is not None and marker.config != sibling:
                    problems.append(f"{model.__qualname__}.{field}: pairs {marker.config}")
            if sibling is not None and not any(isinstance(i, SubPlugin) for i in info.metadata):
                problems.append(f"{model.__qualname__}.{field}: unmarked")
    return sorted(problems)


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
    fields = _named_like_a_role(_with_nested(_config_models(registry) | _pack_settings_models()))

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


def test_no_registered_config_field_spells_a_marker_where_pydantic_drops_it() -> None:
    """R43.42: `Annotated[str, LLMRole()] | None` loses the marker from `FieldInfo.metadata`;
    `Annotated[str | None, LLMRole()]` keeps it, and is the spelling the tree uses."""
    # Arrange
    registry = discover_for_tests()
    register_out_of_tree_examples(registry)

    # Act
    dropped = _dropped_markers(_with_nested(_config_models(registry) | _pack_settings_models()))

    # Assert
    assert dropped == []


class _PlantedOptionalConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lossy_by: Annotated[str, LLMRole()] | None = None
    kept_by: Annotated[str | None, LLMRole()] = None
    lossy_helper: Annotated[str, SubPlugin(config="lossy_settings")] | None = None
    lossy_settings: dict[str, object] | None = None


class _PlantedOptional:
    config_model: ClassVar[type[_PlantedOptionalConfig]] = _PlantedOptionalConfig

    def __init__(self, config: object = None) -> None:
        self.config = config


def test_the_dropped_marker_check_can_actually_fail() -> None:
    # Arrange
    registry = Registry()
    registry.add(Reranker, "planted-optional", _PlantedOptional, distribution="weft-planted")

    # Act
    dropped = _dropped_markers(_with_nested(_config_models(registry)))

    # Assert
    assert dropped == [
        f"{__name__}._PlantedOptionalConfig.lossy_by",
        f"{__name__}._PlantedOptionalConfig.lossy_helper",
    ]


def test_every_registered_sub_plugin_reference_is_declared_with_its_config() -> None:
    """R43.42: a reference the walk cannot pair with its config is a sibling whose roles it
    never reads, so a routed rung naming it is offered and refuses after a paid call."""
    # Arrange
    registry = discover_for_tests()
    register_out_of_tree_examples(registry)
    models = _with_nested(_config_models(registry) | _pack_settings_models())

    # Act
    problems = _unpaired(models)

    # Assert
    assert problems == []
    assert _references(models).items() >= {
        ("RetrieverArm.use", "config"),
        ("IterativeRetrievalConfig.leaf", "leaf_config"),
        ("IterativeRetrievalConfig.sufficiency", "sufficiency_config"),
        ("CorrectiveConfig.primary", "primary_config"),
        ("CorrectiveConfig.grader", "grader_config"),
        ("CorrectiveConfig.knowledge_action", "knowledge_action_config"),
        ("RefineOnUncertaintyConfig.signal", "signal_config"),
        ("RefineOnUncertaintyConfig.retriever", "retriever_config"),
    }


class _PlantedArm(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    use: str
    config: dict[str, object] | None = None


class _PlantedComposerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    arms: tuple[_PlantedArm, ...] = ()
    helper: str = "helper"
    helper_config: dict[str, object] | None = None
    other: Annotated[str, SubPlugin(config="helper_config")] = "other"
    stray: Annotated[str, SubPlugin(config="stray_settings")] = "stray"
    paired: Annotated[str, SubPlugin(config="paired_config")] = "paired"
    paired_config: dict[str, object] | None = None


class _PlantedComposer:
    config_model: ClassVar[type[_PlantedComposerConfig]] = _PlantedComposerConfig

    def __init__(self, config: object = None) -> None:
        self.config = config


def test_the_sub_plugin_check_can_actually_fail() -> None:
    # Arrange
    registry = Registry()
    registry.add(Reranker, "planted-composer", _PlantedComposer, distribution="weft-planted")

    # Act
    problems = _unpaired(_with_nested(_config_models(registry)))

    # Assert
    assert problems == [
        "_PlantedArm.use: unmarked",
        "_PlantedComposerConfig.helper: unmarked",
        "_PlantedComposerConfig.stray: names no field stray_settings",
    ]
