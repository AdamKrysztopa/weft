"""Fitness function 9, clauses (a) and (b) — extension is proven from outside.

Specified in `docs/07-extension-cost.md` section 2 and `docs/06-phase-0-build.md`
step 10, and this file is what turns both on — `docs/build-ledger.md` 0.10:
"turns on FF9(a), FF9(b)". Clause (c) is not this file's: `07` states it
"active from Phase 2, the first phase that publishes a contract Phase 0 did
not", so it has no subject yet.

**Clause (a) — the stranger runs — is
`test_the_stranger_runs_and_uninstalling_it_breaks_resolution`.** It is
deliberately one test, not two, mirroring
`tests/integration/test_ingest_pipeline.py`'s own note that a scenario this
end-to-end "should read as a single, self-contained scenario": `docs/06`
step 10 states the property as one continuous proof — "Install it, run an
ingest pipeline that names it, uninstall it, and watch the pipeline fail to
resolve" — and splitting it into two tests would either duplicate the
expensive setup or make the second test depend on the first having already
run, which is worse.

**Real wheels, not `uv pip install <directory>`.** An early draft of this
test called `uv pip install` directly on `packages/weft-kernel`'s directory
and found that `weft-kernel` — and only `weft-kernel`, not `weft-chunk` or
the example pack — came back installed *editable*, `direct_url.json`
carrying `"editable": true` and a `.pth` file pointing straight at
`packages/weft-kernel/src`: a path back into this workspace, which is
exactly what clause (a) exists to rule out. `docs/07-extension-cost.md`
already says what to do instead — "The test builds the first-party
distributions as wheels, installs them plus the example pack into a
throwaway environment" — and building real wheel files with `uv build
--wheel` first, then installing *those files*, never exhibits the editable
behaviour: every `direct_url.json` below is checked to confirm it names a
`.whl` file, and `sys.path` is checked from inside the throwaway environment
itself to confirm no path under this repository is on it, so neither half of
"the source tree is not the reason it works" is taken on faith.

**Clause (b) — core does not know the stranger exists — is
`test_no_first_party_file_names_the_example_pack`.** It reads every file
under `packages/` and `testing/` for the example pack's distribution name,
module name and plugin name, none of which either side of clause (a) is
told to expect — computed independently, from the example pack's own
`pyproject.toml`, never from a shared constant a first-party file could also
import. `test_the_grep_can_actually_fail` is the self-test `07` requires: it
plants one of those same three strings in a throwaway file and confirms the
same scanning function reports it, so this clause cannot pass merely because
it stopped being able to fail.

**Clause (a)'s other half — *outside the uv workspace* — is
`test_the_example_pack_is_outside_the_uv_workspace`.** `07` names it as a
failure mode in as many words: "put the example back on the path as a
workspace member". The throwaway-environment test above would not notice
that happening — a workspace member builds a wheel and installs into a
throwaway venv exactly as a stranger does — so the membership itself is read
from the root `pyproject.toml` and checked against the example's own
location, against both places the workspace can claim a distribution:
`[tool.uv.workspace] members` and `[tool.uv.sources]`. Neither file is under
`packages/` or `testing/`, so clause (b)'s scan does not cover them either.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from collections.abc import Iterable
from fnmatch import fnmatch
from pathlib import Path
from typing import Final

import pytest

from .conftest import str_list_at, table_at

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
KERNEL_DIR: Final[Path] = REPO_ROOT / "packages" / "weft-kernel"
CHUNK_DIR: Final[Path] = REPO_ROOT / "packages" / "weft-chunk"
EXAMPLE_DIR: Final[Path] = REPO_ROOT / "examples" / "weft-example-chunker"
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"
TESTING_ROOT: Final[Path] = REPO_ROOT / "testing"

#: The example pack's own identity, read from its `pyproject.toml` rather than restated —
#: a hand-typed copy here is exactly the second-list-that-can-drift `README.md` opens with.
with (EXAMPLE_DIR / "pyproject.toml").open("rb") as _handle:
    _EXAMPLE_PROJECT = tomllib.load(_handle)["project"]

EXAMPLE_DISTRIBUTION: Final[str] = _EXAMPLE_PROJECT["name"]  # "weft-example-chunker"
EXAMPLE_MODULE: Final[str] = _EXAMPLE_PROJECT["entry-points"]["weft.packs"][
    "example-chunker"
].split(":")[0]  # "weft_example_chunker"
EXAMPLE_PLUGIN_NAME: Final[str] = "example-chunker"  # docs/06 step 10: "registering one chunker"

#: The probe every throwaway environment runs. `{repo_root!r}` lets it assert, from *inside*
#: the environment under test, that nothing on `sys.path` reaches back into this repository —
#: the machine-checked form of "the source tree is not the reason it works", not just an
#: absence of `PYTHONPATH` this test happens to control from the outside.
_PROBE_SCRIPT = """
import asyncio
import sys

repo_root = {repo_root!r}
leaked = [p for p in sys.path if p and (p == repo_root or p.startswith(repo_root + "/"))]
if leaked:
    print("LEAKED")
    print(",".join(leaked))
    raise SystemExit(0)

from weft_chunk.contract import Chunker
from weft_kernel.context import Context
from weft_kernel.discovery import discover
from weft_kernel.payload import MediaType, Node
from weft_kernel.registry import Registry, UnknownPluginError
from weft_kernel.runner import Runner, StageSpec

registry = Registry()
discover(registry)
runner = Runner(registry)
specs = (StageSpec(id="chunk", contract=Chunker, name={plugin_name!r}),)

try:
    pipeline = runner.resolve(specs, tenant_id="tenant-a")
except UnknownPluginError as exc:
    print("MISSING")
    print(str(exc))
    raise SystemExit(0)

node = Node.synthetic(content="alpha beta gamma", media_type=MediaType.TEXT, reason="ff9 probe")


async def _one_batch(batch):
    yield batch


async def _run() -> None:
    ctx = Context(tenant_id="tenant-a", run_id="r", trace_id="t", locale="en")
    summary = await runner.run(pipeline, _one_batch([node]), ctx)
    print("OK")
    print(summary.produced)
    print(pipeline.stages[0].distribution)


asyncio.run(_run())
"""


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """One `uv`/`python` subprocess call, with `PYTHONPATH` scrubbed from its environment.

    Fixed argv built entirely from paths this test computed itself — no shell, nothing
    user-controlled.
    """
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    return subprocess.run(  # noqa: S603 — fixed argv, no shell
        command, cwd=cwd, env=env, capture_output=True, text=True, timeout=120, check=False
    )


def _build_wheel(source_dir: Path, *, out_dir: Path) -> Path:
    result = _run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir), str(source_dir)], cwd=out_dir
    )
    assert result.returncode == 0, (
        f"building a wheel for {source_dir} failed:\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    wheels = sorted(out_dir.glob(f"{source_dir.name.replace('-', '_')}-*.whl"))
    assert wheels, f"uv build reported success but no wheel matching {source_dir.name} appeared"
    return wheels[-1]


@pytest.mark.timeout(180)
def test_the_stranger_runs_and_uninstalling_it_breaks_resolution(tmp_path: Path) -> None:
    # Arrange — real wheel files (never `uv pip install <directory>` — see the module
    # docstring for why that alternative silently exposes this repository's own source
    # tree) for the two first-party distributions the example needs, plus the example
    # itself, installed into a venv that has never heard of this repository.
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    kernel_wheel = _build_wheel(KERNEL_DIR, out_dir=wheel_dir)
    chunk_wheel = _build_wheel(CHUNK_DIR, out_dir=wheel_dir)
    example_wheel = _build_wheel(EXAMPLE_DIR, out_dir=wheel_dir)

    for wheel, source_dir in (
        (kernel_wheel, KERNEL_DIR),
        (chunk_wheel, CHUNK_DIR),
        (example_wheel, EXAMPLE_DIR),
    ):
        assert wheel.suffix == ".whl", f"{source_dir} did not produce a wheel file: {wheel}"

    project_dir = tmp_path / "throwaway-project"
    project_dir.mkdir()
    venv_dir = project_dir / ".venv"
    created = _run(["uv", "venv", str(venv_dir), "--python", "3.12"], cwd=project_dir)
    assert created.returncode == 0, f"uv venv failed:\n{created.stderr}"
    python = venv_dir / "bin" / "python"

    installed = _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            str(kernel_wheel),
            str(chunk_wheel),
            str(example_wheel),
        ],
        cwd=project_dir,
    )
    assert installed.returncode == 0, f"uv pip install failed:\n{installed.stderr}"

    for wheel in (kernel_wheel, chunk_wheel, example_wheel):
        direct_url = _dist_info_dir(venv_dir, wheel).joinpath("direct_url.json").read_text()
        assert '"editable": true' not in direct_url.replace(" ", ""), (
            f"{wheel.name} was installed editable — its direct_url.json is {direct_url!r}. "
            f"An editable install can resolve straight back into this workspace, which is "
            f"exactly what this test exists to rule out."
        )

    probe = project_dir / "probe.py"
    probe.write_text(
        _PROBE_SCRIPT.format(repo_root=str(REPO_ROOT), plugin_name=EXAMPLE_PLUGIN_NAME),
        encoding="utf-8",
    )

    # Act — installed: resolve and run a pipeline naming the example's own plugin.
    ran = _run([str(python), str(probe)], cwd=project_dir)

    # Assert — it worked, from the distribution the throwaway environment actually installed.
    assert ran.returncode == 0, f"the probe crashed:\nstdout:\n{ran.stdout}\nstderr:\n{ran.stderr}"
    lines = ran.stdout.strip().splitlines()
    assert lines and lines[0] != "LEAKED", (
        f"a path back into this repository is on sys.path inside the throwaway environment: "
        f"{lines[1] if len(lines) > 1 else '?'}"
    )
    assert lines[:1] == ["OK"], f"expected the pipeline to resolve and run; probe said: {lines}"
    produced, distribution = lines[1], lines[2]
    assert produced == "1", f"expected one produced batch, got {produced!r}"
    assert distribution == EXAMPLE_DISTRIBUTION, (
        f"the chunk stage resolved to distribution {distribution!r}, not "
        f"{EXAMPLE_DISTRIBUTION!r} — this pipeline should have run the example pack's own "
        f"plugin, not weft-chunk's built-in 'fixed-size'."
    )

    # Act — uninstalled: the same pipeline, against the same venv, minus the example.
    uninstalled = _run(
        ["uv", "pip", "uninstall", "--python", str(python), EXAMPLE_DISTRIBUTION], cwd=project_dir
    )
    assert uninstalled.returncode == 0, f"uv pip uninstall failed:\n{uninstalled.stderr}"
    ran_again = _run([str(python), str(probe)], cwd=project_dir)

    # Assert — resolution fails, and the message names what no distribution registered.
    assert ran_again.returncode == 0, (
        f"the probe crashed:\nstdout:\n{ran_again.stdout}\nstderr:\n{ran_again.stderr}"
    )
    again_lines = ran_again.stdout.strip().splitlines()
    assert again_lines[:1] == ["MISSING"], (
        f"expected resolution to fail once the example pack is uninstalled; probe said: "
        f"{again_lines}"
    )
    message = again_lines[1]
    assert EXAMPLE_PLUGIN_NAME in message, message
    assert "no distribution has registered" in message, message


def _dist_info_dir(venv_dir: Path, wheel: Path) -> Path:
    """The `*.dist-info` directory a wheel's own name maps to, inside `venv_dir`'s site-packages."""
    site_packages = next((venv_dir / "lib").glob("python3.*/site-packages"))
    project, version = wheel.stem.split("-")[:2]
    candidates = list(site_packages.glob(f"{project}-{version}.dist-info"))
    assert candidates, f"no dist-info for {wheel.name} under {site_packages}"
    return candidates[0]


def _text_files(*roots: Path) -> Iterable[Path]:
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            yield path


def _files_naming(names: Iterable[str], *, within: Iterable[Path]) -> list[tuple[Path, str]]:
    """Every `(file, name)` pair where `file` contains `name` as a literal substring.

    Binary files (compiled `.pyc`, if any slip past the `__pycache__` filter) are skipped
    on a decode failure rather than raising — this function's job is to find text that
    names the example pack, not to police what counts as text.
    """
    hits: list[tuple[Path, str]] = []
    for path in within:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in names:
            if name in text:
                hits.append((path, name))
    return hits


def test_no_first_party_file_names_the_example_pack() -> None:
    # Arrange — the example pack's own identity, never a copy of it.
    names = (EXAMPLE_DISTRIBUTION, EXAMPLE_MODULE, EXAMPLE_PLUGIN_NAME)

    # Act
    hits = _files_naming(names, within=_text_files(PACKAGES_ROOT, TESTING_ROOT))

    # Assert
    assert not hits, (
        "the example pack is named from inside packages/ or testing/, which fitness "
        "function 9(b) forbids — core must not anticipate a stranger it never imported:\n  "
        + "\n  ".join(f"{path.relative_to(REPO_ROOT)}: {name!r}" for path, name in hits)
    )


def test_the_example_pack_is_outside_the_uv_workspace(
    workspace_config: dict[str, object],
) -> None:
    # Arrange — the workspace's own two claims on a distribution, read from the root
    # `pyproject.toml`; the example's location, read from where this file says it is.
    members = str_list_at(table_at(workspace_config, "tool", "uv", "workspace"), "members")
    sources = table_at(workspace_config, "tool", "uv", "sources")
    location = EXAMPLE_DIR.relative_to(REPO_ROOT).as_posix()

    # Act
    claiming = [glob for glob in members if fnmatch(location, glob)]

    # Assert
    assert not claiming, (
        f"`{location}` is matched by `[tool.uv.workspace] members` {claiming} — the example "
        f"pack is a workspace member, which fitness function 9(a) forbids in as many words. "
        f"A member is synced into this repository's own environment and locked in `uv.lock`, "
        f"so it is no longer a stranger, and the throwaway-environment test above cannot see "
        f"the difference."
    )
    assert EXAMPLE_DISTRIBUTION not in sources, (
        f"`[tool.uv.sources]` pins {EXAMPLE_DISTRIBUTION!r}. `docs/07-extension-cost.md` §1 "
        f"names that line as the one packaging cost a *first-party* pack pays and an "
        f"out-of-tree pack does not; taking it here would make the example one of ours."
    )


def test_the_grep_can_actually_fail(tmp_path: Path) -> None:
    # Arrange — plant one of the same three literals `_files_naming` looks for.
    planted = tmp_path / "planted.py"
    planted.write_text(f"# pretend core imported {EXAMPLE_MODULE}\n", encoding="utf-8")

    # Act
    hits = _files_naming(
        (EXAMPLE_DISTRIBUTION, EXAMPLE_MODULE, EXAMPLE_PLUGIN_NAME), within=_text_files(tmp_path)
    )

    # Assert
    assert hits == [(planted, EXAMPLE_MODULE)], (
        "the scanning helper behind clause (b) did not find a literal planted for exactly "
        "this purpose; a clause that stopped being able to fail would pass on a tree that "
        "names the example pack from core, which is the everyday case it exists to catch"
    )
