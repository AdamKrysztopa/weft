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
"""

import os
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest

from weft_kernel.discovery import ENTRY_POINT_GROUP, PackStatus, discover
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


def _assert_canary_installed_and_unimported() -> None:
    installed = {
        entry_point.dist.name
        for entry_point in metadata.entry_points(group=ENTRY_POINT_GROUP)
        if entry_point.dist is not None
    }
    assert CANARY_DISTRIBUTION in installed, (
        f"'{CANARY_DISTRIBUTION}' must be installed with a '{ENTRY_POINT_GROUP}' entry point "
        f"for this test to mean anything — run `uv sync` first."
    )
    assert CANARY_MODULE not in sys.modules, (
        f"'{CANARY_MODULE}' is already imported in this process, which makes the marker "
        f"check below meaningless — it would pass even if the code under test loaded the "
        f"canary before it should have, because Python does not re-execute an already"
        f"-imported module. Something else in this test session imported the canary "
        f"first; find it and stop it from doing so."
    )


def test_a_pack_refused_by_the_allow_list_is_never_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    marker = tmp_path / "canary-marker"
    monkeypatch.setenv(MARKER_ENV_VAR, str(marker))
    _assert_canary_installed_and_unimported()

    # Act
    reports = discover(Registry(), allow=[])

    # Assert
    assert not marker.exists(), (
        "the canary writes its marker at import; an allow-list that excludes it must stop "
        "discovery before the import happens, not merely before register() is called"
    )
    assert CANARY_MODULE not in sys.modules, (
        "the canary must never be imported at all when it is excluded from [packs] allow — "
        "this is the categorical form of the marker assertion above, independent of it"
    )
    by_distribution = {report.distribution: report for report in reports}
    assert by_distribution[CANARY_DISTRIBUTION].status == PackStatus.REFUSED


def test_version_command_executes_no_pack_code(tmp_path: Path) -> None:
    # Arrange — no [packs] allow at all: discovery, if it ran, would be wide open and would
    # happily import and register the canary. `weft --version` must still never call it. Run
    # in a fresh interpreter — see the module docstring on why an in-process assertion here
    # would be meaningless in this pytest session.
    marker = tmp_path / "canary-marker"
    env = {**os.environ, MARKER_ENV_VAR: str(marker)}
    _assert_canary_installed_and_unimported()

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
