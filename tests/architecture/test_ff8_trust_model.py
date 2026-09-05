"""Fitness function 8 — trust integrity, clauses (a) and (b).

**Clause (a) — refusal precedes execution.** With an allow-list active that
excludes it, discovery must not import the canary at all —
`docs/01-high-level-plan.md` → *Fitness functions*, clause 8(a). *Active from
Phase 0*, and this is the test that turns it on: `docs/06-phase-0-build.md`
step 5 names it explicitly.

**Clause (b) — no pack code executes for a command that does not need the
registry.** *Active from Phase 0* per the same section's corrected note:
"Phase 0 ships `weft --version`, which is precisely the command this clause
is about; see `docs/06-phase-0-build.md` step 9." This is the test that turns
it on, exercising `weft_cli.cli.main()` itself rather than
`weft_kernel.discovery.discover` directly — 8(b) is a property of the CLI's
dispatch (`dispatch` only calls `build_dependencies`, which calls
`discover`, when `CliCommand.needs_registry` is `True`), not of discovery in
isolation, which clause (a)'s test already covers.

The canary (`testing/weft-canary/`) writes a marker file at **module
import**, before any `register()` could run — so the assertion is always
"marker absent", which needs no timing and would survive a subprocess
boundary exactly as well as it survives this in-process call. Both tests run
against the **real**, installed entry-point metadata (no fake entry points),
because both clauses are properties of the actual discovery and dispatch
paths, not of a double standing in for either — the unit tests in
`tests/unit/weft_kernel/test_discovery.py` and `tests/unit/weft_cli/test_cli.py`
cover the rest of each module's behaviour with doubles; these two exist to
prove the real canary is never imported.

**The marker check alone is not categorical.** A module already present in
`sys.modules` is not re-executed by a second `import`, so if anything else in
this pytest session imports `weft_canary` before a test below runs, the
marker check would pass even against a buggy `discover()`, or a buggy
`dispatch`, that loads it regardless — either clause would be silently
unable to fail. `test_a_pack_refused_by_the_allow_list_is_never_imported`
therefore asserts `weft_canary not in sys.modules` twice: once as an Arrange
precondition (so a prior import fails loudly here rather than letting the
test pass for the wrong reason), and once again afterward, as a second,
independent witness alongside the marker.

**`test_version_command_executes_no_pack_code` needs a stronger witness
still, and a subprocess.** Clause 8(b) is not "the canary stays unimported" —
it is "`weft --version` executes no pack code at all", and `weft-canary` is
not one of `weft_cli.cli`'s hardcoded imports, so the canary alone cannot see
a bug where `cli.py` imports a *named* pack (`weft_extract`, `weft_chunk`,
`weft_embed`, `weft_store`) at module scope instead of inside the one handler
that needs it. This test therefore checks all five pack modules by name. And
it cannot check them in-process: `tests/unit/weft_cli/test_ask.py` and
`test_ingest.py` import `weft_cli.ask`/`weft_cli.ingest` directly elsewhere in
this same pytest session — collected, and so imported, before any test
function runs — which pulls `weft_extract`, `weft_chunk`, `weft_embed` and
`weft_store` into `sys.modules` regardless of what `weft --version` itself
does. An in-process `sys.modules` assertion here would therefore pass even
against a `cli.py` that imports every pack module at the top of the file — a
fresh interpreter, which starts with none of them loaded, is the only way to
observe what `cli.main()` alone imports.

**Clause (c) — the run record names the active distribution set, equal to
what `plugins doctor` reports as `active`.** *Active from Phase 4*, task
**4.4**: `weft_eval.run_record.active_distribution_set` is the run record's
own derivation, and `weft_cli.plugins_report.render_doctor` is the function
`weft plugins doctor` itself calls to print its "active" lines — both read
`weft_kernel.discovery.PackReport.status`, and nothing else, off the
identical report tuple. `test_run_record_active_distributions_equal_what_plugins_doctor_reports`
proves the two still agree, against the real, installed environment, by
comparing `active_distribution_set`'s output to text parsed out of
`render_doctor`'s own rendered block — never against a second copy of the
same filter, which would prove the check could never fail.
`test_the_equality_check_is_not_vacuous` then manufactures the exact drift
the clause exists to catch: a plausible-looking alternative filter
(`contributed > 0` instead of `status is PackStatus.ACTIVE`) that disagrees
with what `render_doctor` reports the moment a `PARTIAL` pack is in the mix,
demonstrating the comparison actually fails when the two definitions of
"active" diverge, rather than passing regardless of what either side
computes.
"""

import os
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Final

from weft_cli.installed_versions import installed_versions
from weft_cli.plugins_report import render_doctor
from weft_eval.run_record import active_distribution_set
from weft_kernel.discovery import ENTRY_POINT_GROUP, PackReport, PackStatus, discover
from weft_kernel.registry import Registry

CANARY_DISTRIBUTION = "weft-canary"
CANARY_MODULE = "weft_canary"
MARKER_ENV_VAR = "WEFT_CANARY_MARKER"

#: Every top-level pack module `weft --version` must import none of — the categorical form of
#: fitness function 8(b), not just "the canary stays unimported". `weft_cli.ingest` and
#: `weft_cli.ask` each import the first four at their own module scope; the fifth is the canary
#: clause (a)'s own subject.
_PACK_MODULES: tuple[str, ...] = (
    "weft_extract",
    "weft_chunk",
    "weft_embed",
    "weft_store",
    CANARY_MODULE,
)

#: The subprocess script `test_version_command_executes_no_pack_code` runs: parse `weft
#: --version`'s own exit code, then report which of `_PACK_MODULES` ended up in `sys.modules` —
#: printed rather than asserted in-process, since the assertion has to happen in the fresh
#: interpreter that ran `cli.main()`, not in the parent pytest process reading its result.
_VERSION_PROBE_SCRIPT = """
import sys

sys.argv = ["weft", "--version"]
from weft_cli import cli

try:
    cli.main()
except SystemExit as exc:
    exit_code = exc.code
else:
    exit_code = None

loaded = sorted(name for name in {pack_modules!r} if name in sys.modules)
print(exit_code)
print(",".join(loaded))
"""


def _assert_canary_installed() -> None:
    """The canary is installed with its entry point — the floor both clauses rest on.

    Split from the `sys.modules` half at ledger task **6.33**. *Installed* is a fact about the
    environment and both tests need it; *unimported* is a fact about this pytest process and only
    an in-process assertion could care — and neither test makes one any more.
    """
    installed = {
        entry_point.dist.name
        for entry_point in metadata.entry_points(group=ENTRY_POINT_GROUP)
        if entry_point.dist is not None
    }
    assert CANARY_DISTRIBUTION in installed, (
        f"'{CANARY_DISTRIBUTION}' must be installed with a '{ENTRY_POINT_GROUP}' entry point "
        f"for this test to mean anything — run `uv sync` first."
    )


#: Run in a fresh interpreter, for the reason ledger task **6.33** found the hard way. This
#: assertion used to be made in-process, guarded by "the canary is not imported yet" — and that
#: guard is a **statement about the whole pytest session**, not about the code under test. Four
#: `tests/docs` modules and five `tests/unit/weft_cli/test_contract_reference.py` tests call
#: `discover_for_reference()`, which discovers open and therefore imports the canary; the last of
#: those cannot avoid it, because testing that function *is* what it is for. So the guard was
#: satisfied only by `tests/architecture` sorting before `tests/docs`, and `pytest tests/docs
#: tests/architecture` failed while `pytest tests` passed. A subprocess starts with an empty
#: `sys.modules` whatever ran before it, which is what the canary's own docstring says it was
#: built for: "the same canary works for an in-process discovery test and for a CLI invocation."
_REFUSAL_PROBE = """
import sys
from weft_kernel.discovery import discover
from weft_kernel.registry import Registry

reports = discover(Registry(), allow=[])
status = {report.distribution: report.status.value for report in reports}
print("imported", "weft_canary" in sys.modules)
print("status", status.get("weft-canary"))
"""


def test_a_pack_refused_by_the_allow_list_is_never_imported(tmp_path: Path) -> None:
    # Arrange — a fresh interpreter, so what this observes is what `discover` did and not what
    # some earlier test in the session happened to import.
    marker = tmp_path / "canary-marker"
    _assert_canary_installed()
    env = {**os.environ, MARKER_ENV_VAR: str(marker)}

    # Act
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, no user input
        [sys.executable, "-c", _REFUSAL_PROBE],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    # Assert
    assert result.returncode == 0, f"the probe failed:\n{result.stderr}"
    reported = dict(line.split(" ", 1) for line in result.stdout.strip().splitlines())
    assert not marker.exists(), (
        "the canary writes its marker at import; an allow-list that excludes it must stop "
        "discovery before the import happens, not merely before register() is called"
    )
    assert reported["imported"] == "False", (
        "the canary must never be imported at all when it is excluded from [packs] allow — "
        "this is the categorical form of the marker assertion above, independent of it"
    )
    assert reported["status"] == PackStatus.REFUSED.value


def test_version_command_executes_no_pack_code(tmp_path: Path) -> None:
    # Arrange — no [packs] allow at all: discovery, if it ran, would be wide open and would
    # happily import and register the canary. `weft --version` must still never call it. Run
    # in a fresh interpreter — see the module docstring on why an in-process assertion here
    # would be meaningless in this pytest session.
    marker = tmp_path / "canary-marker"
    env = {**os.environ, MARKER_ENV_VAR: str(marker)}
    # Only *installed* matters here: this runs in a fresh interpreter, so whether the canary is
    # in **this** process's `sys.modules` says nothing about what the subprocess loads
    # (ledger task 6.33).
    _assert_canary_installed()

    # Act — cwd=tmp_path: no weft.toml there for weft_cli.registry_bootstrap to read.
    result = subprocess.run(  # noqa: S603 — sys.executable, fixed script, no shell, no user input
        [sys.executable, "-c", _VERSION_PROBE_SCRIPT.format(pack_modules=_PACK_MODULES)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    # Assert
    assert result.returncode == 0, (
        f"the probe script itself must exit cleanly; stderr:\n{result.stderr}"
    )
    # `weft --version` itself prints "weft <version>" to stdout ahead of the probe's own two
    # lines — the probe's output is always the last two lines, regardless of what the command
    # under test printed.
    exit_code_line, loaded_line = result.stdout.splitlines()[-2:]
    assert exit_code_line == "0", f"weft --version must exit 0; got {exit_code_line}"
    assert not marker.exists(), (
        "weft --version must execute no pack code at all — weft_kernel.discovery.discover() "
        "is never called for a command that does not need the registry (fitness function "
        "8(b)), so even a wide-open [packs] posture must leave the canary unimported."
    )
    assert loaded_line == "", (
        f"weft --version must import none of {_PACK_MODULES} — this is fitness function 8(b) "
        f"in its categorical form, not just 'the canary stays unimported'. Found imported: "
        f"{loaded_line}"
    )


# --- clause (c): the run record's active set equals what `plugins doctor` reports -----------

#: `weft_cli.plugins_report._summary_line`'s own shape — matched, never retyped: a doctor
#: block's first line is `f"{distribution}: {status}{ambient} ({contributed} contributed)"`.
#: Only the `active` status line is captured; every other status is deliberately not matched,
#: since clause (c) is about the active set alone.
#: The distribution name is the first run of non-space characters; everything between it and
#: the colon is the version column task **6.4** added (`09` §1) — either ` 2.0.0` or
#: ` (version not recorded)`, and empty when no caller asked for the column at all. Tolerating
#: it is not cosmetic: this clause claims to parse "what `weft plugins doctor` itself would
#: print", and after 6.4 the shipped command prints the column. A pattern anchored on the
#: pre-6.4 spelling kept passing because the test called `render_doctor` with its defaults —
#: the check went on agreeing with a rendering the binary no longer produces.
_ACTIVE_SUMMARY_LINE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<distribution>\S+)[^:]*: active(?:, ambient)?(?:, deprecated)? \(\d+ contributed\)$"
)


def _active_names_from_doctor_report(text: str) -> tuple[str, ...]:
    """Every distribution `render_doctor`'s own text reports as `active`, parsed from its
    output rather than recomputed — see the module docstring's clause-(c) paragraph.
    """
    names = (
        match.group("distribution")
        for line in text.splitlines()
        if (match := _ACTIVE_SUMMARY_LINE.match(line)) is not None
    )
    return tuple(sorted(names))


def test_run_record_active_distributions_equal_what_plugins_doctor_reports() -> None:
    # Arrange — real, wide-open discovery against the actual installed environment, the same
    # call clause (a)'s own test makes with `allow=[]` reversed to "everything permitted".
    reports = discover(Registry())

    # Act — two independent readings of the identical `PackReport` tuple: the run record's own
    # derivation, and the text `weft plugins doctor` itself would print.
    record_active = active_distribution_set(reports)
    doctor_active = _active_names_from_doctor_report(
        # Rendered the way `weft_cli.commands.PluginsDoctorCommand` renders it — with the
        # version column task 6.4 added. Calling `render_doctor` with its defaults would
        # compare this clause against output the shipped command no longer produces.
        render_doctor(
            reports,
            versions=installed_versions(report.distribution for report in reports),
        )
    )

    # Assert
    assert record_active, (
        "nothing registered ACTIVE in this environment — the comparison below would be "
        "vacuously true; run `uv sync` first."
    )
    assert record_active == doctor_active


def test_the_check_can_actually_fail() -> None:
    """Fitness function 16 clause (b) — named to the convention at ledger task **6.15**.

    This test predates FF16 and did its job under the name `test_the_equality_check_is_not_
    vacuous`; only the name changes here, so the clause's AST scan can recognise it. The body
    is the original and the argument it makes is unchanged.
    """
    # Arrange — one genuinely active pack, one that registered only part of what it offers.
    # `PARTIAL` is exactly the status a filter built on "contributed > 0" would wrongly admit,
    # since a partially-registered pack still contributes something.
    reports = (
        PackReport(distribution="weft-real", status=PackStatus.ACTIVE, contributed=3),
        PackReport(distribution="weft-half", status=PackStatus.PARTIAL, contributed=1),
    )
    doctor_active = _active_names_from_doctor_report(render_doctor(reports))

    # Act — the correct derivation, and a plausible-looking wrong one.
    correct = active_distribution_set(reports)
    buggy = tuple(sorted(report.distribution for report in reports if report.contributed > 0))

    # Assert — the correct derivation agrees with what doctor reports; the wrong one, which a
    # regression could plausibly introduce, does not. This is the check clause (c) exists to
    # be, not merely to state.
    assert correct == doctor_active == ("weft-real",)
    assert buggy != doctor_active
