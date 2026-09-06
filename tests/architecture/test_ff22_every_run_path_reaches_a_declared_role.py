"""Fitness function 22 — every run path reaches a declared `[services]` role.

Ledger task **9.0**, `docs/01-high-level-plan.md` → Phase 9, and `build-ledger.md` → Phase 7's exit
verdict, finding *(a)*, which is the failure this exists to stop recurring: *"`run_command`
registers `LLM`, `Prompts`, `TokenSink` and `Registry`; a pack needing the configured `NodeStore` or
`Embedder` still cannot reach one... The seam was repaired for the four contracts the agent needed
rather than made whole."*

**The defect is structural, and that is why a unit test cannot hold this.** A run's services are
assembled in more than one place — the query path, the ingest path and the command path — and the
three are one list written thrice. Every fix to that seam has so far landed in the assembler whose
absence somebody happened to notice: task 8.10 built the ingest assembler because two registered
`Expander` plugins had never run through the CLI at all (`docs/lessons.md` L8.4, found by running
the binary and by none of the 1,929 tests then green), and task 7.4 repaired the command path for
the four contracts one pack needed. **A fourth assembler added later, by anyone, would reproduce the
defect exactly** — and every behavioural test in the tree would stay green, because a test asserts
the paths it knows about.

So the property here is deliberately about the *text*: no code in the shipped tree may build a run's
`ServiceRegistry` except through the one function that registers the declared role set. That is a
legitimate subject for a source-reading check in the way `docs/lessons.md` `L9.39` describes —
"a check that greps or parses first-party source is reserved for properties that really are about
the text" — and it is the opposite of the test `L9.39` was written about, which pinned *where* a
registration was written while claiming to check that a command could reach a service.

**Two properties, each able to fail alone:**

*(a) Every `ServiceRegistry` construction in the shipped tree is inside a named assembler.* The
pinned set is the three the plan knows about. A fourth appearing anywhere under `packages/*/src`
fails, naming it, rather than silently becoming a path roles do not reach.

*(b) Every named assembler actually registers the declared roles* — asserted by running each one
against a role no first-party pack declares and requiring the instance back. Clause (a) alone would
pass against three assemblers that all forgot, which is the vacuity `01` item 0's own ratchet style
exists to refuse.

**The waiver is pinned empty.** An assembler that legitimately must not carry roles is a decision
with an argument behind it, recorded here by name, never a silent addition.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest

from weft_cli.service_roles import RoleTable
from weft_cli.services import ServiceSelection
from weft_kernel.context import ServiceRole
from weft_kernel.registry import Registry

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: The functions permitted to build a run's `ServiceRegistry`, each of which must register the
#: declared role set. `qualname` as written in the source, not an import path: this walk reads
#: text and never imports the module it is judging.
ROLE_CARRYING_ASSEMBLERS: Final[frozenset[str]] = frozenset(
    {
        "build_services",
        "build_index_services",
        "command_path_services",
    }
)

#: `01` item 0's own ratchet shape. **Pinned empty.** An assembler that deliberately carries no
#: roles is an argument recorded in `docs/README.md`'s decision log and named here, never a name
#: parked to make a red check green.
ASSEMBLERS_WAIVED_FROM_CARRYING_ROLES: Final[frozenset[str]] = frozenset()


class _StrangerContract:
    """A contract no first-party pack publishes — the only honest subject for this check.

    Using `NodeStore` or `Embedder` would let an assembler pass by registering them the way it
    always did, which is the pre-9.0 behaviour and not the property.
    """


class _StrangerPlugin:
    def __init__(self, config: object = None) -> None:
        del config


_STRANGER_ROLE: Final[ServiceRole] = ServiceRole(key="ff22-probe", contract=_StrangerContract)


def _shipped_python_files() -> Iterator[Path]:
    """Every first-party source file, `packages/*/src/**/*.py`.

    Tests, examples and the canary are deliberately out of scope: a test may construct a
    `ServiceRegistry` freely, and does — this check is about what a *run* assembles.
    """
    for package in sorted(PACKAGES_ROOT.iterdir()):
        src = package / "src"
        if src.is_dir():
            yield from sorted(src.rglob("*.py"))


def _construction_sites() -> list[tuple[str, str]]:
    """Every `ServiceRegistry()` call in the shipped tree, as `(path, enclosing function)`."""
    found: list[tuple[str, str]] = []
    for path in _shipped_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        enclosing: dict[ast.AST, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for child in ast.walk(node):
                    enclosing.setdefault(child, node.name)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ServiceRegistry"
            ):
                relative = path.relative_to(REPO_ROOT).as_posix()
                found.append((relative, enclosing.get(node, "<module level>")))
    return found


def test_no_shipped_code_assembles_a_run_outside_a_named_assembler() -> None:
    """Clause (a) — a fourth assembler fails the build rather than silently skipping roles."""
    # Arrange
    permitted = ROLE_CARRYING_ASSEMBLERS | ASSEMBLERS_WAIVED_FROM_CARRYING_ROLES

    # Act
    stray = [(path, fn) for path, fn in _construction_sites() if fn not in permitted]

    # Assert
    assert not stray, (
        f"these build a run's ServiceRegistry outside the named assemblers: {stray}. A run "
        f"assembled anywhere else is a path a pack's declared [services] role cannot reach, "
        f"which is the defect Phase 7's close filed as finding (a) and task 9.0 closed. Either "
        f"route it through weft_cli.run_services, or name it in "
        f"ROLE_CARRYING_ASSEMBLERS and make it register the roles too."
    )


def test_the_pinned_assemblers_all_exist() -> None:
    """The list is a claim about the tree, and a stale name would make clause (a) weaker in
    silence — the same two-way ratchet `test_ff12`'s own family list carries.
    """
    # Arrange
    names = {fn for _, fn in _construction_sites()}

    # Act
    missing = ROLE_CARRYING_ASSEMBLERS - names

    # Assert
    assert not missing, (
        f"ROLE_CARRYING_ASSEMBLERS names {sorted(missing)}, which construct no ServiceRegistry "
        f"in the shipped tree. A name here that no longer exists silently widens what clause "
        f"(a) permits."
    )


def test_the_waiver_is_empty() -> None:
    """`01` item 0's ratchet. Changed only by a dated entry in `docs/README.md`'s decision log."""
    assert frozenset() == ASSEMBLERS_WAIVED_FROM_CARRYING_ROLES, (
        "an assembler waived from carrying declared roles is a decision with an argument behind "
        "it, recorded in docs/README.md's decision log, never an edit here to clear a red check."
    )


async def test_every_named_assembler_reaches_a_role_no_first_party_pack_declares() -> None:
    """Clause (b) — the non-vacuity floor.

    Clause (a) passes against three assemblers that all forgot to register anything. This runs
    each one against a stranger's role and requires the instance back, so the check fails when
    the seam is broken rather than only when a fourth assembler appears.
    """
    # Arrange
    from weft_cli.llm_roles import LLMSection
    from weft_cli.registry_bootstrap import Dependencies
    from weft_cli.run_services import build_index_services, build_services, command_path_services
    from weft_llm.client import NullSink

    def _registry() -> Registry:
        registry = Registry()
        registry.add_many(
            [(_StrangerContract, "ff22-plugin", _StrangerPlugin)], distribution="weft-ff22"
        )
        return registry

    selection = ServiceSelection(roles={"ff22-probe": "ff22-plugin"})
    table = RoleTable(roles={"ff22-probe": _STRANGER_ROLE})

    # Act / Assert — the command path
    deps = Dependencies(registry=_registry(), reports=(), services=selection, roles=table)
    assert isinstance(
        command_path_services(deps, sink=NullSink()).resolve(_StrangerContract), _StrangerPlugin
    )

    # Act / Assert — the ingest path
    ingest = await build_index_services(
        registry=_registry(),
        llm=LLMSection(),
        sink=NullSink(),
        embedder=None,
        services=selection,
        roles=table,
    )
    assert isinstance(ingest.resolve(_StrangerContract), _StrangerPlugin)

    # Act / Assert — the query path. It resolves the configured store and embedder
    # unconditionally, so a registry shaped like a real install is what it is asked against.
    from weft_embed import Embedder
    from weft_store import NodeStore

    query_registry = _registry()
    query_registry.add_many(
        [(NodeStore, "pgvector", _StrangerPlugin), (Embedder, "hash", _StrangerPlugin)],
        distribution="weft-ff22",
    )
    query = await build_services(
        registry=query_registry,
        catalogue={},
        llm=LLMSection(),
        services=selection,
        sink=NullSink(),
        roles=table,
    )
    assert isinstance(query.resolve(_StrangerContract), _StrangerPlugin)


def test_the_construction_walk_can_actually_find_something() -> None:
    """The self-test `01` item 0 requires: a walk that matched nothing would pass both clauses
    vacuously, and this file would report a seam it never looked at.
    """
    # Arrange / Act
    sites = _construction_sites()

    # Assert
    assert sites, "the AST walk found no ServiceRegistry construction at all — it is broken"
    assert {fn for _, fn in sites} >= ROLE_CARRYING_ASSEMBLERS, (
        "the walk found constructions but not the three the plan names, so it is reading "
        "something other than what this check is about"
    )


def test_a_planted_stray_assembler_would_be_caught() -> None:
    """The plant. A check whose disagreeing case has never been watched fail is a check nobody
    has evidence about — `01` item 0's own words, and `docs/lessons.md` L6.29's cost.
    """
    # Arrange — the shape a fourth assembler would have, judged by the same predicate
    permitted = ROLE_CARRYING_ASSEMBLERS | ASSEMBLERS_WAIVED_FROM_CARRYING_ROLES
    planted = [("packages/weft-somewhere/src/w/x.py", "assemble_my_own_run")]

    # Act
    stray = [(path, fn) for path, fn in planted if fn not in permitted]

    # Assert
    assert stray == planted, (
        "the predicate clause (a) uses did not reject a function outside the pinned set, so "
        "clause (a) cannot fail and is not a check"
    )


@pytest.mark.parametrize("name", sorted(ROLE_CARRYING_ASSEMBLERS))
def test_each_named_assembler_lives_in_one_module(name: str) -> None:
    """One seam, one home. Three assemblers spread across three modules is how the list got
    written thrice in the first place; keeping them together is what makes a fourth obvious.
    """
    # Arrange
    homes = {path for path, fn in _construction_sites() if fn == name}

    # Assert
    assert homes == {"packages/weft-rag/src/weft_cli/run_services.py"}, (
        f"'{name}' assembles a run from {sorted(homes)}. Every run assembler lives in "
        f"weft_cli.run_services, so the set of them is readable in one file."
    )
