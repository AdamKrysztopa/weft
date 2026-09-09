"""Fitness function **28** — the graph pack is an ordinary pack. Ledger task 11.5.

`01` → *Fitness functions* item 28 carries the argument; this file is the check. Fitness function
21's three clauses applied to `weft_kg`, each able to fail alone.

**The numeral is 28 and it was written down as 24 for three days.** `01` → Phase 11 allocated 24 to
this check on 2026-09-06, in the same paragraph that quotes FF0(b)'s rule — *"numbered and filed
**by the task that makes it true**"* — and `tests/architecture/test_ff24_no_bytes_in_a_node.py` has
held 24 since task **9.5**. A numeral is a claim on a shared namespace and planning is not
claiming. `docs/lessons.md` `L11.24`.

**And clause (a) asserts a pack, not a wheel.** It read *"its own distribution … never bundled into
the `weft-rag` wheel"* until **G19** settled that Weft publishes two names and a new capability
never adds a third — at which point the clause asserted the opposite of what the project had
decided. What it was *for* survives, because a pack's identity was never its distribution: `weft_kg`
reaches the registry through **one ordinary `weft.packs` entry point**, under its own pack name,
its own `[packs.graph]` settings namespace and its own `plugins doctor` row, with nothing it
receives that a third party's pack does not.

**Clause (c) is the one G19 made sharper rather than weaker.** `weft_kg` now sits in the same wheel
as `weft_cli`, so an import that used to require a dependency edit somebody would notice is one
line away, and nothing but this check stands between.

**Clause (b) carries the exception, and the exception is wired rather than asserted.** `weft_kg`
publishes `GraphTraversal` and is its only first-party implementer, which is the "second paradigm"
`S12` refused — a retriever bound to one class — unless somebody who did not write it can satisfy
the Protocol. Fitness function 9c is what proves that, so the exception here is admitted only while
9c's own ratchet does not waive this contract: `test_the_traversal_exception_is_earned` reads
`CONTRACTS_WITHOUT_AN_EXAMPLE_PACK` from that module rather than restating the claim, so waiving
`GraphTraversal` there fails *here*, at the check whose exception depended on it.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

from tests.architecture.test_ff9c_every_contract_has_a_stranger import (
    CONTRACTS_WITHOUT_AN_EXAMPLE_PACK,
)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
#: The wheel that carries the graph pack — inside `weft-rag` since **G19** (2026-09-09).
RAG_ROOT: Final[Path] = REPO_ROOT / "packages" / "weft-rag"
GRAPH_MODULE: Final[Path] = RAG_ROOT / "src" / "weft_kg"
KERNEL_ROOT: Final[Path] = REPO_ROOT / "packages" / "weft-kernel"

#: The entry-point group every pack declares — `docs/02-extension-model.md` §2.
_PACK_GROUP: Final[str] = "weft.packs"

#: The Protocol this pack publishes itself, and the one contract clause (b) admits. Spelled as the
#: qualified name fitness function 9c uses on both sides of its own comparison, so the two modules
#: are talking about the same thing.
_PUBLISHED_HERE: Final[str] = "weft_kg.contract.GraphTraversal"


def _pack_entry_points(distribution: Path) -> Mapping[str, str]:
    """The `weft.packs` table a distribution declares, as a mapping of name to target.

    Narrowed once, here, rather than by chaining `.get` off a bare `isinstance` — the identical
    helper `test_ff21_agent_is_an_ordinary_pack.py` carries, for the reason its own docstring
    gives about pyright reading the chained form as partially unknown.
    """
    with (distribution / "pyproject.toml").open("rb") as handle:
        loaded: Mapping[str, Any] = tomllib.load(handle)
    project: Mapping[str, Any] = loaded.get("project", {})
    entry_points: Mapping[str, Any] = project.get("entry-points", {})
    declared: Mapping[str, str] = entry_points.get(_PACK_GROUP, {})
    return declared


def _sibling_package_dirs() -> tuple[Path, ...]:
    """Every top-level package in the `weft-rag` wheel except `weft_kg` itself.

    Read off the source tree rather than from a list here, so a pack added tomorrow is covered
    with no edit — `L5.14`, and the same derivation fitness function 9c uses for `packages/`.
    """
    src = RAG_ROOT / "src"
    return tuple(
        sorted(
            path
            for path in src.iterdir()
            if path.is_dir() and path.name != "weft_kg" and (path / "__init__.py").is_file()
        )
    )


def naming_the_graph_pack(
    names: Iterable[str], *, within: Iterable[Path]
) -> list[tuple[Path, str]]:
    """Every `(file, name)` pair where a file under `within` contains one of `names`.

    Factored out so `test_the_check_can_actually_fail` drives the same function the clauses do —
    a self-test that reimplements the sweep proves nothing about the sweep.
    """
    wanted = tuple(names)
    hits: list[tuple[Path, str]] = []
    for root in within:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".toml", ".md", ".yaml"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            hits.extend((path, name) for name in wanted if name in text)
    return hits


def test_the_graph_pack_is_an_ordinary_pack_module() -> None:
    """(a) — a pack, in a place a pack lives, with the wheel's own licence files beside it."""
    assert GRAPH_MODULE.is_dir(), (
        "packages/weft-rag/src/weft_kg/ does not exist. The graph pack is a pack like any other "
        "and has to be somewhere a pack lives."
    )
    for required in ("pyproject.toml", "LICENSE", "NOTICE"):
        assert (RAG_ROOT / required).is_file(), f"packages/weft-rag/{required} is missing"


def test_the_graph_pack_declares_one_pack_entry_point() -> None:
    """(a), continued — the same single entry point a third party declares.

    Narrowed to this pack's own row: `weft-rag` declares one per pack, and what this asserts is
    that exactly one of them is the graph pack's and that it points at `weft_kg`.
    """
    packs = dict(_pack_entry_points(RAG_ROOT))
    graph_rows = {name: target for name, target in packs.items() if target.startswith("weft_kg")}

    assert list(graph_rows) == ["graph"], (
        f"weft_kg must be reached by exactly one `{_PACK_GROUP}` entry point named `graph`, like "
        f"every other pack in this wheel; found {graph_rows!r} among {sorted(packs)}"
    )


def test_the_graph_pack_registers_against_contracts_it_did_not_define_except_its_own() -> None:
    """(b) — read off the registry the pack actually populates, never textually.

    Every contract it registers under is asked which module defines it. Exactly one may be its
    own — the traversal Protocol `11.4` published, which `S12` settled ships from the pack that
    owns the capability. A *second* home-grown contract would mean the pack had grown a private
    extension point and registered into it, which proves nothing about whether a stranger could.
    """
    from weft_kernel.discovery import PackRegistrar
    from weft_kernel.registry import Registry
    from weft_kg import Settings, register

    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")
    register(registrar, Settings())
    registrar.commit()

    contracts = list(registry.contracts())
    assert contracts, "weft_kg registered nothing at all, so it is not yet a pack"

    home_grown = sorted(
        f"{contract.__module__}.{contract.__qualname__}"
        for contract in contracts
        if contract.__module__.split(".")[0] == "weft_kg"
    )
    assert home_grown == [_PUBLISHED_HERE], (
        f"weft_kg registers against these contracts of its own: {home_grown}. Exactly one is "
        f"admitted — {_PUBLISHED_HERE}, the Protocol `S12` settled it publishes — and it is "
        f"admitted only while fitness function 9c holds an out-of-tree stranger implementing it."
    )


def test_the_traversal_exception_is_earned() -> None:
    """(b)'s exception, wired to the thing that earns it rather than asserted beside it.

    A pack that publishes a contract and is its only implementer has built the second paradigm
    `S12` refused. What makes that untrue is a stranger, and fitness function 9c is where a
    stranger is proven — so the moment `GraphTraversal` is waived out of 9c's ratchet, the
    exception above is unearned and this fails, naming why.
    """
    assert _PUBLISHED_HERE not in CONTRACTS_WITHOUT_AN_EXAMPLE_PACK, (
        f"{_PUBLISHED_HERE} is waived out of fitness function 9c, so nothing out of tree "
        f"implements it any more — and clause (b) above admits weft_kg registering under its own "
        f"contract only while something does. Either restore the stranger or stop registering "
        f"under a contract this pack alone can satisfy."
    )


def test_nothing_else_in_the_wheel_or_the_kernel_reaches_into_the_graph_pack() -> None:
    """(c) — and G19 made this the clause that matters.

    Swept over the kernel distribution and over every *other* top-level package in the `weft-rag`
    wheel: an import of `weft_kg`, or a literal naming a plugin it registers, is core knowing
    about a capability it must not. Before G19 an import here needed a dependency edit somebody
    would have seen in a diff; now it is one line inside a wheel that already contains both.
    """
    leaks = naming_the_graph_pack(
        ("weft_kg", "pgvector-graph", "pgvector-traversal"),
        within=(KERNEL_ROOT, *_sibling_package_dirs()),
    )
    assert not leaks, (
        "these first-party files name the graph pack or a plugin it registers:\n  "
        + "\n  ".join(f"{path.relative_to(REPO_ROOT)}: {name!r}" for path, name in leaks)
        + "\n\nFitness function 28(c): nothing in the kernel or in any other pack of this wheel "
        "may know the graph pack exists. It is reached through discovery and by no other path."
    )


def test_at_least_one_sibling_package_is_swept() -> None:
    """The floor — a sweep over an empty set of roots passes by asking nothing (`L5.19`)."""
    siblings = _sibling_package_dirs()
    assert len(siblings) > 10, (
        f"only {len(siblings)} sibling packages found under packages/weft-rag/src, so clause (c) "
        f"is reporting on almost nothing. The wheel ships more than twenty."
    )
    assert all(path.name != "weft_kg" for path in siblings), (
        "the graph pack is in its own clause-(c) sweep, so every mention of itself would be a leak"
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Each half planted through the same predicate it guards — `docs/lessons.md` L5.6.

    The plant for clause (c) is a **real** mention in a file the sweep would read, not a
    same-shaped string in a directory it never opens: a self-test that plants outside the swept
    roots proves the planting, not the sweep.
    """
    # Arrange — a sibling package that names the graph pack, in the shape a real leak takes.
    planted_root = tmp_path / "weft_somepack"
    planted_root.mkdir()
    (planted_root / "__init__.py").write_text("from weft_kg import Settings\n", encoding="utf-8")
    clean_root = tmp_path / "weft_cleanpack"
    clean_root.mkdir()
    (clean_root / "__init__.py").write_text("# nothing to see\n", encoding="utf-8")

    # Act
    caught = naming_the_graph_pack(("weft_kg",), within=[planted_root])
    quiet = naming_the_graph_pack(("weft_kg",), within=[clean_root])

    # Assert
    assert [name for _, name in caught] == ["weft_kg"], (
        "the clause (c) sweep did not find an import planted for exactly this purpose"
    )
    assert quiet == [], "the sweep reported a leak in a file that has none"
    assert not (REPO_ROOT / "packages" / "weft-no-such-pack").is_dir()
