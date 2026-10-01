"""The role a rung's answer is generated under — carried repair **R44.20b**.

A rung's `roles_needed` is every role any stage calls (grade, hyde, a critic); which one of those
writes the *answer* is the last `Generator` stage's own role field — `role`, or `answer_role` for
`contradiction-check`, whose `critic_role` is not the one that writes. Read from the resolved
form, so a derived rung's `set:` counts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.route_ask import resolve_in_catalogue
from weft_engine import registry_bootstrap
from weft_generate.generating_role import generating_role
from weft_kernel.pipeline import Pipeline
from weft_kernel.resolution import ResolvedPipeline


def _resolve(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *derived: Pipeline
) -> ResolvedPipeline:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "weft.toml"
    config.write_text("", encoding="utf-8")
    deps = registry_bootstrap.build_dependencies(config_path=config)
    catalogue = {**full_catalogue(reports=deps.reports), **{item.name: item for item in derived}}
    return resolve_in_catalogue(
        catalogue[name],
        registry=deps.registry,
        catalogue=catalogue,
        reports=deps.reports,
        contributions=deps.contributions,
    )


def test_a_cited_answer_rung_generates_under_its_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Act
    role = generating_role(_resolve("retrieve-then-generate", tmp_path, monkeypatch))

    # Assert
    assert role == "generate"


def test_a_contradiction_check_generates_under_answer_role_never_its_critic_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — the critic defaults to `grade`; only the answer is the generating call.
    derived = Pipeline.model_validate(
        {
            "name": "contradiction-on-small",
            "extends": "contradiction-aware",
            "set": [{"id": "generate", "with": {"answer_role": "small", "critic_role": "grade"}}],
        }
    )

    # Act
    plain = generating_role(_resolve("contradiction-aware", tmp_path, monkeypatch))
    small = generating_role(_resolve("contradiction-on-small", tmp_path, monkeypatch, derived))

    # Assert
    assert plain == "generate"
    assert small == "small"


def test_a_refine_rung_generates_under_its_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Act
    role = generating_role(_resolve("draft-then-refine", tmp_path, monkeypatch))

    # Assert
    assert role == "generate"


def test_a_derived_rung_that_sets_the_role_generates_under_that_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    derived = Pipeline.model_validate(
        {
            "name": "whole-corpus-on-long-context",
            "extends": "whole-corpus-wide-then-generate",
            "set": [{"id": "generate", "with": {"role": "long-context"}}],
        }
    )

    # Act
    role = generating_role(_resolve("whole-corpus-on-long-context", tmp_path, monkeypatch, derived))

    # Assert
    assert role == "long-context"


def test_a_pipeline_whose_last_stage_is_no_generator_has_no_generating_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Act — a retrieval-only rung ends in a repack, never a Generator.
    role = generating_role(_resolve("lexical-retrieve", tmp_path, monkeypatch))

    # Assert
    assert role is None
