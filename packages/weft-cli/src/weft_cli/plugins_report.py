"""Rendering `weft plugins list` and `weft plugins doctor` from a tuple of `PackReport`.

`docs/03-cli.md`: "`weft plugins doctor` reports what was discovered, from
which distribution... and what failed to load and why... one status per
distribution... plus each pack's disclosure." Everything printed here reads
straight off `weft_kernel.discovery.PackReport` — nothing is computed twice.
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
    """One line per distribution: status, ambient flag, contribution count."""
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
    """
    if not reports:
        return "no packs discovered."
    by_loser = _group_by_loser(displaced)
    by_offerer = _group_by_distribution(unreachable_contributions)
    blocks = [
        _doctor_block(
            report, by_loser.get(report.distribution, ()), by_offerer.get(report.distribution, ())
        )
        for report in _sorted(reports)
    ]
    if unconsulted_pins:
        blocks.append(_unconsulted_pins_block(unconsulted_pins))
    if skew:
        blocks.append(_skew_block(skew))
    if tracing is not None:
        blocks.append(f"tracing: {tracing}")
    return "\n\n".join(blocks)


def _sorted(reports: tuple[PackReport, ...]) -> list[PackReport]:
    return sorted(reports, key=lambda report: report.distribution)


def _group_by_loser(
    displaced: tuple[DisplacedRegistration, ...],
) -> Mapping[str, tuple[DisplacedRegistration, ...]]:
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
) -> Mapping[str, tuple[Contribution, ...]]:
    """Every `Contribution`, keyed by the distribution that offered it — task 5.3a (`S8`)."""
    by_distribution: dict[str, list[Contribution]] = {}
    for contribution in contributions:
        by_distribution.setdefault(contribution.distribution, []).append(contribution)
    return {
        distribution: tuple(sorted(items, key=lambda item: (item.slot, item.stage.id)))
        for distribution, items in by_distribution.items()
    }


def _summary_line(report: PackReport) -> str:
    ambient = ", ambient" if report.ambient else ""
    deprecated = ", deprecated" if report.deprecations else ""
    return (
        f"{report.distribution}: {report.status.value}{ambient}{deprecated} "
        f"({report.contributed} contributed)"
    )


def _doctor_block(
    report: PackReport,
    displaced: tuple[DisplacedRegistration, ...],
    unreachable: tuple[Contribution, ...] = (),
) -> str:
    lines = [_summary_line(report)]
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
    for notice in report.deprecations:
        lines.append(f"  deprecated: '{notice.surface}' — {notice.reason}")
    for contribution in unreachable:
        lines.append(
            f"  unreachable: slot '{contribution.slot}' (stage '{contribution.stage.id}') "
            f"lands in no pipeline this catalogue holds"
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
