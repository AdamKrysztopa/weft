"""Repair **R43.45**: a `SubPlugin` whose `config` names no field of its model is refused, naming
the fields the model has.

R43.42 published `SubPlugin(config="<field>")`, and the role walk read that field with a bare
`getattr`, so a stranger's `SubPlugin(config="setings")` raised `AttributeError` naming nothing —
requirement 5 on the surface R43.42 published. The refusal is FF12's family: the declared name
fails against an enumerable set, the declaring model's own fields.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.errors import UnresolvedNameError
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import resolve
from weft_kernel.runner import PipelineResolutionError
from weft_llm import LLMRole
from weft_retrieve import SubPlugin
from weft_retrieve.contract import Reranker
from weft_retrieve.engine import UnknownSubPluginConfigFieldError, roles_needed
from weft_retrieve.payload import Ranking

_RUNG = "composed-rung"
_JUDGE = "stranger-judge"
_MISDECLARED = "stranger-misdeclared"
_MISDECLARED_SEATS = "stranger-misdeclared-seats"
_MISDECLARED_UNSET = "stranger-misdeclared-unset"
_DECLARED = "stranger-declared"


class _JudgeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judge_role: Annotated[str, LLMRole()] = Field(default="judge", min_length=1)


class _MisdeclaredConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    panelist: Annotated[str, SubPlugin(config="setings")] = Field(min_length=1)
    settings: Mapping[str, object] | None = None
    quorum: int = 1


class _MisdeclaredSeat(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reranker: Annotated[str, SubPlugin(config="reranker_with")] = Field(min_length=1)
    options: Mapping[str, object] | None = None


class _MisdeclaredSeatsConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seats: tuple[_MisdeclaredSeat, ...] = Field(min_length=1)


class _MisdeclaredUnsetConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    helper: Annotated[str, SubPlugin(config="helper_setings")] | None = None
    helper_settings: Mapping[str, object] | None = None


class _DeclaredConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    panelist: Annotated[str, SubPlugin(config="settings")] = Field(min_length=1)
    settings: Mapping[str, object] | None = None


class _Passthrough:
    config_model: ClassVar[type[BaseModel]]

    def __init__(self, config: object = None) -> None:
        self.config = config

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        del ctx
        return Produced(value=payload)


class _Judge(_Passthrough):
    config_model = _JudgeConfig


class _Misdeclared(_Passthrough):
    config_model = _MisdeclaredConfig


class _MisdeclaredSeats(_Passthrough):
    config_model = _MisdeclaredSeatsConfig


class _MisdeclaredUnset(_Passthrough):
    config_model = _MisdeclaredUnsetConfig


class _Declared(_Passthrough):
    config_model = _DeclaredConfig


def _registry() -> Registry:
    registry = Registry()
    for name, plugin in (
        (_JUDGE, _Judge),
        (_MISDECLARED, _Misdeclared),
        (_MISDECLARED_SEATS, _MisdeclaredSeats),
        (_MISDECLARED_UNSET, _MisdeclaredUnset),
        (_DECLARED, _Declared),
    ):
        registry.add(Reranker, name, plugin, distribution="weft-example-stranger")
    return registry


def _roles(use: str, config: Mapping[str, object]) -> frozenset[str]:
    registry = _registry()
    stage = StageDeclaration(id="stage", use=use, config=dict(config))
    resolved = resolve(
        Pipeline(name=_RUNG, stages=(stage,)), registry=registry, contracts={"stage": Reranker}
    )
    return roles_needed(resolved, registry)


def test_the_refusal_is_in_fitness_function_12s_family_and_exits_as_a_resolution_failure() -> None:
    # Assert
    assert issubclass(UnknownSubPluginConfigFieldError, UnresolvedNameError)
    assert issubclass(UnknownSubPluginConfigFieldError, PipelineResolutionError)


def test_a_reference_naming_no_field_of_its_model_is_refused_naming_the_fields_it_has() -> None:
    # Act
    with pytest.raises(UnknownSubPluginConfigFieldError) as refused:
        _roles(_MISDECLARED, {"panelist": _JUDGE, "settings": {"judge_role": "critic"}})

    # Assert
    message = str(refused.value)
    assert refused.value.valid_options == ("panelist", "quorum", "settings")
    assert f"{_MisdeclaredConfig.__name__}.panelist" in message, message
    assert "'setings'" in message, message
    assert all(field in message for field in refused.value.valid_options), message
    assert refused.value.pipeline == _RUNG


def test_the_fields_named_are_the_declaring_models_own_when_it_is_nested() -> None:
    # Act
    with pytest.raises(UnknownSubPluginConfigFieldError) as refused:
        _roles(_MISDECLARED_SEATS, {"seats": [{"reranker": _JUDGE}]})

    # Assert
    message = str(refused.value)
    assert refused.value.valid_options == ("options", "reranker")
    assert f"{_MisdeclaredSeat.__name__}.reranker" in message, message
    assert "'reranker_with'" in message, message


def test_a_misdeclared_reference_is_refused_even_where_this_document_leaves_it_unset() -> None:
    """The declaration is the pack's defect whatever a document sets; refusing only when a
    document happens to set the field would leave the defect to surface on someone else's rung."""
    # Act
    with pytest.raises(UnknownSubPluginConfigFieldError) as refused:
        _roles(_MISDECLARED_UNSET, {})

    # Assert
    assert refused.value.valid_options == ("helper", "helper_settings")
    assert "'helper_setings'" in str(refused.value)


def test_a_reference_naming_a_field_its_model_has_is_still_followed() -> None:
    # Act
    roles = _roles(_DECLARED, {"panelist": _JUDGE, "settings": {"judge_role": "critic"}})

    # Assert
    assert roles == frozenset({"critic"})
