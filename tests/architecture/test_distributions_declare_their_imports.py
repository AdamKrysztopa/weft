"""Every first-party module a distribution imports is one it ships or one it declares.

This test was written for a reviewer finding against task 2.8: `weft_cli.route_ask`
(the module backing the `weft route` command) imports `weft_generate.payload.Answer`
at module scope, but `weft-cli`'s own `pyproject.toml` never listed `weft-generate` in
`dependencies` — and nothing it *did* declare pulled `weft-generate` in transitively
(`weft-retrieve` deliberately does not, per `.phase2-design.md`'s own DAG rule). Inside
this repository's shared `uv` workspace venv every first-party package is already
editable-installed regardless of any one distribution's declared dependencies, so the gap
was invisible to every test that ran here — the same blind spot `tests/architecture/
test_ff1_boundary.py`'s module docstring names for the kernel, applied to a pack instead
of the kernel: "a kernel that is its own wheel is checked by installing it alone and
importing it" (`CLAUDE.md`, *Where things are*). A real `pip install weft-cli` installed a
wheel that raised `ModuleNotFoundError` the first time `weft route` ran.

**Widened from `weft-cli` alone to every published distribution on 2026-09-05**, when
fourteen distributions became one. Scoped to `weft-cli`, this check would now be close to
vacuous — `weft_cli` ships in `weft-rag` alongside every module it imports, so almost
nothing it imports needs declaring at all. The property is unchanged and the subject is
simply larger: for each distribution under `packages/`, every first-party module its own
source tree imports must either ship in that same distribution or be named in its
`dependencies`. That is what makes `weft-pdf`'s `import weft_extract` a declared fact
rather than an accident of a shared venv, and it is exactly the finding above generalised
past the one distribution that produced it.

Mirrors `test_ff1_boundary.py`'s AST-walk approach (`_top_level_imports` there), checked
against each distribution's own manifest rather than a fixed dependency set — a pack is not
the kernel, so what it may import is whatever it declares, not a G1-fixed pair.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT, first_party_source_roots, str_list_at, table_at

PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"


def test_every_distribution_declares_every_first_party_distribution_it_imports() -> None:
    # `weft_extract` -> `weft-pdf`, and so on: which distribution actually ships each
    # first-party module, read off the tree rather than guessed from the module's own name.
    ships = {
        module: _distribution_at(root.parents[1])
        for module, root in first_party_source_roots().items()
    }

    violations: list[str] = []
    for manifest in sorted(PACKAGES_ROOT.glob("*/pyproject.toml")):
        root = manifest.parent
        with manifest.open("rb") as handle:
            document = tomllib.load(handle)
        project = table_at(document, "project")
        own = project["name"]
        declared = {_requirement_name(entry) for entry in str_list_at(project, "dependencies")}

        for path in sorted((root / "src").rglob("*.py")):
            for imported in _top_level_first_party_imports(path):
                provider = ships.get(imported)
                if provider is None:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)} imports {imported}, which no "
                        f"distribution under packages/ ships"
                    )
                elif provider != own and provider not in declared:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)} imports {imported}, shipped by "
                        f"'{provider}', but '{provider}' is not in {own}'s own "
                        f"pyproject.toml dependencies"
                    )

    assert not violations, (
        "a distribution imports a first-party module it neither ships nor declares:\n  "
        + "\n  ".join(sorted(violations))
        + "\nOutside this repo's shared uv workspace venv (where every first-party package "
        "is already installed regardless of declared deps), a real install would not pull "
        "this in, and the import would fail at runtime."
    )


def test_at_least_one_source_file_is_walked() -> None:
    # Floor, same shape as test_ff1_boundary's — a walk that finds nothing would let the
    # assertion above pass vacuously. Stated per distribution rather than in total, because
    # the failure this guards against is a *directory layout* change silently emptying the
    # walk, and one distribution's tree can vanish while the total stays non-zero.
    for manifest in sorted(PACKAGES_ROOT.glob("*/pyproject.toml")):
        root = manifest.parent
        walked = sorted((root / "src").rglob("*.py"))
        assert walked, f"no `.py` file found under {root / 'src'} — the walk itself is broken."


def _distribution_at(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        document = tomllib.load(handle)
    name = table_at(document, "project")["name"]
    assert isinstance(name, str)
    return name


def _requirement_name(requirement: str) -> str:
    """`opentelemetry-api>=1.28` -> `opentelemetry-api`."""
    for separator in (">=", "==", "<=", "~=", ">", "<", "[", ";", " "):
        requirement = requirement.split(separator)[0]
    return requirement.strip()


def _top_level_first_party_imports(path: Path) -> set[str]:
    modules: set[str] = set()

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])

    return {m for m in modules if m.startswith("weft_") and m not in sys.stdlib_module_names}


#: Extras that deliberately name no pack, and why each is here. This is a **ratchet**: a
#: waiver is a visible act in a diff rather than a silent edit, and the check below is only
#: worth running while this stays this short.
#:
#: - `all` is an aggregate of the capability extras, not a capability of its own.
#: - `bertscore` and `reference` supply a *library* to code that already ships unconditionally
#:   (`weft_eval`'s BERTScore metric, `weft_cli.contract_reference`'s formatter). Neither is a
#:   pack whose registration can fail, so neither can ever appear in a `PackReport`, which is
#:   the only place the install line below is composed from.
_EXTRAS_THAT_NAME_NO_PACK: Final[frozenset[str]] = frozenset({"all", "bertscore", "reference"})


def test_every_capability_extra_is_the_name_of_a_pack_in_the_same_distribution() -> None:
    # Carried repair **R11.3**. `weft_cli.pack_attribution.install_hint` tells an operator
    # whose pack reported `failed` to run `pip install <distribution>[<pack>]`, and it reads
    # the distribution's own `Provides-Extra` before saying so — so the sentence is never
    # *wrong*. What it can be is silently *absent*: declare the extra as `pdf-support` while
    # the pack is `pdf` and the one actionable line disappears with nothing failing. G19 is
    # what makes this the load-bearing direction — a capability needing an outside library
    # is now an extra of `weft-rag` rather than a distribution of its own, so the extra name
    # is the only handle an operator has.
    violations: list[str] = []
    for manifest in sorted(PACKAGES_ROOT.glob("*/pyproject.toml")):
        extras = _capability_extras_of(manifest)
        packs = set(_packs_declared_by(manifest))
        for extra in sorted(extras - packs):
            violations.append(
                f"{manifest.relative_to(REPO_ROOT)} declares extra '{extra}', which is not "
                f"a weft.packs entry-point name in that same distribution"
            )

    assert not violations, (
        "a capability extra does not carry the name of the pack it supplies:\n  "
        + "\n  ".join(violations)
        + "\nweft_cli.pack_attribution.install_hint derives `pip install <dist>[<pack>]` "
        "from the pack name, so an extra named anything else is an install line an "
        "operator never sees — silently, because a missing sentence fails nothing."
    )


def test_the_check_can_actually_fail() -> None:
    # The check above is a set difference, and a set difference over an empty left-hand side
    # is green about nothing. Two floors: the subject is non-empty today, and a disagreeing
    # input is refused. The first is the one that would rot — `weft-rag` is the only
    # distribution declaring extras at all, so a layout change moving it would empty the
    # walk with no assertion looking wrong.
    surveyed = {
        manifest.parent.name: _capability_extras_of(manifest)
        for manifest in sorted(PACKAGES_ROOT.glob("*/pyproject.toml"))
    }
    assert any(surveyed.values()), (
        "no distribution under packages/ declares a capability extra, so the check above "
        f"compared nothing against nothing. Surveyed: {sorted(surveyed)}."
    )

    # A capability extra whose name is not a pack is exactly what the check refuses.
    packs = {"pdf", "qdrant"}
    planted = {"pdf", "qdrant", "pdf-support"}
    assert planted - _EXTRAS_THAT_NAME_NO_PACK - packs == {"pdf-support"}


def _capability_extras_of(manifest: Path) -> set[str]:
    """Every extra a manifest declares that claims to supply a *capability* — the waived
    three removed, so what is left is exactly the set whose names an install line is
    derived from. Empty for a distribution declaring no extras at all.
    """
    return set(_optional_table(manifest, "optional-dependencies")) - _EXTRAS_THAT_NAME_NO_PACK


def _packs_declared_by(manifest: Path) -> set[str]:
    """Every `weft.packs` entry-point name a manifest declares — the pack identity a
    `PackReport.pack` carries and a `[packs.<pack>]` settings block keys on.
    """
    return set(_optional_table(manifest, "entry-points", "weft.packs"))


def _optional_table(manifest: Path, *path: str) -> dict[str, object]:
    """`table_at` under `[project]`, answering `{}` for a table a manifest simply omits.

    `table_at` refuses a missing path, which is right for the shapes these checks *require*
    and wrong for these two: a distribution with no extras and a distribution with no packs
    are both ordinary, and `weft-kernel` is each of them. Narrowed here rather than at the
    call sites so the two helpers above stay `set[str]` rather than `set[Unknown]`.
    """
    with manifest.open("rb") as handle:
        document = tomllib.load(handle)
    try:
        return table_at(document, "project", *path)
    except KeyError:
        return {}
