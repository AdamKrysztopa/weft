"""Fitness function 12 — an unknown name names the alternatives. `01` -> *Fitness
functions* item 12; `05` -> G11; `docs/build-ledger.md` 2.36, which turns this on.

"Every error class whose failure mode is an unresolvable name carries those options
as a **typed field**, not only interpolated into its message, and the check asserts
that across the family with a waiver constant pinned empty in the style of item 0."
Item 0's own words apply unchanged: a check that greps a formatted message for a
comma-separated list is a test of prose, and it passes the moment someone writes a
plausible-looking sentence.

**How the family is identified — structurally, not by class name.** `weft_kernel.
errors.UnresolvedNameError` is a marker every family member mixes in alongside
whichever `WeftError` subclass it already is (`PipelineResolutionError`'s four
fields, `LLMError`'s `provider`/`model`, or plain `WeftError`) — it declares no
`__init__` of its own on purpose, so it never has to cooperate with each family
member's own constructor chain; each subclass sets `self.valid_options` itself, the
same way it already sets any of its other typed fields. Membership is therefore a
mechanical fact: `issubclass(cls, UnresolvedNameError)`. `NAME_RESOLUTION_FAMILY`
below is the pinned, hand-audited set of qualnames that inherit the marker today —
audited the way task 2.34 and 2.35 audited their own reference claims, by reading every
raise site of every `WeftError` subclass in the tree (82 today: `test_ff9c_every_
contract_has_a_stranger.py`'s own `_exported_protocol_classes`-style walk finds 80
`WeftError` subclasses across the first-party packages, plus `WeftError` itself and
`weft_retrieve.boolean.BooleanSyntaxError`, a bare `Exception` never routed through
this hierarchy at all) for whether it already computes and interpolates a concrete,
enumerable collection of the names that *were* valid where the one given was not.
That is the line: a class whose message already says "X available: {sorted(...)}"
is this family and had the field withheld from it; a class reporting a collision, a
malformed shape, or a type mismatch is a different failure mode this function does
not reach, because there is no alternative *name* to offer — `weft_kernel.discovery.
EnvInterpolationError`, say, cannot enumerate "valid" environment variable names,
and `weft_kernel.registry.DuplicateRegistrationError` reports two names that both
already resolved, never one that failed to. **`01` claimed 18; the audit below found
20** — `weft_cli.run_services.StoreCapabilityMissingError` and `weft_prompts.errors.
TemplateVariableError` were the two `01` missed, both already carrying a real
alternatives collection at their own raise site before this task gave it a field.

**Two ratchets**, `test_ff9c_every_contract_has_a_stranger.py`'s own shape. `NAME_
RESOLUTION_FAMILY` is not itself a waiver — it is the membership list, and it is
guarded against silent omission by `test_the_discovered_family_matches_the_pinned_
list`: every `UnresolvedNameError` subclass this walk actually finds under a
first-party package must be named here, and every name here must resolve to a real
one, both directions, so a new family member that inherits the marker and is not
added to this list fails the build rather than passing invisibly. `FAMILY_MEMBERS_
WITHOUT_A_TYPED_FIELD` is the real waiver `01` asks for — pinned empty, changeable
only by a dated decision-log entry, never a place to park an unfinished migration.

**What this cannot catch, stated rather than papered over.** A brand-new error class
whose failure mode genuinely is an unresolvable name but that never inherits
`UnresolvedNameError` at all is invisible to every check in this file — the same
honest limit `test_ff9c`'s own service ratchet carries for a `Protocol` nobody
thought to classify. `01`'s own "how it fails" example is closer to home than that:
a *raise site* of an *existing* family member that forgets to collect the registered
names is caught immediately, at import time, by Python itself — `valid_options` is a
required keyword-only parameter on every family member's own `__init__`, with no
default, so a call site omitting it never constructs an instance at all rather than
constructing one with a silently empty tuple. That is the structural fix task 2.36
does, not only the check that proves it happened.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import tomllib
import typing
from pathlib import Path
from typing import Final, cast

from weft_kernel.errors import UnresolvedNameError, WeftError

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: Fitness function 12's family — every `UnresolvedNameError` subclass in the
#: first-party tree today, hand-audited against every raise site (see the module
#: docstring). Guarded against silent omission by `test_the_discovered_family_
#: matches_the_pinned_list`, not left to stand on its own the way a plain hand list
#: would.
NAME_RESOLUTION_FAMILY: Final[frozenset[str]] = frozenset(
    {
        "weft_kernel.registry.UnknownPluginError",
        "weft_kernel.registry.UnresolvedPluginPinError",
        "weft_kernel.context.UnresolvedServiceError",
        "weft_kernel.discovery.UnknownPackSettingsError",
        "weft_kernel.resolution.UnknownParentPipelineError",
        "weft_kernel.resolution.UndefinedVarError",
        "weft_kernel.resolution.StaleOperatorTargetError",
        "weft_kernel.runner.UnknownFallbackError",
        "weft_cli.compile.UnknownStagePluginError",
        "weft_cli.compile.AmbiguousStageContractError",
        "weft_cli.config_surface.UnknownConfigKeyError",
        "weft_cli.ingest.UnclaimedFormatError",
        "weft_cli.ingest.AmbiguousExtractorError",
        "weft_cli.ingest.PipelineMissingExtractStageError",
        "weft_cli.commands.UnresolvedPluginNameError",
        "weft_cli.llm_roles.UnknownLLMKeyError",
        "weft_cli.permission_policy.UnknownPermissionKeyError",
        "weft_cli.reconcile_policy.UnknownReconcileKeyError",
        "weft_cli.eval_commands.UnknownRunIdError",
        "weft_cli.pipeline_catalogue.UnknownPipelineNameError",
        "weft_eval.offline.UnknownMetricNameError",
        "weft_cli.services.UnknownServiceKeyError",
        "weft_cli.route_ask.UnroutedPipelineNameError",
        "weft_cli.run_services.StoreCapabilityMissingError",
        "weft_llm.models.UnknownModelError",
        "weft_llm.models.AmbiguousModelError",
        "weft_llm.roles.UnmappedLLMRoleError",
        "weft_store.fields.UnaddressableFieldError",
        "weft_store.pgvector_store.UnknownTextSearchConfigError",
        "weft_store.contract.UnhandledFilterOpError",
        "weft_prompts.errors.TemplateVariableError",
    }
)

#: `01`'s own ratchet shape, item 0's style. **Pinned empty.** A family member with
#: no typed `valid_options` field is work task 2.36 does, never a name parked here.
FAMILY_MEMBERS_WITHOUT_A_TYPED_FIELD: Final[frozenset[str]] = frozenset()


def _first_party_top_level_packages() -> tuple[str, ...]:
    """Every first-party distribution's top-level import name, off `packages/*/pyproject.toml`.

    The identical derivation `tests/docs/test_troubleshooting_coverage.py`'s own
    `_first_party_top_level_packages` uses, restated here rather than imported
    across test files — `test_ff11_pipeline_integrity.py`'s own precedent for why:
    "the same computation... restated here... on the same 'one self-contained
    scenario' reasoning."
    """
    names: list[str] = []
    for package_dir in sorted(p for p in PACKAGES_ROOT.iterdir() if p.is_dir()):
        pyproject = package_dir / "pyproject.toml"
        if not pyproject.is_file():
            continue
        with pyproject.open("rb") as handle:
            document = tomllib.load(handle)
        project = cast("dict[str, object]", document.get("project", {}))
        name = project.get("name")
        if isinstance(name, str):
            names.append(name.replace("-", "_"))
    return tuple(names)


_FIRST_PARTY_TOP_LEVEL_PACKAGES: Final[tuple[str, ...]] = _first_party_top_level_packages()


def _import_every_first_party_module() -> None:
    """Import every submodule of every first-party distribution.

    So `UnresolvedNameError.__subclasses__()` below sees every subclass ever
    defined, not only the ones some other test happened to import first — the
    identical reasoning and the identical walk `tests/docs/test_troubleshooting_
    coverage.py`'s own `_import_every_first_party_module` uses for `WeftError`.
    """
    for top_level in _FIRST_PARTY_TOP_LEVEL_PACKAGES:
        package = importlib.import_module(top_level)
        package_path = getattr(package, "__path__", None)
        if package_path is None:
            continue
        prefix = f"{top_level}."
        for module_info in pkgutil.walk_packages(package_path, prefix=prefix):
            importlib.import_module(module_info.name)


def _qualname(cls: type[object]) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _all_unresolved_name_subclasses() -> frozenset[type[UnresolvedNameError]]:
    """Every `UnresolvedNameError` subclass defined in the first-party source tree.

    Recursive over `__subclasses__()`, exactly as `test_troubleshooting_coverage.
    py`'s own `_all_weft_error_subclasses` walks `WeftError` — a class that
    subclasses an existing family member rather than the marker directly must
    still be found. `WeftError.__subclasses__()` is process-global, so the same
    file's own reasoning applies: filtered to `__module__`s under a first-party
    top-level package, so a throwaway subclass a *test* defines can neither be
    required here nor mask a real one.
    """
    _import_every_first_party_module()
    found: set[type[UnresolvedNameError]] = set()
    frontier = list(UnresolvedNameError.__subclasses__())
    while frontier:
        cls = frontier.pop()
        if cls in found:
            continue
        found.add(cls)
        frontier.extend(cls.__subclasses__())
    return frozenset(
        cls for cls in found if cls.__module__.split(".")[0] in _FIRST_PARTY_TOP_LEVEL_PACKAGES
    )


def _resolve(qualname: str) -> type[object] | None:
    """The class `qualname` names, or `None` if the module or the attribute is gone."""
    module_name, _, class_name = qualname.rpartition(".")
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    return getattr(module, class_name, None)


def _carries_valid_options_field(cls: type[object]) -> bool:
    """Whether `cls.__init__` declares `valid_options: tuple[str, ...]` as a required field.

    Structural: reads the constructor's own resolved type hints and the parameter's
    own default, never a raised message's text. `typing.get_type_hints` resolves a
    string annotation exactly as a live one — some of these modules carry `from
    __future__ import annotations` and some do not, and a check that only worked
    for one style would be an accident, not a property. Required, not merely
    present: a `valid_options` with a default could be silently omitted at a raise
    site and the class would still construct, which is the reference's own defect this
    function exists to make structurally impossible rather than merely discouraged.
    """
    try:
        hints = typing.get_type_hints(cls.__init__)
    except (NameError, TypeError):
        return False
    if hints.get("valid_options") != tuple[str, ...]:
        return False
    parameter = inspect.signature(cls.__init__).parameters.get("valid_options")
    return parameter is not None and parameter.default is inspect.Parameter.empty


def members_without_the_typed_field(
    *, members: frozenset[type[object]], waived: frozenset[str]
) -> frozenset[str]:
    """Every member of `members` that does not carry `valid_options`, unless `waived` names it.

    A pure function, kept separate from both classes' own computation — `weft_cli.
    contract_reference.missing_from_walked_set`'s own precedent, restated by `test_
    ff9c_every_contract_has_a_stranger.py`'s own `missing_strangers`: "the check has
    something to call that is not the same code path it is checking."
    """
    return frozenset(
        _qualname(cls)
        for cls in members
        if not _carries_valid_options_field(cls) and _qualname(cls) not in waived
    )


def _discovered_family_mismatch(
    *, pinned: frozenset[str], discovered: frozenset[str]
) -> tuple[frozenset[str], frozenset[str]]:
    """`(unpinned, stale)` — discovered members `pinned` never names, and pinned names
    nothing discovers any more. A pure function for the identical reason `members_
    without_the_typed_field` is one: something the self-test below can call that is
    not the exact assertion it protects.
    """
    return frozenset(discovered - pinned), frozenset(pinned - discovered)


# --- the floor ------------------------------------------------------------------------


def test_at_least_one_family_member_is_named() -> None:
    # Floor — a comparison against an empty family would pass by having nothing to
    # require, `01` item 9's own floor rule applied here.
    assert NAME_RESOLUTION_FAMILY


def test_every_named_family_member_resolves() -> None:
    # Floor — every pinned qualname must still be a real, importable class. A rename
    # or a deletion that left a stale entry here would otherwise let the coverage
    # check below silently skip it rather than fail loudly.
    missing = sorted(qualname for qualname in NAME_RESOLUTION_FAMILY if _resolve(qualname) is None)
    assert not missing, f"pinned but no longer resolves: {missing}"


def test_every_named_family_member_is_an_unresolved_name_error() -> None:
    # Sanity — every pinned qualname must actually carry the structural marker
    # membership is defined by. A name added to NAME_RESOLUTION_FAMILY without
    # `UnresolvedNameError` mixed in would otherwise be silently accepted by every
    # test below it, on the strength of being spelled correctly alone.
    not_marked = sorted(
        qualname
        for qualname in NAME_RESOLUTION_FAMILY
        if not issubclass(_resolve(qualname) or object, UnresolvedNameError)
    )
    assert not not_marked, (
        f"pinned in NAME_RESOLUTION_FAMILY but not a UnresolvedNameError subclass: "
        f"{not_marked} — mix the marker in, or this name does not belong in the family"
    )


# --- the discovery ratchet: nothing joins or leaves the family silently ---------------


def test_the_discovered_family_matches_the_pinned_list() -> None:
    # Arrange / Act — the left side is `NAME_RESOLUTION_FAMILY`, computed once by hand
    # and audited (module docstring); the right side is a live walk of every
    # `UnresolvedNameError` subclass the first-party tree actually defines today,
    # computed from neither the left side nor from itself.
    discovered = frozenset(_qualname(cls) for cls in _all_unresolved_name_subclasses())

    # Act
    unpinned, stale = _discovered_family_mismatch(
        pinned=NAME_RESOLUTION_FAMILY, discovered=discovered
    )

    # Assert
    assert not unpinned, (
        f"UnresolvedNameError subclass(es) not named in NAME_RESOLUTION_FAMILY: "
        f"{sorted(unpinned)} — a new family member must be added to the pinned list "
        f"in the same commit that mixes the marker in, or it is invisible to fitness "
        f"function 12's own coverage check below."
    )
    assert not stale, (
        f"NAME_RESOLUTION_FAMILY names {sorted(stale)}, which no longer resolves to an "
        f"UnresolvedNameError subclass — remove the stale entry, or restore the marker."
    )


def test_the_discovery_ratchet_can_actually_fail() -> None:
    # Error case — the vacuousness proof `07` §2's own ratchets require: fabricate a
    # discovered set the pinned list does not name, and a pinned name discovery no
    # longer backs, and prove the comparison itself reports both, on inputs neither
    # side derives from the other.
    unpinned, stale = _discovered_family_mismatch(
        pinned=frozenset({"weft_kernel.registry.UnknownPluginError", "pkg.mod.GoneError"}),
        discovered=frozenset(
            {"weft_kernel.registry.UnknownPluginError", "pkg.mod.NeverPinnedError"}
        ),
    )
    assert unpinned == frozenset({"pkg.mod.NeverPinnedError"})
    assert stale == frozenset({"pkg.mod.GoneError"})


# --- the coverage check itself: every family member carries the typed field ----------


def test_waiver_list_is_empty() -> None:
    # `07` §2's own ratchet policy, restated for this family: an exemption is a
    # visible entry in a diff, changeable only by a dated decision-log entry, never
    # a silent edit — and `01` asks that this one stay empty, not merely small.
    assert frozenset() == FAMILY_MEMBERS_WITHOUT_A_TYPED_FIELD


def test_every_family_member_carries_valid_options_as_a_typed_field() -> None:
    # Arrange
    members = frozenset(
        cast("type[object]", _resolve(qualname))
        for qualname in NAME_RESOLUTION_FAMILY
        if _resolve(qualname) is not None
    )
    assert members, "the resolves-check above should already have failed if this is empty"

    # Act
    missing = members_without_the_typed_field(
        members=members, waived=FAMILY_MEMBERS_WITHOUT_A_TYPED_FIELD
    )

    # Assert
    assert not missing, (
        f"family member(s) with no typed valid_options field: {sorted(missing)} — `01` "
        f"requirement 5's other half: the refusal must carry the valid options as a "
        f"typed field a caller can read, not only a comma-separated list inside the "
        f"message a human has to notice."
    )


def test_missing_typed_field_check_can_actually_fail() -> None:
    # Error case — the self-test `07` §2 requires: a fabricated class with no
    # `valid_options` field at all, so this function is proven able to report a real
    # gap rather than having stopped being able to fail. Mirrors `test_ff9c_every_
    # contract_has_a_stranger.py`'s own `test_missing_strangers_can_actually_fail`.
    class _ForgotTheFieldError(WeftError, UnresolvedNameError):
        pass  # inherits WeftError.__init__ unchanged — no valid_options anywhere

    missing = members_without_the_typed_field(
        members=frozenset({_ForgotTheFieldError}), waived=frozenset()
    )

    assert missing == frozenset({_qualname(_ForgotTheFieldError)})


def test_missing_typed_field_check_honours_the_waiver() -> None:
    class _WaivedForTheTestError(WeftError, UnresolvedNameError):
        pass

    missing = members_without_the_typed_field(
        members=frozenset({_WaivedForTheTestError}),
        waived=frozenset({_qualname(_WaivedForTheTestError)}),
    )

    assert missing == frozenset()


def test_a_family_member_with_the_field_is_not_reported() -> None:
    # The other direction of the self-test: a class shaped exactly like a real family
    # member — a required, correctly annotated `valid_options` — must not be flagged,
    # or the check above is not measuring what it claims to.
    class _CarriesTheFieldError(WeftError, UnresolvedNameError):
        def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
            super().__init__(message)
            self.valid_options = valid_options

    missing = members_without_the_typed_field(
        members=frozenset({_CarriesTheFieldError}), waived=frozenset()
    )

    assert missing == frozenset()


def test_an_optional_valid_options_field_is_not_enough() -> None:
    # Error case — a `valid_options` with a default is exactly the reference's own defect:
    # a raise site could silently omit it and the class would still construct with an
    # empty tuple, indistinguishable from "genuinely nothing to offer". This proves
    # `_carries_valid_options_field` requires the field, not merely its name.
    class _OptionalFieldError(WeftError, UnresolvedNameError):
        def __init__(self, message: str, *, valid_options: tuple[str, ...] = ()) -> None:
            super().__init__(message)
            self.valid_options = valid_options

    missing = members_without_the_typed_field(
        members=frozenset({_OptionalFieldError}), waived=frozenset()
    )

    assert missing == frozenset({_qualname(_OptionalFieldError)})
