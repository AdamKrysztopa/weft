"""Rendering `weft plugins list` and `weft plugins doctor` from a tuple of `PackReport`.

`docs/03-cli.md`: "`weft plugins doctor` reports what was discovered, from
which distribution... and what failed to load and why... one status per
pack... plus each pack's disclosure." Everything printed here reads
straight off `weft_kernel.discovery.PackReport` — nothing is computed twice.

**A row is one pack, not one distribution.** `PackReport.pack` is the `weft.packs`
entry-point name and `PackReport.distribution` is what an index ships; a status line
prints `pack (distribution version)` because `weft-rag` ships twelve registering packs
and twelve rows reading `weft-rag` answer nobody's question. See `weft_kernel.discovery`'s
own module docstring for where the two identities part, and `docs/02-extension-model.md` §2.
Two fields that section also names are not printed, because nothing in the
kernel exposes them yet, and this module states what it has rather than
approximating what it does not: **per-plugin contract versions** (`PackReport`
carries a contribution *count*, not the `(contract, name)` pairs themselves —
`weft_kernel.registry.Registry.contracts()` and `.distributions_for()`, added
at task 0.12 for the generated contract reference, answer "which contracts,
published by which distributions", not "which plugin name, under which
contract, at which version"; that finer enumeration is still absent), and
**what `register()` cost** (`weft_kernel.discovery`'s own module docstring
describes timing and a `sys.modules` diff as the eventual measurement, but
`PackReport` carries neither field today). Both are real gaps, not oversights
this module papers over — the honest, doctor-shaped answer to "how much did
this pack cost" until the kernel measures it is `not measured`, not a number
this module makes up.

**Task 1.12** adds `render_doctor`'s `displaced` parameter — `docs/03-cli.md`:
"A displaced registration: the pack lost a `(contract, name)` collision to
an operator's pin, so it is installed, active, and one of its plugins is
unreachable." A `weft_kernel.registry.DisplacedRegistration` is grouped
under the *losing* distribution's own block, because that is the report an
operator staring at `weft-loser: active (1 contributed)` needs sitting right
next to it, not a separate section to cross-reference by name. The winner's
block prints nothing about it — a pin resolving in a pack's favour is not a
fact about *that* pack; it is the pin's own record, already visible on the
loser's line. `displaced=()`, the default, leaves every existing caller's
output unchanged.

**Repair for a reviewer finding — `render_doctor`'s `unconsulted_pins` parameter.**
`weft_kernel.discovery.discover`'s `strict_pins=False` (see its own docstring) lets
`weft plugins doctor` build a registry even when a `[plugins]` pin never arbitrated
anything, rather than dying before a single report exists — but a diagnostic command
that swallowed the very thing it exists to diagnose would trade one silent failure for
another. `weft_cli.cli.handle_plugins_doctor` reads the same
`weft_kernel.registry.Registry.unconsulted_pins()` `InertPluginPinError` would have
raised off and hands it here instead, printed as its own loud block rather than folded
into any one distribution's — the same reasoning `InertPluginPinError`'s own docstring
already gives for not folding it into a pack's report: this is not one pack's failure.
`unconsulted_pins=()`, the default, leaves every existing caller's output unchanged.

**`render_doctor`'s `tracing` parameter — task 5.1d.** `weft_cli.tracing_status.
describe_tracing()`'s own words: whether the process's `TracerProvider` is a real one, read
after discovery has run, so it reflects what actually happened — `weft-otel` installed and
configured, installed and set to `exporter: none`, or absent entirely. Printed as its own
trailing block, the same shape `unconsulted_pins` already takes, because it is a fact about
the process rather than about any one distribution's `PackReport`; see
`weft_kernel.discovery.PackReport`'s own docstring for why nothing on it could carry this.
`tracing=None`, the default, leaves every existing caller's output unchanged.

**`render_doctor`'s `skew` parameter — task 5.2e.** Every `weft_cli.skew.SkewReport`
`weft_cli.skew.detect_skew()` found: a distribution whose installed version does not
satisfy another installed distribution's own declared specifier — `docs/09-release.md`
§2.3 answer 1, "detected and reported by `weft plugins doctor`." Printed as its own
trailing block for the identical reason `unconsulted_pins`/`tracing` are: it is a fact
about the environment as a whole, not about any one distribution's own `PackReport`.
`skew=()`, the default, leaves every existing caller's output unchanged.

**Deprecation, also task 5.2e, needs no new parameter here.** `weft_kernel.discovery.
PackReport.deprecations` already travels with every report `render_doctor` walks, so it is
read the same way `ambient` already is — a flag beside a pack's own status, printed from
`_summary_line`/`_doctor_block` below, `docs/09-release.md` §3: "a flag on an existing
status... no new status."

**`render_doctor`'s `unreachable_contributions` parameter — task 5.3a (`S8`).** `02` §3 →
*Slots*: "`weft plugins doctor` flags a pack whose contributions land in *no* pipeline at
all." `weft_cli.commands.PluginsDoctorCommand` computes this against `weft_cli.
pipeline_catalogue.declared_slot_ids` — every `Contribution` in `Dependencies.contributions`
whose `slot` no pipeline in the catalogue declares — and passes it here grouped by
distribution, the same shape `displaced` already takes, since it is a fact about *that*
pack's own offer, not about the environment as a whole. `unreachable_contributions=()`, the
default, leaves every existing caller's output unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping

from weft_cli.skew import SkewReport
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.registry import DisplacedRegistration
from weft_kernel.resolution import Contribution


def render_list(reports: tuple[PackReport, ...]) -> str:
    """One line per pack: status, ambient flag, contribution count."""
    if not reports:
        return "no packs discovered."
    lines = [_summary_line(report) for report in _sorted(reports)]
    return "\n".join(lines)


def render_doctor(
    reports: tuple[PackReport, ...],
    displaced: tuple[DisplacedRegistration, ...] = (),
    unconsulted_pins: tuple[str, ...] = (),
    tracing: str | None = None,
    skew: tuple[SkewReport, ...] = (),
    unreachable_contributions: tuple[Contribution, ...] = (),
    versions: Mapping[str, str] | None = None,
) -> str:
    """A fuller block per distribution: status, reason (if any), disclosure, and what it lost.

    `displaced` — task 1.12, `docs/03-cli.md`'s own words — is every
    `weft_kernel.registry.DisplacedRegistration` the registry recorded; each
    one is grouped under the *losing* distribution's block. The default `()`
    reproduces exactly the output this function gave before that field
    existed, for every caller that has not started passing it.

    `unconsulted_pins` — see the module docstring's *repair for a reviewer
    finding* — is every `[plugins]` pin `weft_kernel.registry.Registry.
    unconsulted_pins()` reports, printed as its own trailing block rather
    than folded into any one distribution's, since it is not one
    distribution's fact. The default `()` again reproduces prior output
    unchanged.

    `skew` — task 5.2e, see the module docstring's own paragraph — is every
    `weft_cli.skew.SkewReport` `weft_cli.skew.detect_skew()` found, printed as its own
    trailing block after `unconsulted_pins` and before `tracing`, for the same "not one
    distribution's fact" reason. The default `()` reproduces prior output unchanged.

    `unreachable_contributions` — task 5.3a (`S8`), see the module docstring's own
    paragraph — is every `Contribution` naming a slot no pipeline in the catalogue
    declares, grouped under the *offering* distribution's own block, on `displaced`'s own
    footing. The default `()` reproduces prior output unchanged.

    **A pack name two installed distributions both claim** gets its own trailing block,
    computed here from `reports` rather than passed in — `_packs_claimed_by_more_than_one_
    distribution`. It takes no parameter because it is derivable from what this function was
    already given, and a second channel for a fact already in the input would be one more
    thing a caller could forget to pass. See `docs/02-extension-model.md` §2 → *Pack settings*
    for why this is reported and not refused.

    `versions` — task **6.4**, `docs/09-release.md` section 1 — is what
    `weft_cli.installed_versions.installed_versions` read for each distribution reported here,
    printed on the status line beside the name because that section calls for "one column, not
    a new command". `None`, the default, prints no column at all and leaves every existing
    caller's output unchanged; a name absent from a mapping that *was* supplied prints
    "(version not recorded)", which is the state distinguishable from the other two. Only
    `doctor` takes it: `weft plugins list` is a summary and section 1 gives the column to
    `doctor`.
    """
    if not reports:
        return "no packs discovered."
    by_loser = _group_by_loser(displaced)
    by_offerer = _group_by_distribution(unreachable_contributions)
    # A `DisplacedRegistration` and a `Contribution` are attributed to a *distribution*,
    # which is no longer one pack's fact: `weft-rag` ships fourteen packs, so looking each
    # one up per report would print the same line under all fourteen blocks. Popped rather
    # than read, so a distribution's items appear exactly once — under the first of its
    # packs in sorted order. Carrying `pack` down through `Registry.add` to
    # `DisplacedRegistration` is what would put each line under the pack that actually lost
    # it; that is a wider seam than this change opens, and until it is opened, printing once
    # under a named distribution beats printing fourteen times under fourteen.
    blocks = [
        _doctor_block(
            report,
            by_loser.pop(report.distribution, ()),
            by_offerer.pop(report.distribution, ()),
            versions,
        )
        for report in _sorted(reports)
    ]
    shared = _packs_claimed_by_more_than_one_distribution(reports)
    if shared:
        blocks.append(_shared_pack_name_block(shared))
    if unconsulted_pins:
        blocks.append(_unconsulted_pins_block(unconsulted_pins))
    if skew:
        blocks.append(_skew_block(skew))
    if tracing is not None:
        blocks.append(f"tracing: {tracing}")
    return "\n\n".join(blocks)


def _sorted(reports: tuple[PackReport, ...]) -> list[PackReport]:
    """Ordered by the identity that is printed: the pack, with `ALLOWED_NOT_INSTALLED`'s
    distribution standing in for the one row that has no pack at all."""
    return sorted(reports, key=lambda report: report.pack or report.distribution)


def _group_by_loser(
    displaced: tuple[DisplacedRegistration, ...],
) -> dict[str, tuple[DisplacedRegistration, ...]]:
    """Every `DisplacedRegistration`, keyed by the distribution that lost it."""
    by_loser: dict[str, list[DisplacedRegistration]] = {}
    for item in displaced:
        by_loser.setdefault(item.distribution, []).append(item)
    return {
        distribution: tuple(sorted(items, key=lambda item: (item.contract.__name__, item.name)))
        for distribution, items in by_loser.items()
    }


def _group_by_distribution(
    contributions: tuple[Contribution, ...],
) -> dict[str, tuple[Contribution, ...]]:
    """Every `Contribution`, keyed by the distribution that offered it — task 5.3a (`S8`)."""
    by_distribution: dict[str, list[Contribution]] = {}
    for contribution in contributions:
        by_distribution.setdefault(contribution.distribution, []).append(contribution)
    return {
        distribution: tuple(sorted(items, key=lambda item: (item.slot, item.stage.id)))
        for distribution, items in by_distribution.items()
    }


def _summary_line(report: PackReport, version_label: str = "") -> str:
    """`pack (distribution): status ...` — the two identities, in that order.

    The pack leads because it is what the reader is looking for: which of the twelve
    installed packs this row is about. The distribution follows in parentheses because it
    is what they would `pip install`, uninstall or pin, and because several rows now share
    one. `ALLOWED_NOT_INSTALLED` is the single row with no pack — `[packs] allow` named a
    distribution nothing installed claims — and prints the distribution alone rather than
    inventing a pack name for it, which is byte-for-byte the line this function produced
    before packs had an identity of their own.

    `version_label` follows the parenthesis rather than sitting inside it, so the
    "(version not recorded)" state stays the string it has always been instead of becoming
    a parenthesis nested inside a parenthesis.
    """
    ambient = ", ambient" if report.ambient else ""
    deprecated = ", deprecated" if report.deprecations else ""
    identity = (
        report.distribution if report.pack is None else f"{report.pack} ({report.distribution})"
    )
    return (
        f"{identity}{version_label}: {report.status.value}{ambient}{deprecated} "
        f"({report.contributed} contributed)"
    )


def _version_label(distribution: str, versions: Mapping[str, str] | None) -> str:
    """The `09` section 1 column, or nothing at all when no caller asked for it.

    Three states, deliberately distinguishable. `versions is None` is "nobody asked" and
    reproduces the output this renderer gave before the column existed — every caller that has
    not started passing it sees no change. A name present is its version. A name **absent from a
    mapping that was supplied** is the one that matters: the caller asked, and the environment
    had nothing recorded for that distribution, which is said out loud rather than left blank
    (`docs/lessons.md` L5.9).
    """
    if versions is None:
        return ""
    if distribution in versions:
        return f" {versions[distribution]}"
    return " (version not recorded)"


def _doctor_block(
    report: PackReport,
    displaced: tuple[DisplacedRegistration, ...],
    unreachable: tuple[Contribution, ...] = (),
    versions: Mapping[str, str] | None = None,
) -> str:
    lines = [_summary_line(report, _version_label(report.distribution, versions))]
    if report.status is PackStatus.REFUSED:
        lines.append(f"  never imported — {report.reason}")
    elif report.reason is not None:
        lines.append(f"  reason: {report.reason}")
    lines.append(f"  disclosure: {_disclosure_line(report)}")
    for item in displaced:
        lines.append(
            f"  displaced: '{item.pin}' lost to '{item.winner}' — pinned by "
            f'[plugins] "{item.pin}" = "{item.winner}" in weft.toml'
        )
    # Task **6.29** — what the pack said it could not provide, and why, printed beside its
    # `partial` status. `01` → *Fitness functions* 5: declared unavailable **at discovery
    # time**, so an operator reads it here rather than meeting it when a run fails.
    for missing in report.unavailable:
        lines.append(f"  unavailable: '{missing.surface}' — {missing.reason}")
    for notice in report.deprecations:
        lines.append(
            f"  deprecated: '{notice.surface}' — {notice.reason} ({notice.removal.describe()})"
        )
    for contribution in unreachable:
        lines.append(
            f"  unreachable: slot '{contribution.slot}' (stage '{contribution.stage.id}') "
            f"lands in no pipeline this catalogue holds"
        )
    return "\n".join(lines)


def _packs_claimed_by_more_than_one_distribution(
    reports: tuple[PackReport, ...],
) -> dict[str, tuple[str, ...]]:
    """Every pack name two or more installed distributions both claim, and who claims it.

    `docs/02-extension-model.md` §2 → *Pack settings*: nothing in Python packaging stops two
    distributions from declaring a `weft.packs` entry point under the same name, and weft does
    not refuse it — a stranger's pack is not ours to rename, and failing both would punish an
    operator for something only an uninstall can fix. What it must not do is pass in silence:
    one `[packs.<pack>]` block would then configure both, and two rows would print the same
    first column. So it is reported here, as an environment fact in its own block beside
    version skew and inert pins, rather than folded into either pack's own — neither of them
    did anything wrong, which is exactly why it belongs to neither.
    """
    claimants: dict[str, set[str]] = {}
    for report in reports:
        if report.pack is not None:
            claimants.setdefault(report.pack, set()).add(report.distribution)
    return {
        pack: tuple(sorted(distributions))
        for pack, distributions in sorted(claimants.items())
        if len(distributions) > 1
    }


def _shared_pack_name_block(shared: Mapping[str, tuple[str, ...]]) -> str:
    lines = ["pack names claimed by more than one installed distribution:"]
    for pack, distributions in shared.items():
        named = ", ".join(f"'{distribution}'" for distribution in distributions)
        lines.append(
            f"  '{pack}' — claimed by {named}. One [packs.{pack}] block in weft.toml "
            f"configures both; uninstall one, or ask its author to rename its entry point."
        )
    return "\n".join(lines)


def _unconsulted_pins_block(unconsulted_pins: tuple[str, ...]) -> str:
    lines = ["[plugins] pins that never arbitrated anything:"]
    for pin in sorted(unconsulted_pins):
        lines.append(f"  '{pin}' — weft never saw two distributions contend for what it names.")
    return "\n".join(lines)


def _skew_block(skew: tuple[SkewReport, ...]) -> str:
    lines = ["version skew — installed does not satisfy a declared specifier:"]
    ordered = sorted(
        skew, key=lambda item: (item.requiring_distribution, item.required_distribution)
    )
    for item in ordered:
        lines.append(
            f"  '{item.requiring_distribution}' requires '{item.required_distribution}' "
            f"{item.specifier}, but {item.installed_version} is installed."
        )
    return "\n".join(lines)


def _disclosure_line(report: PackReport) -> str:
    disclosure = report.disclosure
    if disclosure is None:
        return "not disclosed"
    parts = [
        f"network={list(disclosure.network)}",
        f"filesystem={list(disclosure.filesystem)}",
        f"subprocess={list(disclosure.subprocess)}",
    ]
    if disclosure.note:
        parts.append(f"note={disclosure.note!r}")
    return ", ".join(parts)
