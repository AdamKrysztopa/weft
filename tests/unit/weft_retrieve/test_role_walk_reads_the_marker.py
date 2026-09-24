"""Repair **R43.35**: `roles_needed` reads a model role from a field declared with `LLMRole`.

R43.30's walk read four first-party field names, so a stranger's `judge_role` was missed and its
rung refused after a paid call. The settled remedy is a declared marker read from the field's
metadata: the name no longer decides, in either direction.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import resolve
from weft_llm import LLMRole
from weft_retrieve.contract import Reranker
from weft_retrieve.engine import roles_needed
from weft_retrieve.payload import Ranking

_JUDGE = "stranger-judge"
_VERDICT = "stranger-verdict"
_UNMARKED = "stranger-unmarked"
_PARENT = "stranger-parent"


class _JudgeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judge_role: Annotated[str, LLMRole()] = Field(default="judge", min_length=1)


class _VerdictConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict_by: Annotated[str, LLMRole()] = Field(default="verdict", min_length=1)


class _UnmarkedConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str = Field(default="unmarked", min_length=1)


class _ParentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    grader: str = Field(default=_JUDGE, min_length=1)
    grader_config: Mapping[str, object] | None = None


class _Passthrough:
    config_model: ClassVar[type[BaseModel]]

    def __init__(self, config: object = None) -> None:
        self.config = config

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        del ctx
        return Produced(value=payload)


class _Judge(_Passthrough):
    config_model = _JudgeConfig


class _Verdict(_Passthrough):
    config_model = _VerdictConfig


class _Unmarked(_Passthrough):
    config_model = _UnmarkedConfig


class _Parent(_Passthrough):
    config_model = _ParentConfig


def _registry() -> Registry:
    registry = Registry()
    for name, plugin in (
        (_JUDGE, _Judge),
        (_VERDICT, _Verdict),
        (_UNMARKED, _Unmarked),
        (_PARENT, _Parent),
    ):
        registry.add(Reranker, name, plugin, distribution="weft-example-stranger")
    return registry


def _roles(use: str, config: Mapping[str, object] | None = None) -> frozenset[str]:
    registry = _registry()
    stage = StageDeclaration(id="rerank", use=use, config=dict(config or {}))
    pipeline = Pipeline(name="stranger-rung", stages=(stage,))
    resolved = resolve(pipeline, registry=registry, contracts={"rerank": Reranker})
    return roles_needed(resolved, registry)


def test_a_stranger_field_declared_as_a_role_is_read_at_its_default() -> None:
    # Act
    roles = _roles(_JUDGE)

    # Assert
    assert roles == frozenset({"judge"})


def test_a_stranger_role_set_in_the_stage_config_is_the_one_read() -> None:
    # Act
    roles = _roles(_JUDGE, {"judge_role": "critic"})

    # Assert
    assert roles == frozenset({"critic"})


def test_a_marked_field_whose_name_does_not_end_in_role_is_read() -> None:
    # Act
    roles = _roles(_VERDICT)

    # Assert
    assert roles == frozenset({"verdict"})


def test_a_field_named_role_without_the_marker_is_not_read_as_a_role() -> None:
    # Act
    roles = _roles(_UNMARKED)

    # Assert
    assert roles == frozenset()


def test_the_walk_follows_a_named_sibling_into_its_marked_field() -> None:
    # Act
    roles = _roles(_PARENT, {"grader_config": {"judge_role": "critic"}})

    # Assert
    assert roles == frozenset({"critic"})


def test_a_named_sibling_left_unconfigured_is_read_at_its_own_default() -> None:
    # Act
    roles = _roles(_PARENT)

    # Assert
    assert roles == frozenset({"judge"})
