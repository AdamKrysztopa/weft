"""Task 45.5 — every "about N×" a reader is shown names the experiment that measured it.

The whole-corpus rung costs about 170× one search in `whole-corpus-en` and about 157× in
`global-synthesis`; both are right, and a ratio that names neither reads as one number that two
pages disagree about. A ratio passes when the paragraph (or table) holding it names an experiment
directory under `eval/experiments/`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_RATIO: Final[re.Pattern[str]] = re.compile(r"(?:about|~) ?\d+(?:×| times)", re.IGNORECASE)
_EXPERIMENTS: Final[frozenset[str]] = frozenset(
    path.stem for path in (_ROOT / "eval" / "experiments").glob("*.toml")
)


def _pages() -> list[Path]:
    pipelines = sorted((_ROOT / "packages").glob("*/src/*/pipelines/*.yaml"))
    return [_ROOT / "README.md", *sorted((_ROOT / "manual").glob("*.md")), *pipelines]


def unnamed_ratios(text: str, experiments: frozenset[str]) -> list[str]:
    """Each paragraph holding a cost ratio but naming no experiment, by its first ratio."""
    unnamed: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        ratio = _RATIO.search(paragraph)
        if ratio is None:
            continue
        named = re.findall(r"`(?:eval/experiments/)?([a-z0-9-]+)(?:/[^`]*)?`", paragraph)
        if not experiments.intersection(named):
            unnamed.append(ratio.group(0))
    return unnamed


@pytest.mark.parametrize("page", _pages(), ids=lambda path: str(path.relative_to(_ROOT)))
def test_every_cost_ratio_names_its_experiment(page: Path) -> None:
    # Act
    unnamed = unnamed_ratios(page.read_text(encoding="utf-8"), _EXPERIMENTS)

    # Assert
    assert unnamed == [], f"{page.relative_to(_ROOT)}: name the experiment beside {unnamed}"


def test_the_check_can_actually_fail() -> None:
    # Arrange
    page = "It costs about 170 times the prompt tokens.\n\nAbout 157× in `global-synthesis`."

    # Act
    unnamed = unnamed_ratios(page, frozenset({"global-synthesis"}))

    # Assert
    assert unnamed == ["about 170 times"]
