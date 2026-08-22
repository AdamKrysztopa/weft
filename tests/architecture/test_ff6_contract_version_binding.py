"""Fitness function 6 — a contract version's movement agrees with the distribution
publishing it.

`docs/01-high-level-plan.md` states FF6 in one sentence: "Contracts are versioned. Every
published contract carries a version, and a check fails on a changed contract whose
version did not move." Task **5.2a** (`docs/build-ledger.md`) sharpens that: not that the
constant moved, but that its movement *agrees with the version of the distribution
publishing it* — the mechanical half of G9 (`docs/09-release.md` §2.3): "a contract major
forces a major of the distribution that publishes it, a contract minor forces at least a
minor, and a distribution publishing several takes the maximum." That reduces to one
invariant, checked per contract rather than only against the maximum so a distribution
publishing several is named for whichever one it under-declared: **the distribution
version must be at least as high as every contract version it publishes**, compared as
plain `(major, minor, patch)` tuples.

**Two independent sources, on purpose (`docs/lessons.md` L5.6).** L5.6 found
`weft_eval/prompts.py` declaring a version by importing the very constant it was supposed
to check against — a declaration that can never disagree with itself. This check reads
the contract version by parsing `contract.py` as text (`ast`, never `import`, so a pack's
own import-time side effects never run just to read a version number) and reads the
distribution version from that distribution's own `pyproject.toml` via `tomllib` — a
different file, a different parser, a different fact. `test_the_check_can_actually_fail`
plants a disagreeing pair in a throwaway tree and proves the two facts can diverge, in the
spirit of `test_ff9_extension_from_outside.py::test_the_grep_can_actually_fail`.

**Deliberately excludes `*_SCHEMA_VERSION`.** `weft_store.contract.RECONCILE_REPORT_SCHEMA_VERSION`
matches the naming family but is not a contract in G9's sense: it is the second axis §S5
of `docs/README.md`'s decision log added — a version carried *in stored data*, read back
by a pack that may not be the one installed, never available as a live module constant at
the read site at all. Binding it to a distribution version the way a contract is bound
would be meaningless, since the whole reason it exists is that the distribution version
is *not* recoverable when the data is read. `test_schema_version_constants_are_ignored`
pins the exclusion down as a fact about this check rather than an accident of the regex.

**What this check does not attempt, stated honestly rather than faked.** `01`'s sentence
also asks for "a check [that] fails on a changed contract whose version did not move" —
read literally, that needs a stored shape to diff the working tree against. Nothing in
this repository is tagged, released or lock-frozen before Phase 6 (`09` §2.2), so any
snapshot taken today would be this commit's own tree and would rot at the very next
accepted bump, catching nothing a reviewer had not already seen. What is checked instead,
and is stable rather than a snapshot: at every commit, a contract's version can never have
outrun the distribution that publishes it — which is what actually matters, because a
version that moved without a compatible distribution bump is a broken dependency
specifier (fitness function 6's other half, enforced by the ranges task 5.2a also writes),
not merely an unrecorded fact. A commit that bumps a contract constant without bumping its
distribution's `pyproject.toml` fails this check immediately; one that forgets to bump the
contract constant at all is outside what any check here can see without human judgement
about what "changed" means for a Protocol body, and is recorded as a known gap rather than
asserted shut.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT, table_at

PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: A published contract's version constant, by this project's own naming convention
#: (`grep -rn "_CONTRACT_VERSION\|_AST_VERSION"` in the task brief). `_SCHEMA_VERSION` is
#: excluded on purpose — see the module docstring.
_VERSION_CONST_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]*_(CONTRACT|AST)_VERSION$")
_SCHEMA_CONST_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]*_SCHEMA_VERSION$")
_SEMVER_RE: Final[re.Pattern[str]] = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True, slots=True)
class ContractVersion:
    """One `*_CONTRACT_VERSION` / `*_AST_VERSION` constant, and the distribution
    (a `packages/<name>` directory) whose `contract.py` declares it."""

    distribution: str
    constant: str
    version: str


@dataclass(frozen=True, slots=True)
class Disagreement:
    """A contract version that has moved further than the distribution publishing it."""

    distribution: str
    constant: str
    contract_version: str
    distribution_version: str


def semver(value: str) -> tuple[int, int, int]:
    """Parse a plain `X.Y.Z` string. Raises on anything else — a pre-release suffix or a
    two-part version is not a fact this check can compare, and refusing loudly beats
    guessing at an ordering."""
    match = _SEMVER_RE.match(value)
    if match is None:
        raise ValueError(f"not a plain X.Y.Z semver string: {value!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def contract_versions_in(root: Path) -> list[ContractVersion]:
    """Every published contract-version constant under `root/<distribution>/src/*/contract.py`.

    Read by parsing the AST as text, never by `import` — the module docstring's argument
    against L5.6. `root` is a parameter, not a constant, so `test_the_check_can_actually_fail`
    can point this same function at a throwaway tree instead of the real one.
    """
    found: list[ContractVersion] = []

    for contract_file in sorted(root.glob("*/src/*/contract.py")):
        distribution = contract_file.relative_to(root).parts[0]
        tree = ast.parse(contract_file.read_text(encoding="utf-8"), filename=str(contract_file))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                continue

            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if _SCHEMA_CONST_RE.match(target.id):
                    continue
                if _VERSION_CONST_RE.match(target.id):
                    found.append(ContractVersion(distribution, target.id, node.value.value))

    return found


def distribution_version(root: Path, distribution: str) -> str:
    """The `[project].version` a distribution's own `pyproject.toml` declares — the
    independent second source the module docstring's argument requires."""
    pyproject = root / distribution / "pyproject.toml"

    with pyproject.open("rb") as handle:
        config = tomllib.load(handle)

    project = table_at(config, "project")
    version = project.get("version")

    if not isinstance(version, str):
        raise TypeError(f"{pyproject} has no string [project].version")

    return version


def disagreements(root: Path) -> list[Disagreement]:
    """Every contract version that outran the distribution publishing it.

    `docs/09-release.md` §2.3: "a contract major forces a major of the distribution that
    publishes it, a contract minor forces at least a minor, and a distribution publishing
    several takes the maximum." Checked per contract, against that contract's own
    distribution, rather than only against the maximum — so a distribution publishing two
    contracts is named for whichever one it left behind, not only the higher of the two.
    """
    problems: list[Disagreement] = []
    by_distribution: dict[str, list[ContractVersion]] = defaultdict(list)

    for contract_version in contract_versions_in(root):
        by_distribution[contract_version.distribution].append(contract_version)

    for distribution, versions in by_distribution.items():
        dist_tuple = semver(distribution_version(root, distribution))

        for contract_version in versions:
            if semver(contract_version.version) > dist_tuple:
                problems.append(
                    Disagreement(
                        distribution=distribution,
                        constant=contract_version.constant,
                        contract_version=contract_version.version,
                        distribution_version=distribution_version(root, distribution),
                    )
                )

    return problems


def protocol_names_in(contract_file: Path) -> list[str]:
    """Every `@runtime_checkable` class declared in one `contract.py` — used to assert
    that a module publishing a Protocol also publishes a version for it, without
    enumerating contract names anywhere (CLAUDE.md: no closed enumeration of a thing a
    pack could add to)."""
    tree = ast.parse(contract_file.read_text(encoding="utf-8"), filename=str(contract_file))
    names: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if any(_is_runtime_checkable(decorator) for decorator in node.decorator_list):
            names.append(node.name)

    return names


def _is_runtime_checkable(decorator: ast.expr) -> bool:
    if isinstance(decorator, ast.Name):
        return decorator.id == "runtime_checkable"
    if isinstance(decorator, ast.Attribute):
        return decorator.attr == "runtime_checkable"
    return False


def test_every_published_contract_agrees_with_its_distribution_version() -> None:
    problems = disagreements(PACKAGES_ROOT)

    assert not problems, (
        "a contract version has moved further than the distribution publishing it, so "
        f"the dependency range a resolver enforces can no longer be trusted: {problems}. "
        "docs/09-release.md §2.3: a contract major forces a distribution major, a "
        "contract minor forces at least a minor, and a distribution publishing several "
        "takes the maximum."
    )


def test_every_module_publishing_a_protocol_declares_a_version_constant() -> None:
    versions_by_file: dict[Path, list[ContractVersion]] = defaultdict(list)
    for contract_version in contract_versions_in(PACKAGES_ROOT):
        distribution_dir = PACKAGES_ROOT / contract_version.distribution
        versions_by_file[distribution_dir].append(contract_version)

    missing: list[Path] = []
    for contract_file in sorted(PACKAGES_ROOT.glob("*/src/*/contract.py")):
        if not protocol_names_in(contract_file):
            continue
        distribution_dir = contract_file.parents[2]
        if not versions_by_file.get(distribution_dir):
            missing.append(contract_file)

    assert not missing, (
        f"{[str(path) for path in missing]} declare a @runtime_checkable Protocol but no "
        f"'*_CONTRACT_VERSION' or '*_AST_VERSION' constant — a published contract with "
        f"nothing for fitness function 6 to bind to a distribution version."
    )


def test_schema_version_constants_are_ignored() -> None:
    # Arrange — `RECONCILE_REPORT_SCHEMA_VERSION` is exactly this shape in the real tree:
    # a stored-data schema version, not a contract, deliberately excluded by the module
    # docstring's argument. Assert the exclusion as a fact about the naming convention,
    # not only as an accident of today's one instance.
    assert not _VERSION_CONST_RE.match("RECONCILE_REPORT_SCHEMA_VERSION")
    assert _SCHEMA_CONST_RE.match("RECONCILE_REPORT_SCHEMA_VERSION")


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    # Arrange — plant a contract version that outruns its own distribution's pyproject
    # version, the everyday defect this check exists to catch.
    package_dir = tmp_path / "weft-fake" / "src" / "weft_fake"
    package_dir.mkdir(parents=True)
    (package_dir / "contract.py").write_text('FAKE_CONTRACT_VERSION = "2.0.0"\n', encoding="utf-8")
    (tmp_path / "weft-fake" / "pyproject.toml").write_text(
        '[project]\nname = "weft-fake"\nversion = "1.0.0"\n', encoding="utf-8"
    )

    # Act
    problems = disagreements(tmp_path)

    # Assert
    assert problems == [
        Disagreement(
            distribution="weft-fake",
            constant="FAKE_CONTRACT_VERSION",
            contract_version="2.0.0",
            distribution_version="1.0.0",
        )
    ], (
        "the disagreement check did not find a version planted for exactly this purpose; "
        "a check that stopped being able to fail would pass on a tree where a contract "
        "outran the distribution version that is supposed to be its enforceable shadow"
    )


def test_a_distribution_version_that_keeps_pace_is_not_a_disagreement(tmp_path: Path) -> None:
    # Arrange — the ordinary, passing case: distribution version equal to the contract
    # version it publishes, so the check does not fire on agreement.
    package_dir = tmp_path / "weft-fake" / "src" / "weft_fake"
    package_dir.mkdir(parents=True)
    (package_dir / "contract.py").write_text('FAKE_CONTRACT_VERSION = "1.0.0"\n', encoding="utf-8")
    (tmp_path / "weft-fake" / "pyproject.toml").write_text(
        '[project]\nname = "weft-fake"\nversion = "1.0.0"\n', encoding="utf-8"
    )

    # Act / Assert
    assert disagreements(tmp_path) == []
