"""Fitness function 0's other half — a check that is named exists, and a check that exists can fail.

**Renumbered 2026-09-06, at Phase 8's close review, and the collision is the reason.** This file
called itself *fitness function 16* — a number `docs/01-high-level-plan.md` assigns to nothing at
all when this was written, and which Phase 8 then assigned to **ladder reachability**
(`01` item 16, `tests/architecture/test_ff16_ladder_reachability.py`). Clause (a) below maps a plan
number to a file by filename prefix, so `16` was satisfied by whichever of the two `glob` returned
first: **delete the ladder-reachability check and this file reported nothing missing.** That is
`docs/lessons.md` `L5.4` — a fitness function living in prose — reintroduced at the one number the
phase touched, by the check written to prevent it. A fitness-function number is a registry key, and
nothing was asserting it resolved to one function.

`0b` rather than a new number because this file's own argument has always been that it is FF0's
other half: FF0 asserts every architecture check is *reachable* from `ci-checks`, and this asserts
each one is *real*. `9c` and `12b` already use that suffix convention for a sub-clause of one
function.

**Added at Phase 5's lessons drain (2026-08-22), from four entries that turned out to be one
defect.** `docs/lessons.md` L5.1, L5.4, L5.8 and L5.19 were written independently, hours apart,
about an OpenTelemetry escape hatch, a fitness function, a changelog and a coverage floor. They
say the same thing: **a mechanism was named in a document, everybody believed it ran, and it did
not.** L5.4's subject is the sharpest — fitness function 6 was specified in
`docs/01-high-level-plan.md` from the first day of the project and had no file in this directory
until task 5.2a built it, five phases later.

That is this repository's oldest failure mode and it already has a fitness function about it:
**FF0**, *the gate must be in the gate*, which exists because a boundary checker can be written,
committed, and never wired into the canonical task that would actually run it. FF0 asserts every
check *in this
directory* is reachable from `ci-checks`. It cannot see the other half — a check that `01`
promises and nobody wrote is invisible to a walk over the files that exist. This function is that
half, plus the one property FF0's subject needs to be worth anything.

**Clause (a): every fitness function `01` names has a file here.** Mechanical, and it is the
reason L5.4 could go five phases unnoticed: `01`'s numbered list is prose, and prose does not fail
a build. The waiver constant below is pinned to the functions `01` itself defers to a later
phase — a named, dated act in a diff, `test_allowlist_empty.py`'s own ratchet discipline, which
`01` item 0 names as the pattern most worth reimplementing.

**Clause (b): every check here proves it can fail.** A check derived from the thing it verifies
cannot fail, and a check that cannot fail is prose with a test runner attached — `docs/lessons.md`
L5.6 names the shape and L5.19 found the specific case where a real subject is legitimately empty
today, so the floor is a **self-test** proving the comparison is not vacuous rather than an
assertion that the real-world set is non-empty. Several files here already carry one, written
independently and named consistently enough to be recognised
(`test_the_grep_can_actually_fail`, `test_the_check_can_actually_fail`, and their siblings); this
clause makes the convention load-bearing instead of customary.

**What this function deliberately does not check.** Whether a self-test is *good* — a test named
`test_the_check_can_actually_fail` that asserts `True` satisfies clause (b) and nothing else. That
is unreachable by any check and it is what review is for. Naming the convention still moves the
default, which is all a ratchet ever does.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

ARCHITECTURE_ROOT: Final[Path] = REPO_ROOT / "tests" / "architecture"
PLAN: Final[Path] = REPO_ROOT / "docs" / "01-high-level-plan.md"

#: A fitness function `01` names that has no file here **yet**, because `01` itself schedules it
#: for a later phase. Pinned, dated, and changed only by a decision-log entry — the ratchet
#: discipline `01` item 0 requires, so a waiver is a visible act in a diff rather than a silent
#: edit.
#:
#: **10 left this set on 2026-08-25**, both clauses built into
#: `test_ff10_ship_set_integrity.py`: clause (a) at ledger task **6.2** and clause (b) at **6.3**.
#: It was held here across 6.2 rather than removed the moment a file with the right *name* existed
#: — a fitness function `01` states in two clauses is not built while one of them is prose, and
#: removing a waiver per-clause is how `docs/lessons.md` L5.4 gets re-created one clause at a time.
#:
#: **5 left this set on 2026-08-25, at ledger task 6.14**, and it is worth recording what it cost
#: to be here: it was this clause's own first catch, on 2026-08-22 — *"every declared capability
#: resolves"* had been numbered in `01` since the project's first day with no file here, five
#: phases, the same span FF6 went unnoticed for, and `docs/lessons.md` L5.4 exactly repeated. It
#: was waived rather than built in that drain because its subject is real design work and
#: **building a fitness function hastily at a phase close is how a check that cannot fail gets
#: written**. `test_ff5_declared_capability_resolves.py` holds two of FF5's clauses and says
#: plainly in its own docstring that it does not hold the third, which is pinned there as a
#: ratchet with ledger task **6.29** owning it — a gap with a constant, a date and an owner rather
#: than a check pretending to be complete.
FITNESS_FUNCTIONS_NOT_YET_DUE: Final[frozenset[int]] = frozenset()

#: Check files written before this function existed and carrying no self-test — a **ratchet that
#: must shrink to empty**, never a snapshot to live with.
#:
#: **Empty since 2026-08-25, ledger task 6.15.** Seven files were waived here on 2026-08-22, this
#: clause's first run. Six were given a self-test one at a time, each planting a disagreement
#: through the file's own real helpers and watched going red: `test_ff0_gate_in_the_gate.py`,
#: `test_ff1_boundary.py`, `test_ff2_no_privileged_builtins.py`, `test_ff3_kernel_budget.py`,
#: `test_ff7_colour_integrity.py` and `test_ff8_trust_model.py` — two of those (FF2, FF8) turned
#: out to have had one all along under a name this clause did not recognise, and FF8's had
#: quietly stopped describing the shipped command (`docs/lessons.md` L6.21). The seventh,
#: `test_ff11_pipeline_integrity.py`, always had four; `_SELF_TEST` above is what could not see
#: them. **Nothing may be added to this set** — a new check arrives with its self-test or it does
#: not arrive.
CHECKS_WITHOUT_A_SELF_TEST: Final[frozenset[str]] = frozenset()

#: How a self-test for clause (b) is spelled. Written independently by different tasks, so the
#: forms are read off the population rather than declared — `docs/lessons.md` L6.4.
#:
#: **A third form was found at ledger task 6.15 and this pattern did not know it.**
#: `test_ff11_pipeline_integrity.py` carries four self-tests named `..._would_be_caught`
#: (`test_a_pipeline_naming_an_unknown_plugin_would_be_caught` and its siblings), every one of
#: them planting a disagreement and watching the comparison go red — exactly what clause (b)
#: asks for. This pattern recognised two spellings and the file was therefore waived in
#: `CHECKS_WITHOUT_A_SELF_TEST` as carrying none, which was false about the tree from the day
#: the constant was written. The fix is here rather than in that file: renaming four accurate
#: test names to satisfy a regex would be the check dictating the tree, and the defect was
#: this pattern being written from what its author expected the convention to be instead of
#: from what the convention actually was.
_SELF_TEST = re.compile(
    r"^def test_the_\w*can_actually_fail\w*$"
    r"|^def test_\w*_can_actually_fail$"
    r"|^def test_\w*_would_be_caught$"
)

#: `01` → *Fitness functions* numbers its entries `0.` through `12.` at the start of a line. Read
#: from the document rather than restated here, so this cannot drift from the list it checks —
#: which is the entire point of the function (`docs/lessons.md` L5.6: a declaration derived from
#: the thing it claims to verify cannot fail, and the inverse holds too — a list *copied* from the
#: document it verifies fails to notice the document changing).
_NUMBERED = re.compile(r"^(?P<number>\d{1,2})\. \*\*", re.MULTILINE)


def _named_in_the_plan() -> frozenset[int]:
    """Every fitness-function number `01` → *Fitness functions* actually numbers."""
    text = PLAN.read_text(encoding="utf-8")
    start = text.index("## Fitness functions")
    section = text[start : text.index("\n## ", start + 1)]
    return frozenset(int(match.group("number")) for match in _NUMBERED.finditer(section))


def _implemented_here() -> frozenset[int]:
    """Every fitness-function number this directory has a file for, read off the filenames.

    `test_ff<N>_<slug>.py` is the convention every file here already follows; a file that does not
    match is a helper or a self-test module and names no function.
    """
    found: set[int] = set()
    for path in ARCHITECTURE_ROOT.glob("test_ff*.py"):
        match = re.match(r"test_ff(?P<number>\d{1,2})[_a-z]", path.name)
        if match is not None:
            found.add(int(match.group("number")))
    return frozenset(found)


def _check_files() -> list[Path]:
    return sorted(ARCHITECTURE_ROOT.glob("test_ff*.py"))


def test_every_fitness_function_the_plan_names_has_a_file_here() -> None:
    """Clause (a) — `docs/lessons.md` L5.4, which is the reason this exists."""
    # Arrange
    named = _named_in_the_plan()
    assert named, (
        "no numbered fitness function was found in `01` — the parse is wrong, not the plan"
    )

    # Act
    missing = named - _implemented_here() - FITNESS_FUNCTIONS_NOT_YET_DUE

    # Assert
    assert not missing, (
        f"`docs/01-high-level-plan.md` names fitness function(s) {sorted(missing)} and this "
        f"directory has no `test_ff<N>_*.py` for them. A fitness function that exists only in "
        f"prose does not fail a build — fitness function 6 was named from the first day of the "
        f"project and had no file for five phases (`docs/lessons.md` L5.4). Build it, or add its "
        f"number to `FITNESS_FUNCTIONS_NOT_YET_DUE` with a dated decision-log entry saying which "
        f"phase owns it."
    )


def test_every_check_here_proves_it_can_fail() -> None:
    """Clause (b) — `docs/lessons.md` L5.6 and L5.19."""
    # Arrange
    files = _check_files()
    assert files, "no fitness-function files found — the glob is wrong, not the tree"

    # Act
    without = [
        path.name
        for path in files
        if path.name not in CHECKS_WITHOUT_A_SELF_TEST
        and not any(
            isinstance(node, ast.FunctionDef) and _SELF_TEST.match(f"def {node.name}")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )
    ]

    # Assert
    assert not without, (
        f"{without} contain no self-test proving the check can fail. A check derived from the "
        f"thing it verifies cannot fail (`docs/lessons.md` L5.6), and a check whose real subject "
        f"is legitimately empty today passes vacuously (L5.19) — in both cases the floor is a "
        f"test that plants a disagreeing case and watches the comparison go red. Name it "
        f"`test_the_check_can_actually_fail`."
    )


def test_the_check_can_actually_fail() -> None:
    """This function's own clause (b), turned on itself.

    Both clauses are comparisons between two sets, so both fail exactly when the sets disagree —
    demonstrated here against planted values rather than against the real tree, which is (and
    should stay) in agreement.
    """
    # Arrange — a plan naming a function nothing implements, and a file carrying no self-test.
    named, implemented = frozenset({0, 99}), frozenset({0})
    unproven = [
        node.name
        for node in ast.walk(ast.parse("def test_something_else() -> None:\n    pass\n"))
        if isinstance(node, ast.FunctionDef) and _SELF_TEST.match(f"def {node.name}")
    ]

    # Act
    missing = named - implemented - FITNESS_FUNCTIONS_NOT_YET_DUE

    # Assert
    assert missing == {99}
    assert not unproven


def test_no_plan_number_is_claimed_by_two_different_functions() -> None:
    """A fitness-function number is a registry key, and until Phase 8's close nothing checked it.

    `_implemented_here` reads the number off the filename, so two files named `test_ff16_*` both
    answer to 16 and clause (a) is satisfied by either — the check that exists *because* FF6 sat in
    prose for five phases, made unable to see the same thing. FF18 asserts one plugin name resolves
    to one contract; this is that property one abstraction up.

    A **letter suffix** is what distinguishes a sub-clause of one function (`ff9c`, `ff12b`) from a
    second function wearing the same number, so the rule is: at most one unsuffixed file per number.
    """
    unsuffixed: dict[int, list[str]] = {}
    for path in sorted(ARCHITECTURE_ROOT.glob("test_ff*.py")):
        match = re.match(r"test_ff(?P<number>\d{1,2})_", path.name)
        if match is not None:
            unsuffixed.setdefault(int(match.group("number")), []).append(path.name)

    collisions = {number: files for number, files in unsuffixed.items() if len(files) > 1}
    assert not collisions, (
        f"these plan numbers are claimed by more than one function: {collisions}. Clause (a) maps "
        f"a number to a file by prefix, so it is satisfied by whichever glob returns first and the "
        f"other could be deleted with nothing said. Give a sub-clause a letter suffix (ff9c), or "
        f"renumber the one that is a different function."
    )


def test_the_collision_rule_can_actually_fail() -> None:
    # Plant the exact pair that existed until 2026-09-06, through the same matcher.
    planted = ["test_ff16_ladder_reachability.py", "test_ff16_checks_are_real.py", "test_ff9c_x.py"]
    seen: dict[int, list[str]] = {}
    for name in planted:
        match = re.match(r"test_ff(?P<number>\d{1,2})_", name)
        if match is not None:
            seen.setdefault(int(match.group("number")), []).append(name)
    assert {n: f for n, f in seen.items() if len(f) > 1} == {
        16: ["test_ff16_ladder_reachability.py", "test_ff16_checks_are_real.py"]
    }
    assert 9 not in seen, "a letter-suffixed sub-clause must not count as an unsuffixed claim"
