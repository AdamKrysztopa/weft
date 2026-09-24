"""Repair **R43.42**: `roles_needed` reaches a sub-plugin however its composer declares it.

The walk followed a sibling only through an `X`/`X_config` field pair, so `multi-retriever`'s
arms — built by `StageLookup.build(Retriever, arm.use, arm.config)` — were never read, and a
routed rung whose arm needs `grade` was offered with `grade` unmapped. A sub-plugin reference is
now declared with `weft_retrieve.SubPlugin`, read at any depth of the config, and an optional
role or reference keeps its marker in either `| None` spelling.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import resolve
from weft_llm import LLMRole
from weft_retrieve import SubPlugin
from weft_retrieve.contract import Reranker, Retriever, Sufficiency
from weft_retrieve.engine import roles_needed
from weft_retrieve.iterative import NAME as ITERATIVE_RETRIEVAL
from weft_retrieve.iterative import IterativeRetrieval
from weft_retrieve.multi_retriever import NAME as MULTI_RETRIEVER
from weft_retrieve.multi_retriever import MultiRetriever
from weft_retrieve.payload import Candidates, QuerySet, Ranking
from weft_retrieve.sufficiency import LLM_SUFFICIENCY_NAME, LlmSufficiency

_LEAF = "stranger-leaf"
_JUDGE = "stranger-judge"
_PANEL = "stranger-panel"
_CHAIR = "stranger-chair"
_BENCH = "stranger-bench"
_HELPED = "stranger-helped"
_UNMARKED_PAIR = "stranger-unmarked-pair"
_OPTIONAL_LOSSY = "stranger-optional-lossy"
_OPTIONAL_KEPT = "stranger-optional-kept"
_NOTHING: frozenset[str] = frozenset()


class _Leaf:
    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        return Produced(value=Candidates(origin=payload.origin, lists=()))


class _JudgeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judge_role: Annotated[str, LLMRole()] = Field(default="judge", min_length=1)


class _Seat(BaseModel):
    """A composer's own reference type, deliberately spelt neither `use`/`config` nor `X_config`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    judge: Annotated[str, SubPlugin(config="settings")] = Field(min_length=1)
    settings: Mapping[str, object] | None = None


class _PanelConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seats: tuple[_Seat, ...] = Field(min_length=2)


class _ChairConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chair: _Seat


class _Bench(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bench_by: Annotated[str, LLMRole()] = Field(min_length=1)


class _BenchConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    benches: tuple[_Bench, ...] = ()


class _HelpedConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    helper: Annotated[str, SubPlugin(config="helper_settings")] | None = None
    helper_settings: Mapping[str, object] | None = None


class _UnmarkedPairConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    grader: str = Field(default=_JUDGE, min_length=1)
    grader_config: Mapping[str, object] | None = None


class _OptionalLossyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict_by: Annotated[str, LLMRole()] | None = None


class _OptionalKeptConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict_by: Annotated[str | None, LLMRole()] = None


class _Passthrough:
    config_model: ClassVar[type[BaseModel]]

    def __init__(self, config: object = None) -> None:
        self.config = config

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        del ctx
        return Produced(value=payload)


class _Judge(_Passthrough):
    config_model = _JudgeConfig


class _Panel(_Passthrough):
    config_model = _PanelConfig


class _Chair(_Passthrough):
    config_model = _ChairConfig


class _BenchPlugin(_Passthrough):
    config_model = _BenchConfig


class _Helped(_Passthrough):
    config_model = _HelpedConfig


class _UnmarkedPair(_Passthrough):
    config_model = _UnmarkedPairConfig


class _OptionalLossy(_Passthrough):
    config_model = _OptionalLossyConfig


class _OptionalKept(_Passthrough):
    config_model = _OptionalKeptConfig


def _registry() -> Registry:
    registry = Registry()
    registry.add(Retriever, MULTI_RETRIEVER, MultiRetriever, distribution="weft-retrieve")
    registry.add(Retriever, ITERATIVE_RETRIEVAL, IterativeRetrieval, distribution="weft-retrieve")
    registry.add(Sufficiency, LLM_SUFFICIENCY_NAME, LlmSufficiency, distribution="weft-retrieve")
    registry.add(Retriever, _LEAF, _Leaf, distribution="weft-example-stranger")
    for name, plugin in (
        (_JUDGE, _Judge),
        (_PANEL, _Panel),
        (_CHAIR, _Chair),
        (_BENCH, _BenchPlugin),
        (_HELPED, _Helped),
        (_UNMARKED_PAIR, _UnmarkedPair),
        (_OPTIONAL_LOSSY, _OptionalLossy),
        (_OPTIONAL_KEPT, _OptionalKept),
    ):
        registry.add(Reranker, name, plugin, distribution="weft-example-stranger")
    return registry


def _roles(
    use: str, config: Mapping[str, object] | None = None, *, contract: type[object] = Reranker
) -> frozenset[str]:
    registry = _registry()
    stage = StageDeclaration(id="stage", use=use, config=dict(config or {}))
    pipeline = Pipeline(name="composed-rung", stages=(stage,))
    resolved = resolve(pipeline, registry=registry, contracts={"stage": contract})
    return roles_needed(resolved, registry)


def _refined(role: str | None = None) -> dict[str, object]:
    config: dict[str, object] = {"sufficiency": LLM_SUFFICIENCY_NAME, "leaf": _LEAF}
    if role is not None:
        config["sufficiency_config"] = {"role": role}
    return config


def test_a_multi_retriever_arm_is_followed_into_its_sub_plugin_role() -> None:
    # Arrange — the shipped `broad-and-refined-rrf` shape: one plain arm, one looping arm.
    arms = [
        {"name": "broad", "use": _LEAF},
        {"name": "refined", "use": ITERATIVE_RETRIEVAL, "config": _refined()},
    ]

    # Act
    roles = _roles(MULTI_RETRIEVER, {"arms": arms}, contract=Retriever)

    # Assert
    assert roles == frozenset({"grade"})


def test_each_multi_retriever_arm_is_read_with_its_own_config() -> None:
    # Arrange
    arms = [
        {"name": "critical", "use": ITERATIVE_RETRIEVAL, "config": _refined("critic")},
        {"name": "checked", "use": ITERATIVE_RETRIEVAL, "config": _refined("checker")},
    ]

    # Act
    roles = _roles(MULTI_RETRIEVER, {"arms": arms}, contract=Retriever)

    # Assert
    assert roles == frozenset({"critic", "checker"})


def test_a_stranger_composer_declaring_its_references_is_followed_whatever_they_are_called() -> (
    None
):
    # Arrange
    seats = [{"judge": _JUDGE}, {"judge": _JUDGE, "settings": {"judge_role": "critic"}}]

    # Act
    roles = _roles(_PANEL, {"seats": seats})

    # Assert
    assert roles == frozenset({"judge", "critic"})


def test_a_reference_held_in_a_single_nested_model_is_followed() -> None:
    # Act
    roles = _roles(_CHAIR, {"chair": {"judge": _JUDGE, "settings": {"judge_role": "critic"}}})

    # Assert
    assert roles == frozenset({"critic"})


def test_a_role_declared_in_a_nested_model_is_read() -> None:
    # Act
    roles = _roles(_BENCH, {"benches": [{"bench_by": "first"}, {"bench_by": "second"}]})

    # Assert
    assert roles == frozenset({"first", "second"})


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"helper": _JUDGE, "helper_settings": {"judge_role": "critic"}}, frozenset({"critic"})),
        ({}, _NOTHING),
    ],
)
def test_an_optional_reference_declared_outside_the_union_is_followed_only_when_set(
    config: Mapping[str, object], expected: frozenset[str]
) -> None:
    # Act
    roles = _roles(_HELPED, config)

    # Assert
    assert roles == expected


def test_an_unmarked_name_and_config_pair_is_not_followed() -> None:
    """The declaration decides, never the `X`/`X_config` spelling — R43.30's name rule retired."""
    # Act
    roles = _roles(_UNMARKED_PAIR, {"grader_config": {"judge_role": "critic"}})

    # Assert
    assert roles == frozenset()


@pytest.mark.parametrize("plugin", [_OPTIONAL_LOSSY, _OPTIONAL_KEPT])
@pytest.mark.parametrize(
    ("config", "expected"),
    [({"verdict_by": "verdict"}, frozenset({"verdict"})), ({}, _NOTHING)],
)
def test_an_optional_role_is_read_in_either_spelling_and_skipped_when_unset(
    plugin: str, config: Mapping[str, object], expected: frozenset[str]
) -> None:
    # Act
    roles = _roles(plugin, config)

    # Assert
    assert roles == expected
