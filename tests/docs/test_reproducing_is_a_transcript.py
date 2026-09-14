"""`docs/REPRODUCING.md` is a transcript, so no command on it carries a placeholder.

`docs/internal/lessons.md` `L22.10`: the page once said it carried only commands that were run, and
its *Run it* block was `weft eval run <pipeline> <corpus directory> …` — a command nobody can have
run, because a `<placeholder>` is not a value. That is the one half of the lesson a check can see;
whether a count on the page was measured against the published asset rather than a copy is not.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

PAGE: Final[Path] = Path(__file__).resolve().parents[2] / "docs" / "REPRODUCING.md"

_FENCED: Final[re.Pattern[str]] = re.compile(r"^```[a-z]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"<[a-z][a-z _-]*>")


def placeholders_in(markdown: str) -> list[str]:
    return [found for block in _FENCED.findall(markdown) for found in _PLACEHOLDER.findall(block)]


def test_the_page_has_commands_to_check() -> None:
    # Arrange
    text = PAGE.read_text(encoding="utf-8")

    # Act
    blocks = _FENCED.findall(text)

    # Assert
    assert len(blocks) >= 5, f"{PAGE.name} parsed to {len(blocks)} fenced block(s)"


def test_no_fenced_command_on_the_page_carries_a_placeholder() -> None:
    # Arrange
    text = PAGE.read_text(encoding="utf-8")

    # Act
    found = placeholders_in(text)

    # Assert
    assert not found, f"{PAGE.name} is a transcript and a fenced block holds {found}"


def test_the_check_can_actually_fail() -> None:
    # Arrange
    planted = "```console\n$ weft eval run <pipeline> <corpus directory>\n```\n"

    # Act
    found = placeholders_in(planted)

    # Assert
    assert found == ["<pipeline>", "<corpus directory>"]
