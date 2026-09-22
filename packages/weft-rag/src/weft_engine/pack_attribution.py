"""Where a plugin name that did not resolve is attributed to the pack that would have
supplied it — the one place both resolution seams compose that answer, so they cannot drift.

**Carried repair R11.3.** Two callers need the same thing once a plugin name fails to
resolve: `weft_engine.registry_bootstrap.require_plugin` (the `[services]` path) and
`weft_cli.compile._contract_for` (a pipeline document's own `use:` field). Before this
module existed, only the first attached a failed pack's own reason — the second printed
every installed plugin name and nothing about *why* the one asked for was missing, even
when `weft plugins doctor` already held the answer. Composing the message twice from the
same `PackReport` tuple is how `docs/02-extension-model.md` §2's exit-3-versus-policy /
exit-4-versus-resolution split stops being one promise, so this is the one place either
seam is allowed to build it.

**Why a new leaf module rather than folding this into `weft_engine.registry_bootstrap`.**
`weft_cli.compile` imports only from `weft_kernel` today, and `weft_engine.registry_bootstrap`
is heavy — it pulls in `weft_engine.llm_roles`, `weft_engine.permission_policy`,
`weft_engine.service_roles`, `weft_engine.services`, `weft_llm.client` and `weft_llm.contract` at
its own module scope, none of which a pipeline document's own bridge has ever needed. A
leaf module both `weft_cli.compile` and `weft_engine.registry_bootstrap` can import, with no
import running the other way, is what keeps the attribution in one place without adding a
cycle. It may import `weft_command.render` for `ExitCode` and `weft_kernel.discovery`, and
nothing from `weft_cli` at all — which is a stronger statement than the one this paragraph
made before task 24.1 moved this module here, and is now true of every module in this package.
"""

from __future__ import annotations

import importlib.metadata
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass

from weft_command.render import ExitCode
from weft_kernel.discovery import PackFailureKind, PackReport, PackStatus
from weft_kernel.seam import Unavailable

#: The statuses that mean a distribution is installed and permitted, and still did not put
#: everything it publishes in the registry. `attribute_to_packs` names these when a plugin
#: name does not resolve, because one of them is the likeliest reason it did not.
_CONTRIBUTED_INCOMPLETELY = (
    PackStatus.FAILED,
    PackStatus.PARTIAL,
    PackStatus.ALLOWED_NOT_INSTALLED,
)


@dataclass(frozen=True, slots=True)
class PluginRefusal:
    """`require_plugin`'s answer once `name` fails to resolve for `contract`.

    Repair, 2026-08-20 (finding 2, `docs/internal/build-ledger.md` 3.2/3.3/3.7's dated paragraph):
    this class replaces the bare `tuple[ExitCode, str]` `require_plugin` used to return, which had
    no field left to carry `weft_kernel.registry.UnknownPluginError.valid_options` through — the
    caller had already thrown it away into a string before `weft_cli.commands` ever saw it (a second
    repair, open item O4, later stopped that string from quoting `UnknownPluginError`'s own text
    verbatim at all — see `_unresolved`'s own docstring). `valid_options` is populated **only** for
    the two branches inside `_unresolved` that are genuinely a name-resolution failure (the `silent`
    and `nothing amiss` cases, both `ExitCode.RESOLUTION_FAILED`) — carried from the caught
    `UnknownPluginError` itself, every name actually registered for `contract` at the moment of the
    lookup. It stays `None` for the `refused` branch (`ExitCode.POLICY_REFUSED`): a refused pack is
    never imported, so nothing here can honestly claim to know what it would have registered —
    inventing a list there would be worse than omitting one, and it is the identical distinction
    `docs/internal/build-ledger.md` 3.3's own paragraph already draws for why
    `weft_cli.commands.CommandRefusalError`'s no-TTY refusal does not carry `valid_options` either:
    a policy decision is not a name failing to resolve.
    """

    exit_code: ExitCode
    message: str
    valid_options: tuple[str, ...] | None = None


def attribute_to_packs(
    reports: Sequence[PackReport],
    *,
    name: str,
    subject: str,
    not_found: str,
    registered: str,
    valid_options: tuple[str, ...],
) -> PluginRefusal:
    """`subject`, `not_found` and `registered` composed with whatever `reports` can say
    about why `name` did not resolve — `weft_engine.registry_bootstrap._unresolved`'s own
    body (repair, 2026-08-20, open item O4), generalised so a pipeline document's own
    `use:` field can call it too, rather than reimplementing the same branches a second time.

    `subject` is the caller's own "what was asked for" fragment (`[services] store names
    'pgvector'`, `stage 'store' names plugin 'pgvector'`) — never a claim about *why* it
    failed, because that claim is this function's to make once `reports` has been read.
    `not_found` is the caller's own "and nothing registered it" tail, used only where
    `reports` genuinely gives no better cause — carrying its own leading punctuation
    (`", which ..."`, `", and ..."`) since it is concatenated directly onto `subject` with
    no separator of this function's own choosing. `registered` is the caller's own "what is
    registered" sentence, and may be empty. All three are composed as-is, never re-derived
    here, so the two callers keep whatever vocabulary the site where the name was typed
    already speaks.

    Five branches, in order:

    - **A `REFUSED` pack is present** — `ExitCode.POLICY_REFUSED`, naming every refused
      distribution and `[packs] allow`. `valid_options` on the returned `PluginRefusal`
      stays `None` regardless of the `valid_options` argument: a refused pack is never
      imported, so nothing here can honestly claim what it would have registered — see
      `PluginRefusal`'s own docstring for the identical reasoning stated at the field.
    - **Some `silent` report has an `install_hint`** — `ExitCode.RESOLUTION_FAILED`, leading
      with the missing extra rather than any settings failure among the same reports:
      **carried repair R34.2**, found running `weft index` where `store` and `blob` both
      failed on their own settings while `qdrant` sat silent on a missing extra — the
      settings branch below would have won and buried the one line an operator can act on.
    - **A `FAILED` pack with `failure_kind is PackFailureKind.SETTINGS` is present** —
      `ExitCode.RESOLUTION_FAILED`, leading with *that* rather than `not_found`: the pack
      is installed and imported cleanly, `register()` never ran, and repeating "no
      installed distribution registered" would bury the one sentence — the pack's own
      reason, carried whole in `_diagnostic_detail` — an operator can act on. Carried
      repair for the defect `install_hint` and this branch both close: neither the
      headline nor the diagnostic detail offers `pip install` for a pack that already
      imported.
    - **Some other `FAILED`/`PARTIAL`/`ALLOWED_NOT_INSTALLED` pack is present** —
      `ExitCode.RESOLUTION_FAILED`, naming every such distribution, its own reason
      (`_diagnostic_detail`, which also carries the install line for an `IMPORT` failure —
      see `install_hint`), and `valid_options` carried through unchanged.
    - **Nothing amiss** — `ExitCode.RESOLUTION_FAILED`, `subject`, `not_found` and
      `registered` alone, `valid_options` carried through unchanged. The ordinary typo:
      every pack that could explain the miss is `ACTIVE`, so there is nothing left to
      attribute it to.
    """
    refused = tuple(report for report in reports if report.status is PackStatus.REFUSED)
    silent = tuple(report for report in reports if report.status in _CONTRIBUTED_INCOMPLETELY)
    settings_failures = tuple(
        report for report in silent if report.failure_kind is PackFailureKind.SETTINGS
    )
    if refused:
        listed = ", ".join(sorted(report.distribution for report in refused))
        return PluginRefusal(
            exit_code=ExitCode.POLICY_REFUSED,
            message=_compose(
                f"{subject}{not_found}",
                f"These distributions are refused by [packs] allow in weft.toml "
                f"and were never imported, so what they would have registered is unknown: "
                f"{listed}. Add the one that provides '{name}' to [packs] allow.",
                # `registered` names whatever is *currently* active despite the refusal — true
                # and worth stating — but not `PluginRefusal.valid_options` itself: a refused
                # pack is never imported, so this branch cannot honestly claim to know what it
                # would have contributed — see that field's own docstring.
                registered,
            ),
        )
    installable = tuple(
        (report, hint)
        for report in sorted(silent, key=_label_of)
        if (hint := install_hint(report)) is not None
    )
    named = tuple((report, hint) for report, hint in installable if report.pack == name)
    installable = named or installable
    if installable:
        listed = "; ".join(f"{_label_of(report)}: {hint}" for report, hint in installable)
        return PluginRefusal(
            exit_code=ExitCode.RESOLUTION_FAILED,
            message=_compose(
                f"{subject}. A pack it may need is not installed — {listed} — which is why "
                f"'{name}' may not resolve:",
                _diagnostic_detail(silent),
                registered,
            ),
            valid_options=valid_options,
        )
    if settings_failures:
        listed = "; ".join(_label_of(report) for report in sorted(settings_failures, key=_label_of))
        return PluginRefusal(
            exit_code=ExitCode.RESOLUTION_FAILED,
            message=_compose(
                f"{subject}. No installed distribution is missing — {listed} imported "
                f"cleanly and then failed on its own settings, which is why '{name}' does "
                f"not resolve:",
                _diagnostic_detail(silent),
                registered,
            ),
            valid_options=valid_options,
        )
    if silent:
        listed = "; ".join(
            f"{_label_of(report)} ({report.status.value})"
            for report in sorted(silent, key=_label_of)
        )
        return PluginRefusal(
            exit_code=ExitCode.RESOLUTION_FAILED,
            message=_compose(
                f"{subject}{not_found}",
                f"These packs contributed nothing, or only part of what they publish, "
                f"and one of them may be the one that provides it: {listed}.",
                registered,
                _diagnostic_detail(silent),
            ),
            valid_options=valid_options,
        )
    return PluginRefusal(
        exit_code=ExitCode.RESOLUTION_FAILED,
        message=_compose(f"{subject}{not_found}", registered),
        valid_options=valid_options,
    )


def unavailable_surface(reports: Sequence[PackReport], name: str) -> Unavailable | None:
    """The first `Unavailable` any report in `reports` declared for surface `name`, else
    `None` — carried repair **R9.5** (`docs/internal/lessons.md` `L9.86`).

    An `unavailable` surface is a pack-level fact stated at discovery, exactly like a
    `failed`/`partial` pack — but where those are keyed on the whole pack, this is keyed
    on one surface a pack otherwise able to register may still not be able to provide
    (`weft_kernel.discovery.PackReport.unavailable`). A caller scopes the refusal to the
    surface actually named, never the whole pack: only a document naming *this* surface
    is refused for it, so `unavailable_surface` answers the one question either seam
    needs — "did discovery already say `name` cannot be provided, and why" — rather than
    the caller re-walking `reports` and `report.unavailable` itself, the day a second
    caller (`weft eval`) needs the identical lookup.
    """
    for report in reports:
        for item in report.unavailable:
            if item.surface == name:
                return item
    return None


def unavailable_message(unavailable: Unavailable, *, name: str, stage: str) -> str:
    """The refusal sentence for a `use:` naming a surface discovery already reported
    unavailable — composed here, beside `attribute_to_packs`, so a document-path refusal
    and `weft plugins doctor`'s own printing of the identical `Unavailable` cannot drift
    into two different sentences for one fact.

    `unavailable.reason` is carried **verbatim and whole**, never spliced from `str(exc)`
    and never abridged: it is the pack's own words, and it is where the remedy lives — a
    run that only repeats the vendor library's own failure, with no reason and no remedy
    attached, is exactly the defect `L9.86` recorded.
    """
    return (
        f"stage '{stage}' names plugin '{name}', which discovery already reported "
        f"unavailable for {unavailable.distribution}: {unavailable.reason}"
    )


def install_hint(report: PackReport) -> str | None:
    """`pip install <report.distribution>[<report.pack>]`, when the distribution's own
    metadata says that extra genuinely exists — `None` otherwise.

    Read from `importlib.metadata`, never from a table in this tree — `docs/internal/lessons.md`
    `L7.6`: a claim about a distribution is asked of the distribution, not assumed from a
    name written down somewhere else. `None` for four distinct reasons, all of them a
    correct absence rather than a defect:

    - `report.failure_kind` is anything other than `PackFailureKind.IMPORT` — a pack whose
      settings failed validation, or whose `DISCLOSURE`/`SERVICE_ROLES` was malformed, or
      whose `register()`/`commit()` itself raised, is a pack that *did* import; installing
      the extra it already has changes nothing about any of those failures. Checked before
      the three reasons below, which all presuppose the library genuinely might be missing.
    - `report.pack` is `None` — the `ALLOWED_NOT_INSTALLED` case, where `[packs] allow`
      named a distribution nothing installed even claims; there is no entry point, so
      there is nothing to name an extra after.
    - `importlib.metadata.distribution(report.distribution)` raises `PackageNotFoundError`
      — nothing installed answers to that distribution name at all, the same case one
      layer up, reached defensively for a caller that hands this a `report.distribution`
      this environment never installed.
    - `report.pack` is not among that distribution's own `Provides-Extra` — a pack that
      ships unconditionally in the wheel (`chunk`, `store`, ...) has no extra to install,
      and inventing `pip install weft-rag[chunk]` would be advice with nothing behind it.

    `tests/architecture/test_distributions_declare_their_imports.py::
    test_every_capability_extra_is_the_name_of_a_pack_in_the_same_distribution` is the
    standing guard the other direction — that a pack which *should* have an extra is
    declared under its own name — so this function never has to guess at a mismatch.
    """
    if report.failure_kind is not PackFailureKind.IMPORT:
        return None
    if report.pack is None:
        return None
    try:
        distribution = importlib.metadata.distribution(report.distribution)
    except importlib.metadata.PackageNotFoundError:
        return None
    extras = distribution.metadata.get_all("Provides-Extra") or ()
    if report.pack not in extras:
        return None
    return f"pip install {report.distribution}[{report.pack}]"


def _label_of(report: PackReport) -> str:
    """How one incompletely-contributing pack is named to an operator — **carried repair
    R11.3, second half, found by running the binary.**

    Keyed on `pack` rather than `distribution`, with the distribution beside it. Both
    sentences below were written while every pack shipped in a distribution of its own, so
    the two strings were the same string and the choice did not matter. **G19 made it
    matter**: fourteen first-party packs now ship inside `weft-rag`, and the first real run
    of this repair printed

        `weft-rag (failed); weft-rag (failed); weft-rag (partial); weft-rag (failed); ...`

    — seven rows an operator cannot tell apart, one of which was the answer. That is
    `PackReport`'s own docstring predicting this in as many words: the two facts "stopped
    being the same the moment one distribution shipped fourteen packs, and a report that
    carried only the second could no longer tell fourteen rows apart."

    `pack` is `None` on exactly one status — `ALLOWED_NOT_INSTALLED`, where `[packs] allow`
    named a distribution nothing installed claims, so there is no entry point and therefore
    no pack. There the distribution is the only name there is, and it is the honest one.

    **`weft_cli.plugins_report` already had this right**, at its own `_summary_line` and its
    `sorted(..., key=lambda report: report.pack or report.distribution)`, which is why
    `weft plugins doctor` printed `qdrant (weft-rag): failed` correctly in the very run where
    this module printed seven indistinguishable `weft-rag`s. The two are deliberately not one
    function — that one renders a status table, this one labels a row inside a refusal — but
    they are one *convention*, and this paragraph is here so the next reader finds both. The
    `refused` branch above stays keyed on `distribution` and is not a third case: `[packs]
    allow` is a list of distributions, so the distribution is the thing the operator edits.
    """
    return report.pack or report.distribution


def _diagnostic_detail(silent: Sequence[PackReport]) -> str:
    """The raw reason each `silent` pack gave — a Pydantic validation dump, for `weft-store`'s
    own `FAILED` case — as its own block, indented under the pack it belongs to
    (`_label_of`), rather than spliced into the middle of the summary sentence above it.
    Empty for a `silent`
    sequence where nothing carries a `reason` (`ALLOWED_NOT_INSTALLED` never does).

    **Grows an install line, carried repair R11.3.** Beneath a report's own reason, when
    `install_hint` has one to offer for that same report, its one line is indented beside
    it — the one thing an operator reading this block can act on, rather than only being
    told what already failed.
    """
    blocks: list[str] = []
    for report in sorted(silent, key=_label_of):
        if not report.reason:
            continue
        block = f"{_label_of(report)}:\n{textwrap.indent(report.reason, '    ')}"
        hint = install_hint(report)
        if hint is not None:
            block += f"\n{textwrap.indent(hint, '    ')}"
        blocks.append(block)
    return "Diagnostic detail:\n" + "\n".join(blocks) if blocks else ""


def _compose(*sentences: str) -> str:
    """Join `attribute_to_packs`'s pieces into one message, in the order given — the join
    `weft_engine.registry_bootstrap`'s own 2026-08-20 repair was about.

    Every argument is written in its own voice, capitalised and ending in a full stop
    already, so a plain space between two single-line pieces reads as one paragraph. A
    multi-line piece (`_diagnostic_detail`'s block) gets a blank line on either side
    instead, so it reads as a distinct, clearly-delimited section rather than a
    continuation of the sentence next to it. An empty piece contributes nothing, not even
    a stray separator.
    """
    parts: list[str] = []
    previous_was_multiline = False
    for sentence in sentences:
        if not sentence:
            continue
        multiline = "\n" in sentence
        if parts:
            parts.append("\n\n" if multiline or previous_was_multiline else " ")
        parts.append(sentence)
        previous_was_multiline = multiline
    return "".join(parts)
