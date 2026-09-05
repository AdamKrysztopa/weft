"""`docs/08-manuals.md` §3 clause (d) — a new failure mode cannot land with no entry about it.

Task **0.14**: "a new failure mode cannot land in code with no entry describing what to do about
it." The failure set this check compares against is **derived from the code, never hand-listed**:
every `weft_kernel.errors.WeftError` subclass defined anywhere under the first-party distributions'
own source trees, found by walking those packages with `pkgutil.walk_packages` and importing every
submodule — so a class added in a file this test's author never thought to import still gets picked
up — plus every `weft_kernel.discovery.PackStatus` member, read off the enum itself rather than
retyped. `manual/troubleshooting.md`'s own entries are `### \\`name\\`` headings, matched by exact
set equality against that derived set: the two-lists bug, aimed at a support document instead of a
file format or a contract.

**The floor** (`08` §3): "the enumerated set of `WeftError` subclasses and doctor statuses is
non-zero before checking each has an entry" — a walk that silently imported nothing would otherwise
let the coverage check pass by having nothing to require, which is exactly the shape
`reference/study/08-salvage.md:777-782`'s parity test failed in: a comparison with nothing to compare
cannot fail, and a check that cannot fail is not a check.

`ERRORS_WITHOUT_TROUBLESHOOTING_ENTRY` is `08`'s named ratchet for this clause — pinned empty, so
excluding any class or status from the requirement is a visible act in a diff, never a silent
omission.

This check requires an entry for every name in the derived set; it does not forbid the guide from
documenting more than that. A failure mode with nothing to derive from — `weft_cli.cli`'s
last-resort catch for an exception no `WeftError` handler translated, which is not a named class —
still gets a hand-written section. Give it a heading `_ENTRY_HEADING` will not match (no backticks
around the name, so it is not a "### `name`" heading) and it is simply invisible to both directions
of this check: not required, and never flagged stale.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path
from typing import Final

from weft_kernel.discovery import PackStatus
from weft_kernel.errors import WeftError

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
GUIDE: Final[Path] = REPO_ROOT / "manual" / "troubleshooting.md"
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"


def _first_party_top_level_packages() -> tuple[str, ...]:
    """Every first-party top-level import name, read as `packages/*/src/*`.

    **This was `packages/*/pyproject.toml` with `project.name`'s hyphens turned into
    underscores**, which held while every distribution shipped exactly one top-level package
    and stopped holding on 2026-09-05, when fourteen of them moved into `weft-rag`. That
    derivation then named `weft_rag` — a module that does not exist — and silently lost the
    fourteen it was there to find. The invariant that survived is the one read here: every
    first-party module lives at `packages/<something>/src/<module>`. A distribution that ships
    no code contributes nothing and needs no name-based exclusion, exactly as before.

    Restated in this file rather than imported from another test module, on the precedent
    `test_ff11_pipeline_integrity.py` set ("one self-contained scenario"). That convention is
    what made this a five-file repair, and it is worth knowing that is its price.
    """
    roots: list[str] = []
    for src in sorted(PACKAGES_ROOT.glob("*/src")):
        roots.extend(
            path.name for path in sorted(src.iterdir()) if (path / "__init__.py").is_file()
        )
    return tuple(sorted(roots))


#: Every first-party distribution's top-level import name — the whole shipped tree
#: `docs/README.md` → *Where things are* lists as packages, minus `weft-canary`
#: (`testing/weft-canary`), which is test-only infrastructure and never reaches a user as a
#: failure mode. Derived from `packages/*/pyproject.toml` (see
#: `_first_party_top_level_packages`) rather than a hand-picked list of modules known today
#: to define a `WeftError` subclass, so a new distribution under `packages/` is found
#: automatically, with nothing to remember to add here.
_FIRST_PARTY_TOP_LEVEL_PACKAGES: Final[tuple[str, ...]] = _first_party_top_level_packages()

#: `08` §3's ratchet for clause (d) — pinned empty. A `WeftError` subclass or `PackStatus`
#: member named here is deliberately excluded from the coverage requirement; nothing is
#: named today.
ERRORS_WITHOUT_TROUBLESHOOTING_ENTRY: Final[frozenset[str]] = frozenset()

_ENTRY_HEADING = re.compile(r"^### `([^`]+)`", re.MULTILINE)


def _import_every_first_party_module() -> None:
    """Import every submodule of every distribution in `_FIRST_PARTY_TOP_LEVEL_PACKAGES`.

    So that `WeftError.__subclasses__()` below sees every subclass ever defined, not only
    the ones some other test happened to import first — a subclass defined in a module
    nothing else in this run imports would otherwise be invisible, which is precisely the
    silent gap this check exists to make impossible.
    """
    for top_level in _FIRST_PARTY_TOP_LEVEL_PACKAGES:
        package = importlib.import_module(top_level)
        package_path = getattr(package, "__path__", None)
        if package_path is None:  # a single-module distribution, nothing further to walk
            continue
        prefix = f"{top_level}."
        for module_info in pkgutil.walk_packages(package_path, prefix=prefix):
            importlib.import_module(module_info.name)


def _all_weft_error_subclasses() -> frozenset[type[WeftError]]:
    """Every `WeftError` subclass defined in the first-party source tree, walked recursively.

    Recursive, not `WeftError.__subclasses__()` alone, so a class that subclasses an
    existing subclass rather than `WeftError` directly is still found — nothing here
    assumes today's one-level hierarchy stays one level forever.

    `WeftError.__subclasses__()` is process-global — it also reports a class any *other*
    test module happens to have defined by the time this one runs (`GraphConnectionError`,
    a function-local class `tests/unit/weft_kernel/test_errors.py` builds to prove
    `WeftError` catches pack-specific subclasses), and pytest's collection order is not this
    module's to depend on. Filtered to classes whose own `__module__` starts with one of
    `_FIRST_PARTY_TOP_LEVEL_PACKAGES`, so a test fixture's throwaway subclass can never
    force a real troubleshooting entry, in either direction: it neither has to be documented
    nor can it mask a real one hiding behind the same coincidental name.
    """
    found: set[type[WeftError]] = set()
    frontier = list(WeftError.__subclasses__())
    while frontier:
        cls = frontier.pop()
        if cls in found:
            continue
        found.add(cls)
        frontier.extend(cls.__subclasses__())
    return frozenset(
        cls for cls in found if cls.__module__.split(".")[0] in _FIRST_PARTY_TOP_LEVEL_PACKAGES
    )


def _derived_failure_set() -> frozenset[str]:
    """Every `WeftError` subclass name, plus every `PackStatus` value — the set `08` names."""
    _import_every_first_party_module()
    error_names = frozenset(cls.__name__ for cls in _all_weft_error_subclasses())
    status_names = frozenset(member.value for member in PackStatus)
    return error_names | status_names


def _troubleshooting_entries(markdown: str) -> frozenset[str]:
    return frozenset(_ENTRY_HEADING.findall(markdown))


def _guide_text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def missing_troubleshooting_entries(
    *, failures: frozenset[str], entries: frozenset[str], waived: frozenset[str]
) -> frozenset[str]:
    """Every name in `failures` that `entries` lacks and `waived` does not excuse.

    A pure function, on the same footing as `test_generated_docs.py`'s
    `missing_from_walked_set` — kept separate from the test body so the self-test below has
    something to call that is not the same comparison it is protecting.
    """
    return frozenset(name for name in failures if name not in entries and name not in waived)


# --- the floor ----------------------------------------------------------------------------


def test_at_least_one_failure_mode_is_derived_from_the_code() -> None:
    # Floor — `08` §3: a walk that found nothing would let every later assertion in this
    # file pass by having nothing to require, exactly the shape of the check this task
    # exists to replace.
    failures = _derived_failure_set()
    assert failures, (
        "no WeftError subclass or PackStatus member was found across "
        f"{_FIRST_PARTY_TOP_LEVEL_PACKAGES} — the walk itself is broken; fix it before "
        "trusting anything else in this file."
    )


def test_the_derived_set_names_classes_actually_defined_in_the_tree() -> None:
    # A sample, not the whole 22+5 — enough to catch the walk silently landing on the wrong
    # packages (say, picking up nothing because an import path changed) without hand-listing
    # every class this file already derives mechanically.
    failures = _derived_failure_set()
    for name in ("DuplicateRegistrationError", "PipelineResolutionError", "BlockingCallError"):
        assert name in failures, f"the code walk did not find {name} — is it still exported?"
    for value in ("active", "refused", "failed", "partial", "allowed, not installed"):
        assert value in failures, f"PackStatus no longer has a member valued {value!r}"


def test_the_derived_package_list_names_every_distribution_including_the_two_that_drifted() -> None:
    # Repair for a reviewer finding: the hand-written tuple this replaced had already
    # drifted twice — `weft_clean` (task 1.7) and `weft_enhance` (task 1.9) both shipped
    # without landing here, which would have let either pack's first `WeftError`
    # subclass ship with no troubleshooting entry and no failure from this file to catch
    # it. `_first_party_top_level_packages` must find both, plus the eighteen-distribution
    # floor `packages/` holds today — eight through Phase 1, `weft_pdf` at task 2.27,
    # `weft_openai` at task 2.29, `weft_retrieve` and `weft_generate` at task 2.4,
    # `weft_qdrant` at task 2.6, `weft_llm` at task 2.30, `weft_index` at task 2.31,
    # `weft_command` at task 3.1, `weft_eval` at task 4.1, and `weft_otel` at task 5.1d —
    # the last of these defines no `WeftError` subclass of its own (it registers no plugin
    # and raises nothing; a fallback exporter is reported on stderr, not an exception), so
    # its arrival moves only the count this assertion pins, not `manual/troubleshooting.md`.
    packages = _first_party_top_level_packages()
    assert "weft_clean" in packages
    assert "weft_enhance" in packages
    assert "weft_llm" in packages
    assert "weft_index" in packages
    assert "weft_command" in packages
    assert "weft_eval" in packages
    assert "weft_otel" in packages
    assert len(packages) == 19, (
        f"expected 19 first-party distributions under packages/, found {sorted(packages)} — "
        f"either a new one shipped (nothing to do here, this walk found it automatically) "
        f"or the walk itself broke."
    )


# --- the coverage check itself -------------------------------------------------------------


def test_at_least_one_troubleshooting_entry_is_present() -> None:
    # Floor on the document side, mirroring `test_generated_docs.py`'s own shape.
    entries = _troubleshooting_entries(_guide_text())
    assert entries, "manual/troubleshooting.md has no `### `name`` entries to check"


def test_every_failure_mode_has_a_troubleshooting_entry() -> None:
    # Arrange
    failures = _derived_failure_set()
    entries = _troubleshooting_entries(_guide_text())

    # Act
    missing = missing_troubleshooting_entries(
        failures=failures, entries=entries, waived=ERRORS_WITHOUT_TROUBLESHOOTING_ENTRY
    )

    # Assert — the coverage ratchet: a new WeftError subclass or PackStatus member landing
    # in code with no matching entry fails here, naming it, rather than aging silently the
    # way the reference's 17-of-23-evaluators gap did.
    assert not missing, (
        f"{sorted(missing)} landed in code with no manual/troubleshooting.md entry. Add a "
        f"`### `{sorted(missing)[0]}`` section — what it looks like, reproduced, and what "
        f"to do — or name it in ERRORS_WITHOUT_TROUBLESHOOTING_ENTRY if it is deliberately "
        f"excluded."
    )


def test_no_stale_troubleshooting_entries() -> None:
    # The reverse direction of the two-lists bug: an entry for a class or status that no
    # longer exists in code is exactly as misleading as a missing one — it teaches a reader
    # to distrust the page. Not part of the ratchet `08` §3 names (that one is one-directional,
    # "missing" only), so no waiver applies here; a stale entry has no legitimate reason to
    # stay and is simply deleted.
    failures = _derived_failure_set()
    entries = _troubleshooting_entries(_guide_text())

    stale = entries - failures
    assert not stale, (
        f"{sorted(stale)} appear in manual/troubleshooting.md but name no WeftError subclass "
        f"or PackStatus member that exists today — delete the stale entry."
    )


def test_missing_troubleshooting_entries_would_catch_a_dropped_one() -> None:
    # Arrange — the self-test `08` §3 requires of every floor: prove the comparison can
    # actually fail, rather than passing merely because nothing was compared.
    missing = missing_troubleshooting_entries(
        failures=frozenset({"SomeNewError", "active"}),
        entries=frozenset({"active"}),
        waived=frozenset(),
    )

    # Assert
    assert missing == frozenset({"SomeNewError"})


def test_a_waived_entry_is_excused() -> None:
    # AAA — a name present in the waiver is not reported missing even though no entry
    # documents it, proving the ratchet is an escape hatch a diff can see, not a silent one.
    missing = missing_troubleshooting_entries(
        failures=frozenset({"WaivedError"}), entries=frozenset(), waived=frozenset({"WaivedError"})
    )

    assert missing == frozenset()
