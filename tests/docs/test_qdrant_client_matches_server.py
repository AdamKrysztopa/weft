"""The `qdrant` extra allows only clients the Qdrant server this project pins accepts — `R22.13`.

`weft-rag[qdrant]==2.7.0` resolved `qdrant-client` 1.19.0 on a fresh install, and that client warned
on every call that it is incompatible with `qdrant/qdrant:v1.12.4`, the server `compose.yaml` and
`docs/REPRODUCING.md` pin. The client's own rule is that majors match and minors differ by at most
one. The lockfile's 1.13.3 hid it from every run in this tree.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PYPROJECT: Final[Path] = REPO_ROOT / "packages" / "weft-rag" / "pyproject.toml"
PINNED_SERVER_PAGES: Final[tuple[Path, ...]] = (
    REPO_ROOT / "compose.yaml",
    REPO_ROOT / "docs" / "REPRODUCING.md",
)

_SERVER: Final[re.Pattern[str]] = re.compile(r"qdrant/qdrant:v(\d+)\.(\d+)\.\d+")
_FLOOR: Final[re.Pattern[str]] = re.compile(r">=\s*(\d+)\.(\d+)")
_CEILING: Final[re.Pattern[str]] = re.compile(r"<\s*(\d+)\.(\d+)")


def client_specifiers(pyproject_text: str) -> list[str]:
    extras = tomllib.loads(pyproject_text)["project"]["optional-dependencies"]
    return [
        requirement
        for requirements in extras.values()
        for requirement in requirements
        if requirement.startswith("qdrant-client")
    ]


def incompatibilities(specifier: str, server: tuple[int, int]) -> list[str]:
    """What lets `specifier` resolve a client more than one minor away from `server`."""
    major, minor = server
    problems: list[str] = []
    ceiling = _CEILING.search(specifier)
    if ceiling is None:
        problems.append(f"{specifier!r} has no upper bound")
    elif (int(ceiling[1]), int(ceiling[2])) > (major, minor + 2):
        problems.append(f"{specifier!r} allows clients past {major}.{minor + 1}")
    floor = _FLOOR.search(specifier)
    if floor is None or (int(floor[1]), int(floor[2])) < (major, max(minor - 1, 0)):
        problems.append(f"{specifier!r} allows clients below {major}.{max(minor - 1, 0)}")
    return problems


def test_every_page_pins_the_same_server() -> None:
    # Arrange
    pages = {
        page: _SERVER.findall(page.read_text(encoding="utf-8")) for page in PINNED_SERVER_PAGES
    }

    # Act
    versions = {version for found in pages.values() for version in found}

    # Assert
    assert all(pages.values()), f"a page pins no Qdrant server: {pages}"
    assert len(versions) == 1, f"the pages pin different Qdrant servers: {pages}"


def test_the_qdrant_extra_resolves_only_clients_that_server_accepts() -> None:
    # Arrange
    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    found = _SERVER.search(compose)
    assert found is not None
    server = (int(found[1]), int(found[2]))
    specifiers = client_specifiers(PYPROJECT.read_text(encoding="utf-8"))

    # Act
    problems = [problem for spec in specifiers for problem in incompatibilities(spec, server)]

    # Assert
    assert specifiers, "no extra declares qdrant-client, so this check compares nothing"
    assert not problems, problems


def test_the_check_can_actually_fail() -> None:
    # Arrange
    server = (1, 12)

    # Act
    unbounded = incompatibilities("qdrant-client>=1.12", server)
    too_new = incompatibilities("qdrant-client>=1.12,<1.20", server)
    bounded = incompatibilities("qdrant-client>=1.12,<1.14", server)

    # Assert
    assert unbounded == ["'qdrant-client>=1.12' has no upper bound"]
    assert too_new == ["'qdrant-client>=1.12,<1.20' allows clients past 1.13"]
    assert bounded == []
