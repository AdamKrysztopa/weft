"""Fitness function 5 — every declared capability resolves. Ledger task **6.14**.

`docs/01-high-level-plan.md` → *Fitness functions* 5: "Every capability a plugin declares must
resolve to a live implementation at discovery time, or the plugin must declare it unavailable and
say why."

**Named on the project's first day and built five phases later**, which is `docs/lessons.md` L5.4
exactly — and this file exists because FF16 clause (a) caught it, the check written *from* that
lesson finding the lesson's own subject still open. FF16's waiver carried it with a warning worth
repeating: *"building a fitness function hastily at a phase close is how a check that cannot fail
gets written."* So what follows says plainly which of FF5's two halves it holds and which it does
not.

**What a "declared capability" is in Weft, and what it is not.** G4 settled that a *store*
capability is derived, never declared — asked of the registered class with `issubclass`, so there
is nothing there to disagree with itself. The declaration FF5 is actually about is an extractor's
**accept set**: a pack says *"I handle `.pdf`"*, and the question is whether anything can.

That is the reference bug `docs/README.md` opens by describing — "the same file format was accepted at
upload and had no extractor at extraction time" — and **it happened here**, predicted by line
number before it did. `docs/11-multimodal.md:205` said `discover_source_docs` filtering on one
pack's module constant would make `.pdf` "silently invisible to ingest" the moment a second
extractor pack shipped; `weft-pdf` shipped at ledger 2.27 and `weft index corpus/mrmr` walked nine
PDFs, matched none, handed an empty batch to a text extractor and **exited 0 reporting success**.
The derivation was built repairing that. The check was not, until here.

**Clause (a) — the accept set is the derivation, not a constant. This is the one that fired.**
Structural, over the AST: no call site anywhere under `packages/` passes a single pack's module
constant as `discover_source_docs`'s `extensions`. `docs/lessons.md` L5.23 is why it is structural
rather than textual — a property about the *shape of a call* needs a check that reads calls.

**Clause (b) — every extension a live extractor declares is reachable by ingest.** Read from two
places that can disagree: the registered classes' own `extensions`, walked directly, and
`weft_extract.claimed_extensions`, which is the function the CLI actually calls. A derivation that
started dropping a suffix — filtering, lower-casing, taking the first claimant — fails here while
clause (a) stays green.

**Clause (c) — "or the plugin must declare it unavailable and say why" — is NOT held, and this is
the honest part.** `weft-kernel`'s `PackStatus.PARTIAL` exists in the vocabulary and no pack ever
reports it: `weft_kernel.discovery`'s own docstring says so — *"the mechanism that produces it is
G4's conditional registration, a later step's job"* — and no later step took it. The one real
instance is `weft-eval`'s `bertscore`, which registers unconditionally and answers `Failed` **at
run time**, naming the missing extra. That is *saying why*, one moment too late: an operator
running `weft plugins doctor` learns nothing, and finds out when a run fails instead.

`PLUGINS_REPORTING_UNAVAILABILITY_TOO_LATE` is that gap as a **ratchet**, pinned to its one real
entry, with `test_the_ratchet_names_only_real_plugins` proving the entry is not a name somebody
typed. Naming it is not the same as holding it, and this docstring is not going to pretend
otherwise — but a gap with a constant, a date and a task is a different object from a gap nobody
wrote down, which is the whole argument `01` item 0 makes for ratchets.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from weft_extract import claimed_extensions
from weft_extract.contract import Extractor
from weft_kernel.discovery import discover
from weft_kernel.registry import Registry

from .conftest import REPO_ROOT

PACKAGES: Final[Path] = REPO_ROOT / "packages"

#: The extractor packs this file needs registered, and **nothing else**.
#:
#: `weft_cli.contract_reference.discover_for_reference()` would have been the obvious call and is
#: the wrong one: it discovers **open**, with no `allow`, so it imports every installed pack —
#: including `testing/weft-canary`, whose entire purpose is to prove it was *never* imported.
#: `test_ff2_no_privileged_builtins.py` restricts its own `allow` for exactly this reason and says
#: so. Using the open call here made `test_ff8_trust_model.py`'s two canary tests fail whenever
#: this file ran before them and pass whenever it ran alone — a test-order dependency introduced
#: by a new test, which is the defect ledger task **6.17** exists about, met from a third
#: direction (`docs/lessons.md` L5.21).
#:
#: **Distribution names, because `allow` is keyed on distributions** — so listing `weft-rag`
#: here admits the twelve packs it ships, not only `weft_extract`. That is the trust boundary's
#: own granularity (`weft_kernel.discovery`: trust attaches to what you installed), and it is
#: coarser than this test would like; what it still buys is the one thing it was written for,
#: which is that `testing/weft-canary` is not among them.
_EXTRACTOR_PACKS: Final[frozenset[str]] = frozenset({"weft-rag", "weft-pdf"})


def _extractor_registry() -> Registry:
    """A registry holding the extractor packs, and importing nothing beyond them."""
    registry = Registry()
    discover(registry, allow=_EXTRACTOR_PACKS)
    return registry


#: The derivation ingest must filter on. A call passing anything else is clause (a)'s failure.
DERIVATION: Final[str] = "claimed_extensions"

#: Plugins that register and report their unavailability only when run — FF5's second half.
#:
#: **Empty since 2026-08-25, ledger task 6.29.** It held `bertscore` for one task: the metric
#: needs the optional `bert-score` extra and answered `Failed` at *run* time naming it, which is
#: saying why one moment too late. `PackStatus.PARTIAL` now has the mechanism
#: `weft_kernel.discovery`'s own docstring deferred in Phase 0 — `PackRegistrar.unavailable`,
#: buffered exactly like `deprecate` — so `weft-eval` declares it at registration, the pack reports
#: `PARTIAL`, and `weft plugins doctor` says it before a run does. **Nothing may be added here
#: without a task that empties it.**
PLUGINS_REPORTING_UNAVAILABILITY_TOO_LATE: Final[frozenset[str]] = frozenset()


def _calls_to(function: str, tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == function)
            or (isinstance(node.func, ast.Attribute) and node.func.attr == function)
        )
    ]


def accept_set_arguments() -> list[tuple[Path, ast.expr]]:
    """Every `extensions=` argument handed to `discover_source_docs` under `packages/`."""
    found: list[tuple[Path, ast.expr]] = []
    for path in sorted(PACKAGES.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in _calls_to("discover_source_docs", tree):
            found.extend(
                (path, keyword.value) for keyword in call.keywords if keyword.arg == "extensions"
            )
    return found


def _traces_to_derivation(argument: ast.expr, tree: ast.AST) -> bool:
    """Whether `argument` is, or is computed from, the derivation rather than a constant.

    A local name is followed back to what assigned it — the real call site writes
    `readable = present & accepted`, so the argument is a name whose provenance is two
    assignments away, and a check that only looked at the argument itself would see a bare `Name`
    and have to guess.
    """
    if _calls_to(DERIVATION, argument):
        return True
    if not isinstance(argument, ast.Name):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if argument.id in targets and (
            _calls_to(DERIVATION, node.value)
            or any(
                _traces_to_derivation(part, tree)
                for part in ast.walk(node.value)
                if isinstance(part, ast.Name) and part.id != argument.id
            )
        ):
            return True
    return False


def test_ingest_filters_on_the_derivation_and_never_on_a_packs_constant() -> None:
    """Clause (a) — the one that shipped, and the one `11` §2.1 predicted by line number."""
    # Arrange
    arguments = accept_set_arguments()

    # Act
    constants: list[str] = []
    for path, argument in arguments:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not _traces_to_derivation(argument, tree):
            constants.append(f"{path.relative_to(REPO_ROOT)}: {ast.unparse(argument)}")

    # Assert
    assert arguments, (
        "no `discover_source_docs(..., extensions=...)` call was found under `packages/`. That "
        "is the call this clause is about; finding none means the walk is wrong, not that ingest "
        "has stopped filtering."
    )
    assert not constants, (
        f"ingest filters on something other than `{DERIVATION}`:\n  "
        + "\n  ".join(constants)
        + "\n\n`02` §1: capability is derived, never declared. Filtering on one pack's constant "
        "is how `.pdf` became silently invisible to ingest at ledger 2.27 — nine PDFs walked, "
        "none matched, exit 0 reporting success."
    )


def test_every_extension_a_live_extractor_declares_is_reachable() -> None:
    """Clause (b), from two places that can disagree: the registered classes, and the shipped
    derivation the CLI actually calls.
    """
    # Arrange
    registry = _extractor_registry()

    # Act — the classes' own declarations, walked directly.
    declared: set[str] = set()
    for name in registry.names_for(Extractor):
        entry = registry.entry(Extractor, name)
        extensions = getattr(entry.factory, "extensions", ())
        declared.update(str(suffix) for suffix in extensions)
    derived = set(claimed_extensions(registry))

    # Assert
    assert declared, (
        "no registered extractor declares an extension. The comparison below would pass by "
        "having nothing to compare, which is the vacuous shape `docs/lessons.md` L5.19 names."
    )
    assert declared <= derived, (
        f"{sorted(declared - derived)} are declared by a live extractor and are not in the set "
        f"ingest accepts. A file with that suffix is walked, matched by nothing, and the run "
        f"exits 0 having indexed none of it — the reference bug `docs/README.md` opens by describing."
    )


def test_the_ratchet_names_only_real_plugins() -> None:
    """Clause (c) is not held, so the least this file owes is that its record of the gap is true.

    A ratchet naming something that does not exist reads shorter than it is and makes the task
    that empties it look partly done — the same check `test_ff0_gate_in_the_gate.py` makes about
    its own waived suites, and the same hole `docs/lessons.md` L6.29 found in that one: what has
    to be asserted is that the name is *live*, not that a string appears somewhere.
    """
    # Arrange — the ratchet's one entry is a `weft-eval` metric, so that pack is what has to be
    # discovered to check it is live. Restricted, for the reason `_EXTRACTOR_PACKS` above gives.
    registry = Registry()
    # `weft-rag` is the distribution shipping `eval`, `embed`, `llm` and `prompts` — four
    # separate names before 2026-09-05, one wheel since. Still restricted, and still for the
    # canary reason `_EXTRACTOR_PACKS` above states.
    discover(registry, allow=frozenset({"weft-rag"}))

    # Act
    registered = {
        name for contract in registry.contracts() for name in registry.names_for(contract)
    }
    absent = sorted(PLUGINS_REPORTING_UNAVAILABILITY_TOO_LATE - registered)

    # Assert
    assert registered, "nothing is registered at all — the registry read is wrong"
    assert not absent, (
        f"{absent} is named in PLUGINS_REPORTING_UNAVAILABILITY_TOO_LATE and is registered by "
        f"nothing. Delete the entry: ledger task 6.29 empties this constant, and a stale name "
        f"makes that look already done."
    )


def test_the_check_can_actually_fail() -> None:
    """Clauses (a) and (b), planted through the real readers.

    The tree agrees on both today — clause (a) has since 2.27's repair and clause (b) always —
    so this is the only place either comparison is seen disagreeing (`docs/lessons.md` L5.19).
    Clause (a)'s plant is the **historical defect itself**, written as it was written.
    """
    # Arrange — the pre-2.27 call, and a derivation that drops a suffix.
    regression = ast.parse(
        "from weft_extract.text import EXTENSIONS\n"
        "docs = discover_source_docs(directory, extensions=EXTENSIONS)\n"
    )
    correct = ast.parse(
        "claims = claimed_extensions(registry)\n"
        "readable = present & claims\n"
        "docs = discover_source_docs(directory, extensions=readable)\n"
    )

    # Act
    def constants(tree: ast.Module) -> list[str]:
        return [
            ast.unparse(keyword.value)
            for call in _calls_to("discover_source_docs", tree)
            for keyword in call.keywords
            if keyword.arg == "extensions" and not _traces_to_derivation(keyword.value, tree)
        ]

    declared, derived = {".pdf", ".txt"}, {".txt"}

    # Assert
    assert constants(regression) == ["EXTENSIONS"], "the historical defect must be caught"
    assert constants(correct) == [], "the real call shape must not be flagged"
    assert declared - derived == {".pdf"}, "a dropped suffix must be visible as unreachable"
