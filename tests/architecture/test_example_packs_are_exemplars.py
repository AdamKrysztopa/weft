"""The example packs declare what a real pack declares — ledger task **6.26**.

An `examples/weft-example-*` pack is not a demo. `07` §2 and fitness function 9 make each one the
*evidence* that a contract can be implemented from outside the workspace, and `08`'s pack-author
guide teaches from them. Whatever they declare is what the next person writes.

**Measured at task 6.3 and repaired here: six of the seven declared bare sibling names.** Eighteen
requirements between `weft-example-chunker`, `-command`, `-ingest`, `-llm`, `-metric` and `-query`
read `"weft-kernel"` with no bound at all — precisely the shape fitness function 10(b) exists to
abolish, and precisely what G9 settled against: *"a version requirement **is** the dependency
specifier, so `0.0.0` ends, bare names end, ranges are `>=X,<MAJOR+1`"*. Only
`weft-example-graph`, written after G9 landed, carried bounds.

**Why FF10(b) does not already cover this, and why widening it would be wrong.** `01` scopes that
clause to *"a property over the workspace"*, and an example pack is deliberately **not** a
workspace member — that is fitness function 9(a), the whole point of the out-of-tree arrangement.
Widening a settled clause to reach something it was written to exclude is the proviso `L5.32`
refuses. So this is a separate check with a separate reason: not *"the release must be
installable"*, which is FF10(b)'s, but *"the exemplar must teach the rule"*.

**The bound is a floor with a compatible ceiling, matching what the first-party packs declare.** A
third party reading `weft-kernel>=0.1.0,<1.0.0` learns the rule from the example; one reading
`weft-kernel` learns that bounds are optional, and their pack breaks on the kernel's next major
with nothing to point at.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Final, cast

from packaging.requirements import Requirement

from .conftest import REPO_ROOT

EXAMPLES: Final[Path] = REPO_ROOT / "examples"
PACKAGES: Final[Path] = REPO_ROOT / "packages"

#: The specifier operators that place a lower bound — the same set fitness function 10(b) uses,
#: for the same reason: `01` names a floor, a compatible range or an exact pin, and all three pin
#: the bottom.
LOWER_BOUND_OPERATORS: Final[frozenset[str]] = frozenset({">=", ">", "==", "===", "~="})


def _project(manifest: Path) -> dict[str, Any]:
    with manifest.open("rb") as handle:
        document: dict[str, Any] = tomllib.load(handle)
    return cast("dict[str, Any]", document.get("project", {}))


def first_party_names() -> frozenset[str]:
    """Every distribution under `packages/`, read off its own manifest."""
    names: set[str] = set()
    for manifest in sorted(PACKAGES.glob("*/pyproject.toml")):
        name = _project(manifest).get("name")
        if isinstance(name, str):
            names.add(name)
    return frozenset(names)


def example_requirements_on_first_party() -> list[tuple[str, Requirement]]:
    """Every `(example pack, requirement)` where an example depends on something first-party."""
    first_party = first_party_names()
    found: list[tuple[str, Requirement]] = []
    for manifest in sorted(EXAMPLES.glob("*/pyproject.toml")):
        project = _project(manifest)
        name = project.get("name")
        if not isinstance(name, str):
            continue
        for text in cast("list[str]", project.get("dependencies", [])):
            requirement = Requirement(text)
            if requirement.name in first_party:
                found.append((name, requirement))
    return found


def test_every_example_pack_bounds_the_first_party_packages_it_depends_on() -> None:
    """The property. G9: bare names end."""
    # Arrange
    requirements = example_requirements_on_first_party()

    # Act
    unbounded = [
        f"{pack} → {requirement}"
        for pack, requirement in requirements
        if not any(
            specifier.operator in LOWER_BOUND_OPERATORS for specifier in requirement.specifier
        )
    ]

    # Assert — non-vacuity first: a reader that found no examples would report no violations.
    assert requirements, (
        f"no example pack under {EXAMPLES} was found depending on anything first-party. The "
        f"reader is wrong, not the examples — every one of them implements a first-party "
        f"contract, which is what fitness function 9 makes them for."
    )
    assert len({pack for pack, _ in requirements}) >= 6, (
        "fewer example packs were read than exist; the glob is wrong"
    )
    assert not unbounded, (
        f"{unbounded} declare a first-party dependency with no bound. G9 settled that a version "
        f"requirement **is** the dependency specifier and bare names end. An example pack is what "
        f"the next pack author copies, so an unbounded requirement here teaches that bounds are "
        f"optional — and their pack breaks on the next major with nothing to point at."
    )


def test_the_check_can_actually_fail() -> None:
    """Planted, because the tree agrees once this task lands (`docs/lessons.md` L5.19).

    Through the real predicate, on the two shapes that separate a bound from a specifier: a bare
    name, and a ceiling with no floor — which is a specifier and not a bound, since it still
    permits every older release.
    """
    # Arrange
    planted = [
        Requirement("weft-kernel"),
        Requirement("weft-kernel<1.0.0"),
        Requirement("weft-kernel>=0.1.0,<1.0.0"),
    ]

    # Act
    unbounded = [
        str(requirement)
        for requirement in planted
        if not any(
            specifier.operator in LOWER_BOUND_OPERATORS for specifier in requirement.specifier
        )
    ]

    # Assert
    assert unbounded == ["weft-kernel", "weft-kernel<1.0.0"]
