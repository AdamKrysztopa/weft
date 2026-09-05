"""`docs/08-manuals.md` §3 clause (e) — the deprecation promise is written to, not hoped for.

Task **5.2f** (`docs/build-ledger.md`), owed by `docs/09-release.md` §3's own block quote: *"a
`tests/docs` check asserts that every surface marked deprecated at registration has a
`CHANGELOG.md` entry naming it."* `docs/lessons.md` L5.8 is the finding this repairs — the file a
document designates as where a promise is made had never been written to, and `README.md` →
*Protocol* did not name it among what a phase close updates. The ledger's choice was a check
rather than a protocol line; this module is that check.

**Two independent sources, on purpose (`docs/lessons.md` L5.6).** L5.6 found a declaration that
could never disagree with itself because it was derived from the very thing it verified. Here the
two sources are genuinely separate: `_real_deprecations` asks the **installed tree** — real
`weft.packs` entry points, discovered exactly as `weft plugins doctor` discovers them
(`weft_kernel.discovery.discover(Registry())`, the same bare call
`tests/architecture/test_ff8_trust_model.py::test_run_record_active_distributions_equal_what_
plugins_doctor_reports` makes against this same environment) — and folds every `PackReport.
deprecations` it finds into a set of surface labels; `_changelog_text` reads `CHANGELOG.md` off
disk. Neither is derived from the other, so a real disagreement between them is exactly what this
check exists to catch.

**The floor, stated honestly rather than forced.** `08` §3 asks every `tests/docs` check for "a
condition that must be non-trivially true before the comparison runs, so the check cannot pass by
having nothing to compare" — the fix for a parity check that compares a derived value to itself and
so can never fail, because nothing independent of it was ever computed. That shape does not
transplant literally here: **zero
first-party surfaces are deprecated today** (`09` §3's own block quote is written against that
fact), so asserting the real, installed set is non-empty would be false, not a floor. The floor this
module actually carries is `test_the_comparison_can_actually_fail` below: a real `Deprecation`,
produced through the real registration seam (`PackRegistrar.deprecate` → `commit`, never a
hand-built dataclass standing in for it), proves the comparison reports it missing against today's
real `CHANGELOG.md` and clears once an entry naming it is added — `tests/architecture/
test_ff9_extension_from_outside.py::test_the_grep_can_actually_fail`'s shape, applied to a
changelog instead of a grep, and the third mechanism in one gate to need this proof
(`docs/lessons.md` L5.1, L5.4, L5.8 name the first two).

`DEPRECATIONS_WITHOUT_CHANGELOG_ENTRY` is this clause's ratchet, `08` §3's own naming convention:
pinned empty, so excluding any surface from the requirement is a visible act in a diff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from weft_kernel.discovery import PackRegistrar, discover
from weft_kernel.registry import Registry

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CHANGELOG: Final[Path] = REPO_ROOT / "CHANGELOG.md"

#: `08` §3's ratchet for this clause — pinned empty. A deprecated surface named here is
#: deliberately excused from needing its own `CHANGELOG.md` entry; nothing is named today.
DEPRECATIONS_WITHOUT_CHANGELOG_ENTRY: Final[frozenset[str]] = frozenset()


def _real_deprecations() -> frozenset[str]:
    """Every surface a real, installed pack has marked deprecated at registration.

    `discover(Registry())` — no `entry_points=` override — runs against the actual installed
    `weft.packs` group, the same call `weft plugins doctor` makes and the same one
    `test_ff8_trust_model.py`'s own real-environment tests already use. `PackReport.deprecations`
    travels with every report (task 5.2e); this flattens every notice's `surface` across every
    report into one set, independent of which distribution marked it.
    """
    reports = discover(Registry())
    return frozenset(notice.surface for report in reports for notice in report.deprecations)


def _changelog_text() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


def missing_changelog_entries(
    *, deprecated_surfaces: frozenset[str], changelog: str, waived: frozenset[str]
) -> frozenset[str]:
    """Every surface in `deprecated_surfaces` that `changelog` never names and `waived` excuses.

    A pure function, kept separate from the tests below exactly as `test_troubleshooting_
    coverage.py`'s own `missing_troubleshooting_entries` is — so `test_the_comparison_can_
    actually_fail` has something to call that is not the same comparison it is proving isn't
    vacuous. "Names it" is a literal, backtick-quoted mention — `` `surface` `` — matching this
    repository's own convention of backticking identifiers throughout `docs/` and this file's
    own prose, never a fuzzy substring match that could paper over a surface renamed since its
    changelog entry was written.
    """
    return frozenset(
        surface
        for surface in deprecated_surfaces
        if surface not in waived and f"`{surface}`" not in changelog
    )


# --- the floor: today's real state, and proof the comparison is not vacuous ----------------


def test_today_the_installed_tree_marks_nothing_deprecated() -> None:
    # Documents the measured fact `docs/09-release.md` §3's block quote is written against —
    # if this ever fails, a real first-party surface has been marked deprecated, which is
    # exactly the moment `test_every_real_deprecation_has_a_changelog_entry` below stops being
    # vacuous and starts actually being asked something.
    assert _real_deprecations() == frozenset(), (
        "a real, installed pack now marks something deprecated — good, but this pins the "
        "measured fact 09 §3 is written against; update this assertion and its neighbouring "
        "prose once CHANGELOG.md carries the corresponding entry."
    )


def test_the_comparison_can_actually_fail() -> None:
    # Arrange — a real Deprecation, produced through the real registration seam rather than a
    # hand-built stand-in, so the fixture is honest about what discovery actually buffers.
    registrar = PackRegistrar(Registry(), distribution="weft-fixture-pack")
    registrar.deprecate("legacy-widget-plugin", reason="superseded by widget-v2; remove after 1.2")
    registrar.commit()
    (notice,) = registrar.deprecations

    # Act & Assert — red: today's real CHANGELOG.md says nothing about a surface this test
    # invented, so the comparison must report it missing rather than passing vacuously.
    missing = missing_changelog_entries(
        deprecated_surfaces=frozenset({notice.surface}),
        changelog=_changelog_text(),
        waived=frozenset(),
    )
    assert missing == frozenset({notice.surface})

    # green — a changelog that names the surface clears the identical comparison.
    changelog_with_entry = (
        _changelog_text() + f"\n- `{notice.surface}` deprecated: {notice.reason}\n"
    )
    cleared = missing_changelog_entries(
        deprecated_surfaces=frozenset({notice.surface}),
        changelog=changelog_with_entry,
        waived=frozenset(),
    )
    assert cleared == frozenset()


def test_a_waived_surface_is_excused() -> None:
    # AAA — a name present in the waiver is not reported missing even though no entry names it,
    # proving the ratchet is a visible escape hatch rather than a silent one.
    missing = missing_changelog_entries(
        deprecated_surfaces=frozenset({"waived-surface"}),
        changelog="",
        waived=frozenset({"waived-surface"}),
    )

    assert missing == frozenset()


# --- the real check ---------------------------------------------------------------------------


def test_every_real_deprecation_has_a_changelog_entry() -> None:
    # Arrange — the two independent sources: the installed tree, and the document.
    deprecated = _real_deprecations()
    changelog = _changelog_text()

    # Act
    missing = missing_changelog_entries(
        deprecated_surfaces=deprecated,
        changelog=changelog,
        waived=DEPRECATIONS_WITHOUT_CHANGELOG_ENTRY,
    )

    # Assert — passes vacuously today (see the floor test above); the moment a real,
    # installed pack marks a surface deprecated, this is what stops it from shipping with no
    # matching CHANGELOG.md entry.
    assert not missing, (
        f"{sorted(missing)} marked deprecated at registration with no `CHANGELOG.md` entry "
        f"naming it. Add a bullet naming `{sorted(missing)[0]}` under `### Deprecated`, or "
        f"name it in DEPRECATIONS_WITHOUT_CHANGELOG_ENTRY if it is deliberately excused."
    )
