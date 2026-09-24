"""The composed Phase 32 document — ledger task **32.9**.

`context-construction-then-generate` composes all three rerankers in the order the plan argues
(`fix-plans/09` → *What it becomes*): duplicates are dropped before `mmr` spends a selection on
them, and `adjacent-chunks` runs after selection so neighbours never compete for a slot. Its
`repack` keeps a token budget and no `top_n: 8`, which would cut the widened list back before
the budget ever ran (the decision agent's finding at the opening).
"""

from pathlib import Path

import pytest

from weft_cli.route_ask import resolve_named_pipeline
from weft_engine import registry_bootstrap
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage

_NAME = "context-construction-then-generate"


def _int_field(stage: ResolvedStage, name: str) -> int:
    value = getattr(stage.config, name)
    assert isinstance(value, int)
    return value


def _resolved(tmp_path: Path) -> ResolvedPipeline:
    config = tmp_path / "weft.toml"
    config.write_text("", encoding="utf-8")
    deps = registry_bootstrap.build_dependencies(config_path=config)
    return resolve_named_pipeline(_NAME, registry=deps.registry, reports=deps.reports)


def test_the_three_rerankers_run_between_fusion_and_packing_in_the_argued_order(
    tmp_path: Path,
) -> None:
    # Act
    uses = [stage.use for stage in _resolved(tmp_path).stages]

    # Assert
    assert uses.index("shingle-resemblance") < uses.index("mmr") < uses.index("adjacent-chunks")
    assert uses.index("single-list") < uses.index("shingle-resemblance")
    assert uses.index("adjacent-chunks") < uses.index("repack") < uses.index("cited-answer")


def test_packing_is_bounded_by_tokens_and_not_cut_back_to_eight(tmp_path: Path) -> None:
    # Act
    pack = next(stage for stage in _resolved(tmp_path).stages if stage.use == "repack")

    # Assert
    budget = getattr(pack.config, "budget_tokens", None)
    top_n = getattr(pack.config, "top_n", None)
    assert budget is not None and budget > 0
    assert top_n is None or top_n > 8


def test_mmr_selects_before_expansion_so_the_widened_list_is_bounded(tmp_path: Path) -> None:
    # Act
    diversify = next(stage for stage in _resolved(tmp_path).stages if stage.use == "mmr")

    # Assert — without a `top_n` on `mmr`, expansion would widen every retrieved hit.
    assert getattr(diversify.config, "top_n", None) is not None


@pytest.mark.parametrize(
    "name", ["adjacent-chunks-then-generate", "context-construction-then-generate"]
)
def test_the_generator_reads_every_passage_packing_kept(tmp_path: Path, name: str) -> None:
    """`32.10`'s first run: `cited-answer` reads at most `max_passages` (8) from the front of
    what `repack` hands it, and `method: reverse` puts the best passage last — so the widened
    24 were cut to the eight worst, and both arms scored far below the baseline for it.
    """
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text("", encoding="utf-8")
    deps = registry_bootstrap.build_dependencies(config_path=config)

    # Act
    stages = resolve_named_pipeline(name, registry=deps.registry, reports=deps.reports).stages
    pack = next(stage for stage in stages if stage.use == "repack")
    generate = next(stage for stage in stages if stage.use == "cited-answer")

    # Assert
    assert _int_field(generate, "max_passages") >= _int_field(pack, "top_n")
