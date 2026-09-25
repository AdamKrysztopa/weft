"""Fitness function 31 — every registered `ExtModel` is constructed by something that ships.

**`docs/internal/lessons.md` `L19.7`, and it is `L5.15`'s sixth recurrence** — *an extension
point has a producing side and a consuming side, and one of them is routinely built without the
other*. Fitness function 27 made that rule mechanical for pipeline documents; this makes it
mechanical for the payload facts a pack registers, which is where the sixth instance was found.

**The instance.** `weft_clean.Language` is a registered `ExtModel` that **nothing anywhere
constructs** — not a pack, not a stage, not the CLI. `docs/01-high-level-plan.md` has recorded
it as a gap since Phase 0. A registration is a published claim that something will attach this
fact to a node; a model nothing writes is that claim with nothing behind it, and every reader
of it answers emptily rather than wrongly, which is `L6.14` and is the failure mode with no
symptom.

**Sized before adopting, and the sizing is why this check is narrow.** Two forms were measured
on 2026-09-13:

- *An `ExtModel` with no production **reader***, the form the defect was noticed through, walks
  19 and fails **12** — and most of those twelve are correct. `CorrectiveTrace`,
  `IterativeRetrievalTrace`, `RefinementTrace`, `ExtractionTally`, `BooleanPlan` and `Agreement`
  are **traces**: written for a person reading the record, never read back by code. A fact
  written to be read by a human is not a fact with a missing consumer, and a check failing
  twelve correct sites is one whose waiver is where the real violation hides (`R10.2`).
- *An `ExtModel` with no production **writer** at all* walks 19 and fails **1**. That is the
  measurable, small population `R10.2` says to look for, and it is the form adopted here.

So this file asks the weaker question on purpose. A model with a writer and no reader is still
a real gap — `weft_enhance.Keywords` is one, registered, placed by a shipped pipeline, four
times in the user manual, and read by nothing under `packages/` — but it is a gap a reading has
to judge, and it is filed as a build task rather than asserted here.

**The two sides can genuinely disagree**, which is `L5.6`'s requirement. One side is a real
`discover()` pass: what each pack's `register()` actually handed to the registrar, read off
`PackReport.ext_models`. The other is an `ast` walk over the shipped source for a call whose
callee is that class's own name. Neither is derived from the other, and a textual grep is not
used for the second — a substring match would count the class statement, the import, the
docstring and the annotation as writers, which is `L5.23`'s structural-not-substring rule.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from tests.discovery import installed_packs_except_the_canary
from weft_kernel.discovery import discover
from weft_kernel.registry import Registry

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: The shipped source roots. Tests are excluded deliberately: a construction site in a test is
#: what `Language` already has, and counting it would make the check pass on the one thing it
#: was written to catch.
_SOURCE_ROOTS: Final[tuple[Path, ...]] = (
    _REPO_ROOT / "packages" / "weft-rag" / "src",
    _REPO_ROOT / "packages" / "weft-kernel" / "src",
)

#: The same never-dialled DSN fitness functions 11, 16 and 27 use, and for the reason all three
#: state: `PgVectorStore.__init__` opens no connection, so `register()` runs with no container.
_PLACEHOLDER_STORE_SETTINGS: Final[Mapping[str, Mapping[str, object]]] = {
    "store": {"dsn": "postgresql://ff31-placeholder/placeholder"},
}

#: **Pinned empty is the goal and it is not empty yet.** `weft_clean.Language` is the one entry,
#: and it is a gap `docs/01-high-level-plan.md` has recorded since Phase 0 rather than a
#: judgement this check gets wrong. Carried repair `R19.12` deprecated it for removal in
#: `weft-rag` 3.0.0; the owner withdrew that at task `43.38` (2026-09-25), because
#: `polish-dictionary-spacing` scopes itself by it and would otherwise apply to every node. It
#: leaves when a detect stage writes it or that fixer retires. A second entry is a visible act in a
#: diff, which is the whole point of a ratchet.
WAIVED: Final[tuple[str, ...]] = ("Language",)


def _constructed_names() -> frozenset[str]:
    """Every name that appears as the callee of a call in shipped source.

    Structural rather than textual: `ast` distinguishes `Language(...)` from `class Language`,
    `import Language`, `list[Language]` and the word in a docstring, and only the first is a
    writer. `Name` and `Attribute` callees both count — `payload.Language(...)` is as much a
    construction as `Language(...)`.
    """
    found: set[str] = set()
    for root in _SOURCE_ROOTS:
        for path in root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - a broken tree fails
                continue  # elsewhere, loudly, and this check is not where that is reported
            found |= _callee_names(tree)
    return frozenset(found)


def _callee_names(tree: ast.Module) -> set[str]:
    """The bare or final-attribute name of every call's callee in one parsed file."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name):
            found.add(callee.id)
        elif isinstance(callee, ast.Attribute):
            found.add(callee.attr)
    return found


def _registered_ext_models() -> dict[str, str]:
    """`{class name: the pack that registered it}`, from a real discovery pass."""
    registry = Registry()
    reports = discover(
        registry,
        allow=installed_packs_except_the_canary(),
        pack_settings=_PLACEHOLDER_STORE_SETTINGS,
    )
    # `pack` is optional on a report — a discovery that failed before the pack named itself has
    # none — so the fallback keeps the message readable rather than printing `None`.
    return {
        model.__name__: report.pack or "an unnamed pack"
        for report in reports
        for model in report.ext_models
    }


def test_every_registered_ext_model_is_constructed_by_shipped_code() -> None:
    registered = _registered_ext_models()
    assert registered, "discovery registered no ext models at all — the check has no subject"
    constructed = _constructed_names()
    unwritten = sorted(
        f"{name} (registered by {pack})"
        for name, pack in registered.items()
        if name not in constructed and name not in WAIVED
    )
    assert not unwritten, (
        "a registered ExtModel that nothing constructs is a published claim with nothing "
        "behind it — every reader of it answers emptily rather than wrongly "
        "(docs/internal/lessons.md L19.7, L6.14):\n  " + "\n  ".join(unwritten)
    )


def test_the_check_can_actually_fail() -> None:
    """The comparison is not vacuous, and the waiver is live.

    Two halves, because the check has two ways of meaning nothing. **The subject is
    non-empty**: a real discovery pass registers models, so the set being walked is not the
    empty set passing by default. **The waiver still fires**: `Language` is waived, and the
    check must be able to see that it would otherwise fail — asserting the waived name is
    *present* would only prove the tuple has a string in it, which is the non-vacuity test
    `L6.29` found to be worthless. This asserts the name is registered and unconstructed, which
    is the condition the waiver is suppressing.
    """
    registered = _registered_ext_models()
    assert len(registered) >= 10, f"expected the shipped ext models, walked {len(registered)}"
    constructed = _constructed_names()
    for waived in WAIVED:
        assert waived in registered, f"{waived} is waived and is not registered — stale waiver"
        assert waived not in constructed, (
            f"{waived} is waived as unconstructed and something now constructs it: "
            "remove it from WAIVED, which is the ratchet tightening"
        )
