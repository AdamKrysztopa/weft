"""Fitness function 27 — every pipeline document a distribution ships is contributed.

`01` -> *Fitness functions* item 27. **Carried repair `R10.2`, and the rule it makes
mechanical is `docs/internal/lessons.md` `L5.15`: an extension point has a producing side and a
consuming side, and one of them is routinely built without the other.** That entry stands at
five recurrences across four phases, four of them logged and the fifth caught in the tree
rather than in a queue — which is why it arrives here as a check instead of as a sixth
sentence somewhere. `implement-ll`'s own routing rule: a rule that was applied and did not
bite is in the wrong artefact, and the repair is to move it, never to say it louder.

**The instance that bought this file.** Phase 10 task `10.14` shipped
`weft_retrieve/pipelines/index-with-adrap.yaml` — a real, resolvable document naming the
`adrap` plugin — and did not call `registrar.add_pipeline_resource` for it. The file existed,
parsed, and was reachable by nobody: not `weft pipeline list`, not the route catalogue, not
`weft index --pipeline`. **Fitness function 16 stayed green throughout**, and correctly so:
its subject is deliberately "the contributed catalogue... the ladder a user actually meets
from an installed wheel", so a document nobody contributed is outside what it asks about.
The producing side (a YAML file in a package) and the consuming side (a `PipelineResource` in
the discovery reports) are written in two different files, by two different acts, and until
this check nothing compared them.

**This is 16's complement, not a second copy of it.** 16 asks *does every plugin that could be
named by a document get named by one?* — a question about coverage, over the contributed set.
This asks *does every document that ships reach the contributed set at all?* — a question
about registration, over the shipped set. A tree can pass either and fail the other, and the
adrap defect is the worked example: 16 green, this one red.

**The two sides come from places that can genuinely disagree**, which is
`docs/internal/lessons.md` `L5.6`'s requirement and the reason this file does not grep for
`add_pipeline_resource`. One side is the filesystem — the `pipelines/*.yaml` files actually
present under each first-party source root. The other is a real `discover()` pass, reading
what each pack's `register()` actually did at run time. A textual check would compare a call
site against a filename and pass for a call whose arguments are wrong, which is the failure
`L5.23` names: a property about call shape needs a structural check, never a substring one.

**Sized before adopting, per `implement-ll`.** Measured 2026-09-08: **35** shipped pipeline
documents across two packages, **0** of them unregistered. The check walks a real population
and passes today because `10.14`'s repair already landed; it exists so the next one cannot.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from tests.discovery import installed_packs_except_the_canary
from weft_kernel.discovery import PackReport, discover
from weft_kernel.registry import Registry

#: The same never-dialled DSN fitness functions 11 and 16 both use, for the reason both state:
#: `PgVectorStore.__init__` opens no connection, so `weft-store`'s `register()` runs without a
#: container.
_PLACEHOLDER_STORE_SETTINGS: Final[Mapping[str, Mapping[str, object]]] = {
    "store": {"dsn": "postgresql://ff27-placeholder/placeholder"},
    "blob": {"root": "/nonexistent-blob-root"},
}

#: A shipped pipeline document permitted to reach no pack's `register()`, as
#: `"<package>/<resource>"` — the same spelling `add_pipeline_resource` takes.
#:
#: **Pinned empty, and it should be hard to add to.** The only honest entry here is a document
#: that ships inside a package and is deliberately *not* a rung — a fixture, or a worked example
#: a guide quotes. Neither exists today: a worked example lives under `manual/`, where fitness
#: function 11(b) resolves it and this check never looks. "Not registered yet" is the reason
#: this constant exists to refuse, because that is precisely what `10.14` shipped.
UNREGISTERED_DOCUMENTS_WAIVED: Final[frozenset[str]] = frozenset()


def _source_roots() -> tuple[Path, Path]:
    """`packages/` and the repository root, resolved from this file rather than the cwd."""
    root = Path(__file__).resolve().parents[2]
    return root / "packages", root


def _shipped_documents() -> frozenset[str]:
    """Every `pipelines/*.yaml` under a first-party package, as `"<package>/<resource>"`.

    The path is rebuilt in `add_pipeline_resource`'s own vocabulary — the importable package
    name and the resource path relative to it — rather than as a filesystem path, so the two
    sides of this check are comparable without either learning the other's spelling.
    """
    packages_dir, _root = _source_roots()
    found: set[str] = set()
    for document in packages_dir.glob("*/src/*/pipelines/*.yaml"):
        package = document.parent.parent.name
        found.add(f"{package}/{document.parent.name}/{document.name}")
    return frozenset(found)


def _contributed_documents() -> frozenset[str]:
    """Every `PipelineResource` a real discovery pass saw, in the same spelling.

    A genuine `discover()` rather than a read of any source file: what is being checked is
    what `register()` *did*, and a pack whose call names a resource it does not ship would
    otherwise be indistinguishable from one that ships a resource it does not name.
    """
    registry = Registry()
    reports: tuple[PackReport, ...] = discover(
        registry,
        allow=installed_packs_except_the_canary(),
        pack_settings=_PLACEHOLDER_STORE_SETTINGS,
    )
    return frozenset(
        f"{resource.package}/{resource.resource}"
        for report in reports
        for resource in report.pipeline_resources
    )


def _unregistered(
    shipped: frozenset[str], contributed: frozenset[str], waived: frozenset[str]
) -> frozenset[str]:
    """The comparison itself, factored out so the failure self-test drives the identical code —
    fitness function 16's own convention, and `docs/internal/lessons.md` `L5.19`'s floor: a check
    whose real subject is legitimately empty needs a self-test proving the comparison is not
    vacuous.
    """
    return shipped - contributed - waived


def test_the_check_can_actually_fail() -> None:
    # The falsification, run against the identical function the real check calls, and named
    # the way `test_ff0b_checks_are_real.py` clause (b) requires — that check is fitness
    # function 0's other half and it has enforced this on every file in this directory since
    # Phase 5's drain, written from `L5.6` and `L5.19` themselves. Without this,
    # every assertion in this file would be satisfied by a comparison that can only ever be
    # empty — which is the shape `L5.6` and `L5.19` name and this file's own docstring cites.
    # The pair below is `10.14`'s defect in miniature: a document shipped, nothing registered.
    shipped = frozenset({"weft_retrieve/pipelines/index-with-adrap.yaml"})
    contributed = frozenset({"weft_retrieve/pipelines/index-text.yaml"})

    assert _unregistered(shipped, contributed, frozenset()) == shipped
    assert _unregistered(shipped, contributed, shipped) == frozenset()


def test_the_waiver_is_pinned_empty() -> None:
    # The ratchet. An entry here is a visible act in a diff, never a silent edit —
    # `CLAUDE.md` -> *Quality gates*.
    assert frozenset() == UNREGISTERED_DOCUMENTS_WAIVED


def test_this_check_walks_a_real_population() -> None:
    # `docs/internal/lessons.md` `L5.19`: where a check compares two sets, a walk that finds nothing
    # compares empty against empty and passes by asking nothing. This is the floor that makes
    # the assertion below mean something — and it is the rule fitness function 28 generalises
    # to every check in this directory.
    shipped = _shipped_documents()
    assert len(shipped) >= 2, (
        f"only {len(shipped)} shipped pipeline documents were found — this check walks "
        f"packages/*/src/*/pipelines/*.yaml and something has moved, so its pass below "
        f"means nothing."
    )


def test_every_shipped_pipeline_document_is_contributed_by_its_pack() -> None:
    # Arrange
    shipped = _shipped_documents()
    contributed = _contributed_documents()

    # Act
    unregistered = _unregistered(shipped, contributed, UNREGISTERED_DOCUMENTS_WAIVED)

    # Assert
    assert not unregistered, (
        f"{len(unregistered)} pipeline document(s) ship inside a package and reach no "
        f"`registrar.add_pipeline_resource` call, so nothing can run them and fitness "
        f"function 16 cannot see them: {sorted(unregistered)}. Add the registration to that "
        f"pack's `register()`, or, if the document is genuinely not a rung, name it in "
        f"UNREGISTERED_DOCUMENTS_WAIVED with the reason."
    )


def test_every_contributed_resource_is_a_document_that_exists() -> None:
    # Arrange — the other direction, and it is not symmetry for its own sake: a pack may name a
    # resource it does not ship, which `load_contributed` would meet as a read failure at the
    # first invocation rather than here.
    packages_dir, _root = _source_roots()
    contributed = _contributed_documents()
    first_party = {
        f"{document.parent.parent.name}/{document.parent.name}/{document.name}"
        for document in packages_dir.glob("*/src/*/pipelines/*.yaml")
    }
    packages_shipping_documents = {name.split("/", 1)[0] for name in first_party}

    # Act — only first-party packages are in scope; an installed third party's resource is
    # real and lives in a wheel this walk cannot see.
    claimed = {name for name in contributed if name.split("/", 1)[0] in packages_shipping_documents}
    missing = claimed - first_party

    # Assert
    assert not missing, (
        f"{len(missing)} pack registration(s) name a pipeline resource that does not exist "
        f"in this tree: {sorted(missing)}."
    )
