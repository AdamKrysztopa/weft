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
"""

from __future__ import annotations

from weft_kernel.discovery import PackReport, PackStatus


def render_list(reports: tuple[PackReport, ...]) -> str:
    """One line per distribution: status, ambient flag, contribution count."""
    if not reports:
        return "no packs discovered."
    lines = [_summary_line(report) for report in _sorted(reports)]
    return "\n".join(lines)


def render_doctor(reports: tuple[PackReport, ...]) -> str:
    """A fuller block per distribution: status, reason (if any), disclosure."""
    if not reports:
        return "no packs discovered."
    blocks = [_doctor_block(report) for report in _sorted(reports)]
    return "\n\n".join(blocks)


def _sorted(reports: tuple[PackReport, ...]) -> list[PackReport]:
    return sorted(reports, key=lambda report: report.distribution)


def _summary_line(report: PackReport) -> str:
    ambient = ", ambient" if report.ambient else ""
    return (
        f"{report.distribution}: {report.status.value}{ambient} ({report.contributed} contributed)"
    )


def _doctor_block(report: PackReport) -> str:
    lines = [_summary_line(report)]
    if report.status is PackStatus.REFUSED:
        lines.append(f"  never imported — {report.reason}")
    elif report.reason is not None:
        lines.append(f"  reason: {report.reason}")
    lines.append(f"  disclosure: {_disclosure_line(report)}")
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
