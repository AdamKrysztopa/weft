"""Phase 3's exit criterion — task **3.8**, `docs/build-ledger.md`.

`docs/01-high-level-plan.md` -> Phase 3 **Exit**: "a plugin ships a command that appears in
`weft --help` and in REPL completion without core knowing it exists." This file is that
demonstration, run against the real, installed `weft-example-command` pack
(`examples/weft-example-command/`, built at task 3.2) rather than argued from the code shape.

**Repaired, 2026-08-20, from a review of `4aeba88` (task 2.36's own form: a dated paragraph
appended, no new checkbox).** This file used to prove claim 1 against `weft <name> --help` — the
per-command leaf help — with a paragraph arguing that bare `weft --help` "enters the session"
instead, citing `docs/03-cli.md` -> *Two modes, one implementation* as if that were settled,
deliberate behaviour. It was not: `weft_cli.cli.prescan_command_name` strips every `-`-prefixed
token while guessing a command name, so `argv = ["--help"]` reduced to no tokens, which task 3.4's
own REPL-entry rule (correctly) routes to the session — `-h`/`--help` never reached `build_parser`'s
generated help at all. That is `weft_cli.cli.wants_help`'s own repair (see that function's
docstring and `main`'s, "Repaired, 2026-08-20"), not a documentation correction, and the exit
criterion is stated in exactly the bare form this file now demonstrates: `weft --help`, not `weft
<name> --help`. Per-command leaf help is kept below as an **additional** assertion — the two
surfaces are genuinely different code paths through the same parser (the top-level `-h`/`--help`
action versus a leaf subparser's own), and both are real claims of *Plugin-contributed commands* —
but bare `weft --help` is the one the exit criterion names, and it now carries the primary
assertion.

**Not a new fitness function — the task's own `turns on` field is `—`.** Fitness function 9's
three clauses are generic over *any* published contract; this property is specific to `Command`
and to two CLI-only surfaces neither clause reaches — `weft --help`'s generated text and
`weft_cli.repl.repl_completions` — so it earns its own file rather than a fourth clause bolted
onto `test_ff9_extension_from_outside.py` or `test_ff9c_every_contract_has_a_stranger.py`. It is
reachable from `uv run poe ci-checks` exactly as those two are: `tool.poe.tasks.arch` runs every
file under `tests/architecture` (`pytest tests/architecture -q`), and `test_ff0_gate_in_the_gate.
py`'s own `ARCHITECTURE_TASKS = frozenset({"arch"})` is what asserts that composite task sits
inside `ci-checks` — confirmed by reading that test rather than assumed.

**Three claims, three mechanisms — none of them an in-process Python call standing in for the
real one.**

1. **Appears in bare `weft --help`.** Proven by invoking the real, installed `weft` console
   script (`weft-cli`'s own `[project.scripts]` entry) in a subprocess, with the literal
   `--help` flag and no command name, inside a throwaway environment that has never heard of
   this repository. This is the exit criterion's own words: "a plugin ships a command that
   appears in `weft --help`" names the top-level surface, not a per-command leaf. `weft
   --help` reaches the registry-driven `argparse.ArgumentParser` (`weft_cli.cli.build_parser`)
   the same way every other invocation does — `weft_cli.cli.main` runs discovery and builds
   that parser unconditionally, before it decides which branch to take — and `wants_help`'s own
   pre-scan (see that function's docstring, "Repaired, 2026-08-20") is what routes a lone
   `-h`/`--help` to `parser.parse_args(argv)` instead of the REPL; `argparse`'s own help action
   then fires before the required-subparsers check, printing the plugin's registered name and
   its declared `help` text among every other command's, with no core file naming it anywhere.
   `weft <name> --help` — the leaf form this file used to test exclusively — is kept below as a
   second, additional assertion of the same underlying mechanism (`build_parser`'s own nested
   subparser for the plugin's name), not the only proof.
2. **Appears in REPL completion.** Proven by running a probe script, inside the same throwaway
   environment's own interpreter, that calls the real, installed `weft_cli.registry_bootstrap.
   build_dependencies` and `weft_cli.repl.repl_completions` — the exact function `weft_cli.repl`'s
   own module docstring names as "what a test — 3.8's, or this file's own — can call directly,
   without a pty or a keypress." Not reimplemented: imported from the wheel actually installed.
3. **Without core knowing it exists.** Proven the same way `test_ff9_extension_from_outside.py`'s
   clause (b) proves it for every example pack generically — `files_naming`, imported from that
   module rather than reimplemented, scanning every file under `packages/` for the plugin's
   distribution name, module name and registered plugin name, each read from the pack's own
   `pyproject.toml`/`register()` rather than hand-typed here. `weft-example-command` is already
   one of that test's `_ALL_EXAMPLE_DIRS` (walked from `examples/`'s own directory listing), so
   this property already runs on every commit as part of FF9(b) — this file's own copy of the
   scan is not filling a gap, it is restating the same evidence from the phase-exit angle, on the
   one function proven able to fail (`test_ff9_extension_from_outside.py::
   test_the_grep_can_actually_fail`) rather than a second implementation of the walk.

**Nothing here is a hand-typed second copy of the plugin's identity.** `distribution_name` and
`module_and_plugin_names`, imported from `test_ff9_extension_from_outside`, read the
distribution name, module name and registered plugin name off `weft-example-command`'s own
`pyproject.toml` and its own real `register()` call — the identical reason that module's own
docstring gives for doing the same for `weft-example-chunker`: "a hand-typed second copy here is
exactly the second-list-that-can-drift `README.md` opens with."

**The venv-building machinery is reused, not reinvented a third time.** `run_subprocess`/
`build_wheel`/`FIRST_PARTY_DISTRIBUTIONS`/`PACKAGES_ROOT` are imported from
`test_ff9c_every_contract_has_a_stranger`, which already builds every first-party wheel once per
run rather than hand-computing `weft-cli`'s own transitive dependency closure — its own
docstring's stated reason ("a second dependency graph, hand-maintained, drifting from each
`pyproject.toml`'s own `dependencies` list") applies identically here, so this file installs the
same "everything, plus the one stranger" shape rather than arguing a smaller one. **Both helper
pairs used to be spelled with a leading underscore, in both source files, until this task.**
`pyright`'s own `strict` mode (`reportPrivateUsage`) refuses a third module importing a
single-underscore name across files — correctly, since the convention exists to mark "not part of
this module's own interface" — so reusing them honestly, rather than reimplementing them a third
time to dodge the check, meant renaming the four functions this file needs
(`test_ff9_extension_from_outside.distribution_name`/`module_and_plugin_names`/`files_naming`/
`text_files`) and the three `test_ff9c_every_contract_has_a_stranger` already exposed under
`_`-prefixed names (`run_subprocess`/`build_wheel`/`FIRST_PARTY_DISTRIBUTIONS`) to their public
spellings, in the same commit, with every call site inside both files updated too — a rename, not
an extraction: they are genuinely shared infrastructure across three files now, which the old
names denied. No fourth, standalone module was created to hold a second copy of a decision two
files had already made identically twice.

**The self-test — plant the failure, confirm it is caught, per `test_ff9c`'s own discipline
(`test_the_discovery_ratchet_can_actually_fail`) and `test_ff9`'s (`test_the_grep_can_actually_
fail`).** `test_the_strangers_command_reaches_help_and_completion_without_core_naming_it` installs
the pack, proves bare `weft --help`, the leaf `weft <name> --help` and REPL completion all show
it, then **uninstalls it and re-runs every probe against the same venv** — bare `weft --help` no
longer names the plugin among its listed subcommands, `weft <name> --help` fails with `argparse`'s
own "invalid choice", and `repl_completions` no longer names it. A version of this file with the
mechanism removed (the plugin's command hard-coded into `build_parser`, say) would still pass the
"installed" half and fail the "uninstalled" half loudly, which is what makes this a proof of the
*mechanism* rather than of one fixed transcript. `test_the_command_name_scan_can_actually_fail` is
the matching self-test for claim 3, on `test_ff9`'s own planted-literal pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from .test_ff9_extension_from_outside import (
    distribution_name,
    files_naming,
    module_and_plugin_names,
    text_files,
)
from .test_ff9c_every_contract_has_a_stranger import (
    FIRST_PARTY_DISTRIBUTIONS,
    PACKAGES_ROOT,
    build_wheel,
    run_subprocess,
)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
EXAMPLE_DIR: Final[Path] = REPO_ROOT / "examples" / "weft-example-command"

#: The probe every throwaway environment runs, once, for claim 2 — imported straight from the
#: installed wheel, never reimplemented. `build_dependencies()` with no arguments is exactly
#: `weft_cli.cli.main`'s own call for a `weft.toml`-less project (see that function's own
#: module docstring): no database, no config file, the same first-run shape `manual/
#: quickstart.md` walks.
_COMPLETION_PROBE_SCRIPT = """
import sys

repo_root = {repo_root!r}
leaked = [p for p in sys.path if p and (p == repo_root or p.startswith(repo_root + "/"))]
if leaked:
    print("LEAKED")
    print(",".join(leaked))
    raise SystemExit(0)

from weft_cli.registry_bootstrap import build_dependencies
from weft_cli.repl import repl_completions

deps = build_dependencies()
print("OK")
for name in repl_completions(deps.registry, ""):
    print(name)
"""


@pytest.mark.timeout(900)
def test_the_strangers_command_reaches_help_and_completion_without_core_naming_it(
    tmp_path: Path,
) -> None:
    # Arrange — the plugin's own identity, read off its own pyproject.toml and its own real
    # register() call, never hand-typed (see the module docstring's "not a hand-typed second
    # copy" paragraph).
    distribution = distribution_name(EXAMPLE_DIR)
    _module_name, plugin_names = module_and_plugin_names(EXAMPLE_DIR)
    assert len(plugin_names) == 1, (
        f"expected weft-example-command to register exactly one Command, found {plugin_names} "
        f"— this test's own claims are written for the pack as it stands; a second command "
        f"changes what 'the' plugin name below refers to"
    )
    plugin_name = plugin_names[0]

    # Arrange — every first-party wheel plus the stranger's, built once, shared by both probes
    # below — `test_ff9c`'s own "install everything" shape (see the module docstring).
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    first_party_wheels = [
        build_wheel(PACKAGES_ROOT / dist, out_dir=wheel_dir) for dist in FIRST_PARTY_DISTRIBUTIONS
    ]
    example_wheel = build_wheel(EXAMPLE_DIR, out_dir=wheel_dir)

    project_dir = tmp_path / "throwaway-project"
    project_dir.mkdir()
    venv_dir = project_dir / ".venv"
    created = run_subprocess(["uv", "venv", str(venv_dir), "--python", "3.12"], cwd=project_dir)
    assert created.returncode == 0, f"uv venv failed:\n{created.stderr}"
    python = venv_dir / "bin" / "python"
    weft_bin = venv_dir / "bin" / "weft"

    installed = run_subprocess(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            *(str(wheel) for wheel in first_party_wheels),
            str(example_wheel),
        ],
        cwd=project_dir,
    )
    assert installed.returncode == 0, f"uv pip install failed:\n{installed.stderr}"

    completion_probe = project_dir / "completion_probe.py"
    completion_probe.write_text(
        _COMPLETION_PROBE_SCRIPT.format(repo_root=str(REPO_ROOT)), encoding="utf-8"
    )

    # Act — claim 1, primary: the real `weft` binary, bare `--help`, no command named — the
    # exit criterion's own words, and a real subprocess. `weft_cli.cli.wants_help` is what keeps
    # this out of the REPL; see that function's docstring and `main`'s, "Repaired, 2026-08-20".
    bare_help_ran = run_subprocess([str(weft_bin), "--help"], cwd=project_dir)

    # Assert — claim 1 holds, in the form the exit criterion states it: the plugin's own
    # registered name and declared `help` text are listed among every other command's, in the
    # top-level help `argparse` generates from `build_parser`'s walk of the registry.
    assert bare_help_ran.returncode == 0, (
        f"'weft --help' failed once installed:\nstdout:\n{bare_help_ran.stdout}\n"
        f"stderr:\n{bare_help_ran.stderr}"
    )
    assert "weft -- interactive session" not in bare_help_ran.stdout, (
        "'weft --help' entered the interactive session instead of printing help — this is "
        "the exact defect task 2.36's repair form records against 3.2/3.4/3.8: a lone "
        "-h/--help was stripped to no command name and routed to the REPL"
    )
    assert plugin_name in bare_help_ran.stdout, (
        f"'{plugin_name}' did not appear in bare 'weft --help', the exit criterion's own "
        f"surface: {bare_help_ran.stdout!r}"
    )

    # Act — claim 1, additional: the per-command leaf help — a second, real code path through
    # the same registry-driven parser (a nested subparser rather than the top-level -h/--help
    # action), kept as extra evidence of the same mechanism, not the only proof of claim 1.
    help_ran = run_subprocess([str(weft_bin), plugin_name, "--help"], cwd=project_dir)

    # Assert — the leaf form holds too: the plugin's own leaf help names it in the usage line
    # argparse always prints first.
    assert help_ran.returncode == 0, (
        f"'weft {plugin_name} --help' failed once installed:\nstdout:\n{help_ran.stdout}\n"
        f"stderr:\n{help_ran.stderr}"
    )
    assert f"weft {plugin_name}" in help_ran.stdout, (
        f"'weft {plugin_name} --help' did not name the plugin in its own usage line: "
        f"{help_ran.stdout!r}"
    )

    # Act — claim 2: the real, installed `repl_completions`, called from inside the venv.
    completion_ran = run_subprocess([str(python), str(completion_probe)], cwd=project_dir)

    # Assert — claim 2 holds.
    assert completion_ran.returncode == 0, (
        f"the completion probe crashed:\n{completion_ran.stdout}\n{completion_ran.stderr}"
    )
    completion_lines = completion_ran.stdout.strip().splitlines()
    assert completion_lines and completion_lines[0] != "LEAKED", (
        f"a path back into this repository is on sys.path inside the throwaway environment: "
        f"{completion_lines[1] if len(completion_lines) > 1 else '?'}"
    )
    assert completion_lines[:1] == ["OK"], (
        f"completion probe did not discover cleanly: {completion_lines}"
    )
    assert plugin_name in completion_lines[1:], (
        f"'{plugin_name}' did not appear in repl_completions()'s own output: {completion_lines[1:]}"
    )

    # Act — self-test: uninstall the stranger, from the same venv, and re-run every probe.
    uninstalled = run_subprocess(
        ["uv", "pip", "uninstall", "--python", str(python), distribution], cwd=project_dir
    )
    assert uninstalled.returncode == 0, f"uv pip uninstall failed:\n{uninstalled.stderr}"

    bare_help_ran_again = run_subprocess([str(weft_bin), "--help"], cwd=project_dir)
    help_ran_again = run_subprocess([str(weft_bin), plugin_name, "--help"], cwd=project_dir)
    completion_ran_again = run_subprocess([str(python), str(completion_probe)], cwd=project_dir)

    # Assert — every mechanism genuinely depends on the pack being installed, not on this
    # test's own transcript: removing it breaks all three, which is what makes the "installed"
    # half above a proof of the mechanism rather than of one fixed run.
    assert bare_help_ran_again.returncode == 0, (
        f"'weft --help' itself must keep working once the stranger is gone — only its listing "
        f"of the plugin should disappear:\nstdout:\n{bare_help_ran_again.stdout}\n"
        f"stderr:\n{bare_help_ran_again.stderr}"
    )
    assert plugin_name not in bare_help_ran_again.stdout, (
        f"'{plugin_name}' still appeared in bare 'weft --help' after uninstalling "
        f"{distribution} — the top-level help surface did not actually depend on the pack "
        f"being installed: {bare_help_ran_again.stdout!r}"
    )
    assert help_ran_again.returncode != 0, (
        f"'weft {plugin_name} --help' still succeeded after uninstalling "
        f"{distribution} — the help surface did not actually depend on the pack being "
        f"installed: {help_ran_again.stdout!r}"
    )
    assert "invalid choice" in help_ran_again.stderr, (
        f"expected argparse's own 'invalid choice' once the plugin no longer registers "
        f"'{plugin_name}'; got:\n{help_ran_again.stderr}"
    )
    completion_again_lines = completion_ran_again.stdout.strip().splitlines()
    assert completion_again_lines[:1] == ["OK"], (
        f"completion probe did not discover cleanly after uninstall: {completion_again_lines}"
    )
    assert plugin_name not in completion_again_lines[1:], (
        f"'{plugin_name}' still appeared in repl_completions() after uninstalling "
        f"{distribution} — completion did not actually depend on the pack being installed"
    )


def test_no_first_party_file_names_the_strangers_command() -> None:
    # Arrange — the same three names claim 3 forbids core from ever writing down, computed the
    # same way the big test above computes them.
    distribution = distribution_name(EXAMPLE_DIR)
    module_name, plugin_names = module_and_plugin_names(EXAMPLE_DIR)
    names = [distribution, module_name, *plugin_names]

    # Act
    hits = files_naming(names, within=text_files(PACKAGES_ROOT))

    # Assert
    assert not hits, (
        "weft-example-command's own identity is named from inside packages/, which is "
        "precisely what Phase 3's exit criterion — 'without core knowing it exists' — "
        "forbids:\n  "
        + "\n  ".join(f"{path.relative_to(REPO_ROOT)}: {name!r}" for path, name in hits)
    )


def test_the_command_name_scan_can_actually_fail(tmp_path: Path) -> None:
    # Arrange — plant one of the same names the test above looks for, `test_ff9`'s own
    # `test_the_grep_can_actually_fail` pattern applied to this file's own names.
    _distribution, plugin_names = module_and_plugin_names(EXAMPLE_DIR)
    plugin_name = plugin_names[0]
    planted = tmp_path / "planted.py"
    planted.write_text(f"# pretend core dispatched on {plugin_name!r} directly\n", encoding="utf-8")

    # Act
    hits = files_naming((plugin_name,), within=text_files(tmp_path))

    # Assert
    assert hits == [(planted, plugin_name)], (
        "the scan behind claim 3 did not find a literal planted for exactly this purpose; a "
        "check that stopped being able to fail would pass on a tree that names the plugin "
        "from core, which is the everyday case it exists to catch"
    )
