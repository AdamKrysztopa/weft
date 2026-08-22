"""Version skew — `weft plugins doctor`'s report that an installed distribution does not
satisfy another installed distribution's own declared dependency specifier.

Task 5.2e, `docs/09-release.md` §2.3 answer 1 (G9): "A contract version requirement *is*
the distribution dependency specifier, so the resolver refuses an incompatible install
before the environment is broken. Runtime skew — an editable install, a forced install, a
workspace — is detected and reported by `weft plugins doctor`, never used to refuse a
load. There is no kernel load-time version check and the kernel gains no lines." This
module is that report, and it lives here — `weft-cli`, not `weft-kernel` — for exactly
that reason: a `doctor` feature is the CLI's, and G9's own answer says the kernel gains
zero lines for it.

**Two independent sources, deliberately not derived from each other**
(`docs/lessons.md` L5.6: a declaration derived from the thing it claims to verify proves
nothing). Source A is a distribution's own installed version —
`importlib.metadata.version(name)`, read off its own `.dist-info/METADATA`. Source B is a
*different*, already-installed distribution's own declared requirement on that name —
`importlib.metadata.requires(other)`, each entry a PEP 508 string parsed with
`packaging.requirements.Requirement`. Task 5.2a is what makes this comparison meaningful
rather than vacuous: every intra-repo dependency now carries a real `>=X,<MAJOR+1` range
instead of a bare, unconstrained name, so there is a real specifier for an installed
version to disagree with. A `uv sync`ed workspace never disagrees with itself this way —
skew is exactly the three cases `docs/09-release.md` §2.3 names as its sources: an
editable install whose checked-out code has moved past its own recorded version, a forced
install (`pip install --force-reinstall`, a hand-edited `.dist-info`), or a workspace whose
lockfile has drifted from what is actually on disk.

**Distinct from fitness function 6**
(`tests/architecture/test_ff6_contract_version_binding.py`), which reads a *contract's*
version by AST-parsing `contract.py` against the distribution version recorded in
`pyproject.toml` — a build-time check that a source *published* the right number, run
against the checked-out tree. This module asks whether a number already published is
*satisfied at runtime*, against whatever is actually installed; it never opens a
`contract.py` or a `pyproject.toml`, and FF6 never reads `importlib.metadata`. The two
checks would agree in the ordinary case and are not built to substitute for each other —
FF6 cannot see a forced install, and this module cannot see a contract whose version was
never bumped when it should have been.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from importlib import metadata

from packaging.markers import UndefinedEnvironmentName
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from pydantic import BaseModel, ConfigDict

_RequiresFn = Callable[[str], "list[str] | None"]
_VersionFn = Callable[[str], str]

#: Every requirement this module reports skew against is on a distribution named with this
#: prefix — `docs/build-ledger.md` task 5.2a's own intra-repo range applies to any
#: distribution named `weft-...`, first- or third-party alike, so the filter is a prefix
#: test, never a maintained list of distribution names.
_WEFT_PREFIX = "weft-"


class SkewReport(BaseModel):
    """`requiring_distribution` declares `specifier` on `required_distribution`, but the
    version actually installed does not satisfy it.

    Frozen, like every model this project returns (`CLAUDE.md`). `specifier` and
    `installed_version` are the plain strings `packaging` already renders — nothing past
    this module's own boundary needs `packaging`'s types, so none cross it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    requiring_distribution: str
    required_distribution: str
    specifier: str
    installed_version: str


def detect_skew(
    distributions: Iterable[str] | None = None,
    *,
    requires: _RequiresFn | None = None,
    version: _VersionFn | None = None,
) -> tuple[SkewReport, ...]:
    """Every declared requirement on a `weft-...` distribution whose installed version
    does not satisfy it.

    `distributions` is every *requiring* distribution to read `importlib.metadata.requires`
    off, defaulting to every distribution installed in the current environment — so a
    third-party pack's own mis-declared range is caught exactly as a first-party one's
    would be, with no maintained list of "the weft distributions" to keep in step. A
    caller that already enumerated a narrower set may pass it instead.

    `requires`/`version` default to `importlib.metadata.requires`/`.version` and exist for
    the identical reason `weft_kernel.discovery.discover`'s own `entry_points` parameter
    does: a test proves this module's own logic — parsing, marker evaluation, specifier
    comparison — against a hand-built double instead of a real, force-installed
    distribution, which is what the fitness function and the shipped binary are for.

    Silent about what this function is not built to answer, never wrong about it: a
    requirement string `packaging` cannot parse, a marker this process cannot evaluate (an
    `extra` with no active extra to check it against), or a required distribution that is
    not installed at all — the resolver's own refusal territory, `docs/09-release.md` §2.3's
    unlabelled row, not skew — are skipped rather than misreported.
    """
    requires_fn = requires if requires is not None else metadata.requires
    version_fn = version if version is not None else metadata.version
    names = sorted(set(distributions) if distributions is not None else _installed_names())
    reports: list[SkewReport] = []
    for requiring in names:
        try:
            requirements = requires_fn(requiring) or ()
        except metadata.PackageNotFoundError:
            continue
        for raw in requirements:
            report = _check(requiring, raw, version_fn)
            if report is not None:
                reports.append(report)
    return tuple(reports)


def _installed_names() -> tuple[str, ...]:
    """Every distribution name `importlib.metadata` can see installed, deduplicated."""
    return tuple(
        sorted({name for dist in metadata.distributions() if (name := dist.metadata.get("Name"))})
    )


def _check(requiring: str, raw: str, version_fn: _VersionFn) -> SkewReport | None:
    """`raw` — one of `requiring`'s own declared requirement strings — as a `SkewReport`,
    or `None` if it names no skew this function can report.
    """
    try:
        requirement = Requirement(raw)
    except InvalidRequirement:
        return None
    if not canonicalize_name(requirement.name).startswith(_WEFT_PREFIX):
        return None
    if requirement.marker is not None:
        try:
            if not requirement.marker.evaluate():
                return None
        except UndefinedEnvironmentName:
            return None
    try:
        installed_version = version_fn(requirement.name)
    except metadata.PackageNotFoundError:
        return None
    if requirement.specifier.contains(installed_version, prereleases=True):
        return None
    return SkewReport(
        requiring_distribution=requiring,
        required_distribution=requirement.name,
        specifier=str(requirement.specifier),
        installed_version=installed_version,
    )
