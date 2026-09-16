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
LOCKFILE: Final[Path] = REPO_ROOT / "uv.lock"
PINNED_SERVER_PAGES: Final[tuple[Path, ...]] = (
    REPO_ROOT / "compose.yaml",
    REPO_ROOT / "docs" / "REPRODUCING.md",
)

_SERVER: Final[re.Pattern[str]] = re.compile(r"qdrant/qdrant:v(\d+)\.(\d+)\.\d+")
_FLOOR: Final[re.Pattern[str]] = re.compile(r">=\s*(\d+)\.(\d+)")
_CEILING: Final[re.Pattern[str]] = re.compile(r"<\s*(\d+)\.(\d+)")

#: The version `uv` actually resolved, which is the only statement of the pin that says what a
#: fresh `uv sync` will really install. Ledger task **31.4**.
_LOCK_RESOLVED: Final[re.Pattern[str]] = re.compile(
    r'name = "qdrant-client"\nversion = "(\d+)\.(\d+)\.\d+"'
)


def one_minor_apart(client: tuple[int, int], server: tuple[int, int]) -> bool:
    """The client's own compatibility rule: majors match, minors differ by at most one.

    Stated here rather than imported from the client, deliberately: importing the rule from the
    package whose version is under test is `L5.6`'s one-source comparison, which cannot disagree.
    """
    return client[0] == server[0] and abs(client[1] - server[1]) <= 1


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


def test_the_lockfile_resolves_a_client_the_pinned_server_accepts() -> None:
    """Ledger task **31.4** — the fifth statement of the pin, and the one nothing read.

    `test_every_page_pins_the_same_server` walks `compose.yaml` and `REPRODUCING.md`;
    `client_specifiers` walks `pyproject.toml`'s extras. **`uv.lock` was covered by neither**,
    and it is the only one of the five that says what a fresh `uv sync` will actually install —
    a specifier describes a range, a lockfile names a version. `R22.13` is precisely this defect
    arriving through a door that was still unwatched: the extras' range was correct and the
    resolution was not.
    """
    # Arrange
    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    pinned = _SERVER.search(compose)
    assert pinned is not None
    server = (int(pinned[1]), int(pinned[2]))

    # Act
    resolved = _LOCK_RESOLVED.search(LOCKFILE.read_text(encoding="utf-8"))

    # Assert
    assert resolved is not None, (
        "uv.lock names no resolved qdrant-client, so this check compares nothing — the floor "
        "`08` §3 requires before a coverage check may pass."
    )
    client = (int(resolved[1]), int(resolved[2]))
    assert one_minor_apart(client, server), (
        f"uv.lock resolves qdrant-client {client[0]}.{client[1]}.x against server "
        f"{server[0]}.{server[1]}.x, which the client refuses: majors must match and minors "
        f"differ by at most one."
    )


def test_the_lockfile_check_can_actually_fail() -> None:
    # Arrange / Act / Assert — the assertion above passes today (client 1.13 against server
    # 1.12), so without this its green says nothing about whether it is looking. `R22.13`'s own
    # resolution is the disagreeing case.
    assert one_minor_apart((1, 13), (1, 12))
    assert not one_minor_apart((1, 19), (1, 12))
    assert not one_minor_apart((2, 12), (1, 12))
