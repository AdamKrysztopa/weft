"""Fitness function 9, clauses (a) and (b) — extension is proven from outside.

Specified in `docs/07-extension-cost.md` section 2 and `docs/06-phase-0-build.md`
step 10, and this file is what turns both on — `docs/build-ledger.md` 0.10:
"turns on FF9(a), FF9(b)". Clause (c) is not this file's: `07` states it
"active from Phase 2, the first phase that publishes a contract Phase 0 did
not", so it has no subject yet.

**Clause (b) covers "any example pack" (`07` §2), not just the first one written.** Task
2.11 added three more out-of-tree packs (`weft-example-ingest`, `-llm`, `-query`) alongside
`weft-example-chunker`, and `.phase2-design.md` §9 states the obligation in as many words:
"no file under `packages/` or `testing/` may contain `weft-example-ingest`,
`weft_example_ingest`, `weft-example-llm`, `weft-example-query`, or any plugin name they
register". `test_no_first_party_file_names_the_example_pack` and
`test_the_example_pack_is_outside_the_uv_workspace` therefore walk every directory under
`examples/` that carries a `pyproject.toml` (`_ALL_EXAMPLE_DIRS`, the identical
directory-listing pattern `test_ff9c_every_contract_has_a_stranger.py`'s `_EXAMPLE_DIRS`
already uses), rather than the single `EXAMPLE_DIR` clause (a)'s own end-to-end pipeline
test still targets — that test is deliberately one pack's worth of expensive setup, per its
own note below, and broadening it would not make clause (b)'s coverage any wider.

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

import ast
import os
import subprocess
import sys
import tomllib
import typing
from collections.abc import Iterable
from fnmatch import fnmatch
from importlib import import_module, metadata
from pathlib import Path
from typing import Final

import pytest

from weft_kernel.discovery import PackRegistrar

from .conftest import str_list_at, table_at

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
KERNEL_DIR: Final[Path] = REPO_ROOT / "packages" / "weft-kernel"
#: The distribution that publishes the `Chunker` contract the example pack registers
#: against — `weft-chunk` until 2026-09-05, and `weft-rag` since, which ships `weft_chunk`
#: along with thirteen other packages. A stranger installs whatever publishes the contract,
#: so this test installs whatever that is now.
CHUNK_DIR: Final[Path] = REPO_ROOT / "packages" / "weft-rag"
EXAMPLE_DIR: Final[Path] = REPO_ROOT / "examples" / "weft-example-chunker"
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"
TESTING_ROOT: Final[Path] = REPO_ROOT / "testing"
EXAMPLES_ROOT: Final[Path] = REPO_ROOT / "examples"

#: The example pack's own identity, read from its `pyproject.toml` rather than restated —
#: a hand-typed copy here is exactly the second-list-that-can-drift `README.md` opens with.
with (EXAMPLE_DIR / "pyproject.toml").open("rb") as _handle:
    _EXAMPLE_PROJECT = tomllib.load(_handle)["project"]

EXAMPLE_DISTRIBUTION: Final[str] = _EXAMPLE_PROJECT["name"]  # "weft-example-chunker"
EXAMPLE_MODULE: Final[str] = _EXAMPLE_PROJECT["entry-points"]["weft.packs"][
    "example-chunker"
].split(":")[0]  # "weft_example_chunker"
EXAMPLE_PLUGIN_NAME: Final[str] = "example-chunker"  # docs/06 step 10: "registering one chunker"

#: Every out-of-tree example pack under `examples/` — read from the directory listing itself,
#: the identical pattern `test_ff9c_every_contract_has_a_stranger.py`'s `_EXAMPLE_DIRS` uses,
#: so a fifth example pack extends clause (b)'s scan below without an edit here. Clause (a)'s
#: own end-to-end test above stays pinned to `EXAMPLE_DIR` alone — one real pipeline is what
#: that test proves, and it does not need every pack to prove it once.
_ALL_EXAMPLE_DIRS: Final[tuple[Path, ...]] = tuple(
    sorted(p for p in EXAMPLES_ROOT.iterdir() if (p / "pyproject.toml").is_file())
)


class _NameCapturingRegistrar:
    """A `PackRegistrar` stand-in that records the plugin name of every `.add()` call.

    Clause (b)'s scan needs every name a pack registers, not just the single one
    `weft-example-chunker` happens to have — and several of the newer packs build that name
    from a submodule's own `NAME` constant rather than a literal inline in `register()`
    (`weft-example-query`'s `TRANSFORM_NAME`, `RETRIEVER_NAME`, `GENERATOR_NAME`, for
    instance). Running each pack's real `register()` against this stand-in reads the names
    structurally, off the one function that is already the source of truth for them, rather
    than re-typing a second list here that could drift the moment a pack adds a plugin.
    """

    def __init__(self) -> None:
        self.names: list[str] = []

    def add(self, contract: object, name: str, factory: object, **_: object) -> None:
        del contract, factory
        self.names.append(name)

    def add_ext_model(self, model: object) -> None:
        """A no-op stand-in for `PackRegistrar.add_ext_model` (task 5.2g).

        `weft-example-ingest`'s own `WordCount` namespace is identical to its distribution
        name — `weft_example_ingest.enhancer.WordCount.__namespace__ ==
        "weft-example-ingest"` — already captured via `distribution_name` in the caller
        below, so this scan needs nothing further from an `ExtModel` a pack declares; it
        only needs `register()` not to raise `AttributeError` calling it.
        """
        del model

    def add_pipeline_resource(self, package: str, resource: str) -> None:
        """A no-op stand-in for `PackRegistrar.add_pipeline_resource` (task 1.11).

        The oldest of the three non-plugin contributions and the last to be stubbed here,
        because no example pack shipped a pipeline until `examples/weft-graph` did at task
        5.5 — which is exactly how a hand-maintained double drifts: it grows a method when
        something calls it, so the gap is invisible for as long as nothing does.
        `test_the_double_carries_every_registrar_method` below is what stops the fourth
        recurrence; see `docs/lessons.md` L5.26.
        """
        del package, resource

    def deprecate(self, surface: str, *, reason: str) -> None:
        """A no-op stand-in for `PackRegistrar.deprecate` (task 5.2e).

        Found missing by `test_the_double_carries_every_registrar_method` below rather than
        by a pack crashing on it — which is the whole reason that test exists. A deprecation
        names a surface, never a plugin, so clause (b)'s scan needs nothing from it.
        """
        del surface, reason

    def unavailable(self, surface: str, *, reason: str) -> None:
        """A no-op stand-in — ledger task **6.29** added this to `PackRegistrar`.

        Same reason `deprecate` above is here: this double must carry every public method the
        real registrar declares, or a pack's `register()` calling one raises `AttributeError`
        inside whichever check happens to run it. `docs/lessons.md` **L5.26** is that rule, and
        the completeness check enforcing it is what caught this within a minute of the method
        landing.
        """
        del surface, reason

    def commit(self) -> None:
        """A no-op stand-in for `PackRegistrar.commit`.

        Nothing here calls it — `module_and_plugin_names` reads the names off `.add()` and
        stops — but a double that is missing a method the real class declares is a double
        that breaks the moment a caller changes, so it is stubbed rather than argued about.
        """

    def add_contribution(self, slot: str, stage: object) -> None:
        """A no-op stand-in for `PackRegistrar.add_contribution` (task 5.3a, `S8`).

        `weft-example-ingest` now offers one (`ENRICH_SLOT`, reusing its own
        `example-enhancer` plugin, already captured by `.add()` above under its own name)
        — this method exists purely so `register()` calling it here does not raise
        `AttributeError`, the identical reason `add_ext_model` above exists. Clause (b)'s
        own scan needs nothing further from a `Contribution`: it names no new plugin, only
        a slot a pipeline document declares.
        """
        del slot, stage

    def add_renderer(self, result_type: object, renderer: object) -> None:
        """A no-op stand-in for `PackRegistrar.add_renderer` (task 6.20, G13).

        **The fourth recurrence, and the first one this file caught before a pack crashed on
        it.** `add_pipeline_resource`'s own docstring above named the shape — a hand-maintained
        double grows a method only when something calls it, so the gap is invisible for as long
        as nothing does — and predicted that `test_the_double_carries_every_registrar_method`
        below is "what stops the fourth recurrence". This is that fourth recurrence:
        `examples/weft-example-graph`'s `register()` began calling `add_renderer` at task 6.20,
        and the completeness test named the missing method rather than leaving clause (b)'s scan
        to die of `AttributeError` inside whichever check happened to run it first
        (`docs/lessons.md` L5.26). Clause (b) needs nothing from a renderer: it registers no
        plugin name, only a way to format a result type already registered elsewhere.
        """
        del result_type, renderer


def distribution_name(example_dir: Path) -> str:
    """This example's own distribution name, read from its own `pyproject.toml`."""
    with (example_dir / "pyproject.toml").open("rb") as handle:
        return typing.cast("str", tomllib.load(handle)["project"]["name"])


def module_and_plugin_names(example_dir: Path) -> tuple[str, tuple[str, ...]]:
    """`(module, plugin names)` for one example pack, the latter read off its real `register()`.

    The module is imported straight off `example_dir/src` — never installed, never a
    workspace member, on `sys.path` only for the duration of this one call — solely so its
    own `register()` can be asked what it registers.
    """
    with (example_dir / "pyproject.toml").open("rb") as handle:
        entry_points = tomllib.load(handle)["project"]["entry-points"]["weft.packs"]
    ((_, target),) = entry_points.items()
    module_name = target.split(":")[0]

    src_dir = example_dir / "src"
    sys.path.insert(0, str(src_dir))
    try:
        module = import_module(module_name)
        registrar = _NameCapturingRegistrar()
        module.register(registrar, module.Settings())
    finally:
        sys.path.remove(str(src_dir))

    return module_name, tuple(registrar.names)


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


def text_files(*roots: Path) -> Iterable[Path]:
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            yield path


def files_naming(names: Iterable[str], *, within: Iterable[Path]) -> list[tuple[Path, str]]:
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


#: The calls whose string arguments are a *name a pack is registered under* — `02` §2's
#: registration surface. A literal reaching one of these is core naming a stranger, whatever the
#: surrounding prose looks like.
_REGISTRATION_CALLS: Final[frozenset[str]] = frozenset(
    {"add", "add_renderer", "add_ext_model", "add_pipeline_resource", "add_contribution"}
)


def structurally_naming(names: Iterable[str], *, within: Iterable[Path]) -> list[tuple[Path, str]]:
    """Every `(file, name)` pair where `file` names an example pack **structurally** — task 6.22.

    Three sources, all read from the AST rather than from the text: an **import** of the pack's
    module, a string literal passed to a **registration call**, and a dotted prefix of either.
    `docs/lessons.md` L5.28 is why this exists beside the substring scan rather than instead of
    it: *"a name-collision check built as a substring search is unsound"* — unsound in both
    directions, which is the half a repair specified from one instance misses (`L6.13`).

    **Where the text scan over-fires**, a name assembled or discussed rather than used: `02` §4
    quotes `weft-graph` as a hypothetical throughout, and a real pack taking that name would turn
    every legitimate quotation into a violation — the second half of L5.28, and the reason
    `examples/weft-example-graph` is *not* called `weft-graph`.

    **Where the text scan under-fires**, and this is the one that matters: a reference the text
    never spells. `import weft_example_graph as g` is caught by both; `importlib.import_module(
    "weft_example" + "_graph")` is caught by neither, but a module aliased through a package
    `__init__`, or a name reaching a registration call from a constant, is exactly what an AST
    walk sees and a substring search does not.
    """
    wanted = frozenset(names)
    modules = {name.replace("-", "_") for name in wanted}
    hits: list[tuple[Path, str]] = []

    for path in within:
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in modules:
                        hits.append((path, alias.name.split(".")[0]))
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in modules:
                    hits.append((path, root))
            elif isinstance(node, ast.Call) and _is_registration(node):
                hits.extend(
                    (path, argument.value)
                    for argument in node.args
                    if isinstance(argument, ast.Constant)
                    and isinstance(argument.value, str)
                    and argument.value in wanted
                )
    return hits


def _is_registration(call: ast.Call) -> bool:
    return isinstance(call.func, ast.Attribute) and call.func.attr in _REGISTRATION_CALLS


def test_no_first_party_file_names_the_example_pack_structurally() -> None:
    """Fitness function 9(b), read from the AST — ledger task **6.22**.

    Runs **beside** the substring scan below, never instead of it: the two fail on different
    things, and `docs/lessons.md` L5.28 recorded the AST half as owed while the text half was
    already in place.
    """
    # Arrange — every out-of-tree example pack's own identity, the same set clause (b) already
    # walks, plus each one's module spelling, since an import names the module and not the
    # distribution.
    names: list[str] = []
    for example_dir in _ALL_EXAMPLE_DIRS:
        names.append(distribution_name(example_dir))
        module_name, plugin_names = module_and_plugin_names(example_dir)
        names.append(module_name)
        names.extend(plugin_names)

    # Act
    hits = structurally_naming(names, within=text_files(PACKAGES_ROOT, TESTING_ROOT))

    # Assert
    assert names, "no example pack identity was read — the walk is wrong, not the tree"
    assert not hits, (
        "core imports an example pack, or registers something under its name:\n  "
        + "\n  ".join(f"{path.relative_to(REPO_ROOT)}: {name!r}" for path, name in hits)
        + "\n\nFitness function 9(b): core must not anticipate a stranger it never imported."
    )


def test_the_structural_check_can_actually_fail(tmp_path: Path) -> None:
    """Task 6.22's own clause: the self-test plants a **real reference**, not a matching word.

    That distinction is the point. A plant like `"the weft-example-graph pack"` in a docstring is
    what the *substring* scan catches and what this one must not; a plant that imports the module
    or registers under its plugin name is what this one catches and the substring scan would too.
    The pair below is what separates them, and it is why both checks run.
    """
    # Arrange
    real = tmp_path / "real.py"
    real.write_text(
        "import weft_example_graph\n"
        "def register(registrar: object) -> None:\n"
        '    registrar.add(object, "example-graph", None)\n',
        encoding="utf-8",
    )
    merely_discussed = tmp_path / "discussed.py"
    merely_discussed.write_text(
        '"""A pack such as weft-example-graph would register its own store here."""\n',
        encoding="utf-8",
    )
    names = ["weft-example-graph", "weft_example_graph", "example-graph"]

    # Act
    caught = structurally_naming(names, within=[real])
    prose = structurally_naming(names, within=[merely_discussed])
    by_text = files_naming(names, within=[merely_discussed])

    # Assert
    assert {name for _, name in caught} == {"weft_example_graph", "example-graph"}, (
        "the structural check must see both the import and the registration literal"
    )
    assert prose == [], "a name merely discussed in a docstring is not a structural reference"
    assert by_text, (
        "the substring scan must still catch the discussed name — that is the half this check "
        "does not replace, and why 6.22 adds to it rather than swapping it out"
    )


def test_no_first_party_file_names_the_example_pack() -> None:
    # Arrange — every out-of-tree example pack's own identity, never a copy of it. Clause
    # (b) reads "any example pack" (`docs/07-extension-cost.md` §2), so the scan walks
    # `_ALL_EXAMPLE_DIRS`, not the single pack this test file started with.
    names: list[str] = []
    for example_dir in _ALL_EXAMPLE_DIRS:
        names.append(distribution_name(example_dir))
        module_name, plugin_names = module_and_plugin_names(example_dir)
        names.append(module_name)
        names.extend(plugin_names)

    # Act
    hits = files_naming(names, within=text_files(PACKAGES_ROOT, TESTING_ROOT))

    # Assert
    assert not hits, (
        "an example pack is named from inside packages/ or testing/, which fitness "
        "function 9(b) forbids — core must not anticipate a stranger it never imported:\n  "
        + "\n  ".join(f"{path.relative_to(REPO_ROOT)}: {name!r}" for path, name in hits)
    )


@pytest.mark.parametrize("example_dir", _ALL_EXAMPLE_DIRS, ids=lambda p: p.name)
def test_the_example_pack_is_outside_the_uv_workspace(
    workspace_config: dict[str, object], example_dir: Path
) -> None:
    # Arrange — the workspace's own two claims on a distribution, read from the root
    # `pyproject.toml`; this example's location and identity, read from where it lives.
    members = str_list_at(table_at(workspace_config, "tool", "uv", "workspace"), "members")
    sources = table_at(workspace_config, "tool", "uv", "sources")
    location = example_dir.relative_to(REPO_ROOT).as_posix()
    distribution = distribution_name(example_dir)

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
    assert distribution not in sources, (
        f"`[tool.uv.sources]` pins {distribution!r}. `docs/07-extension-cost.md` §1 "
        f"names that line as the one packaging cost a *first-party* pack pays and an "
        f"out-of-tree pack does not; taking it here would make the example one of ours."
    )


def test_the_grep_can_actually_fail(tmp_path: Path) -> None:
    # Arrange — plant one of the same three literals `files_naming` looks for.
    planted = tmp_path / "planted.py"
    planted.write_text(f"# pretend core imported {EXAMPLE_MODULE}\n", encoding="utf-8")

    # Act
    hits = files_naming(
        (EXAMPLE_DISTRIBUTION, EXAMPLE_MODULE, EXAMPLE_PLUGIN_NAME), within=text_files(tmp_path)
    )

    # Assert
    assert hits == [(planted, EXAMPLE_MODULE)], (
        "the scanning helper behind clause (b) did not find a literal planted for exactly "
        "this purpose; a clause that stopped being able to fail would pass on a tree that "
        "names the example pack from core, which is the everyday case it exists to catch"
    )


def test_the_double_carries_every_registrar_method() -> None:
    """`_NameCapturingRegistrar` stands in for the real `PackRegistrar`, and a stand-in that
    lags the class it stands in for fails on whichever pack first calls the missing method.

    **This has now happened three times and been noticed once.** `add_pipeline_resource`
    (task 1.11), `add_ext_model` (task 5.2g) and `add_contribution` (task 5.3a) were each
    added to `PackRegistrar` and not to this double; the first two went unnoticed for months
    because no example pack called them, and `add_pipeline_resource` only surfaced when
    `examples/weft-example-graph` shipped a pipeline at task 5.5 — as a crash inside a check
    about something else entirely (`docs/lessons.md` L5.26).

    A double is a second copy of a surface, so the only durable fix is to make the copy's
    incompleteness a failure *here*, where it is diagnosable, rather than wherever it happens
    to be called from. Public methods only: `_`-prefixed names are the real class's own
    business and nothing a pack's `register()` can reach.
    """
    # Arrange
    required = {
        name
        for name in vars(PackRegistrar)
        if not name.startswith("_") and callable(getattr(PackRegistrar, name, None))
    }

    # Act
    missing = required - set(dir(_NameCapturingRegistrar))

    # Assert
    assert not missing, (
        f"`_NameCapturingRegistrar` is missing {sorted(missing)}, which `PackRegistrar` "
        f"declares. A pack's `register()` calling one of those raises `AttributeError` "
        f"inside whichever check happens to run it — add a no-op stand-in here."
    )


def test_no_out_of_workspace_pack_is_installed_in_the_development_environment() -> None:
    """Clause (a)'s other half — the environment this suite runs in, `docs/lessons.md` L5.31.

    Clause (a) says an example pack is installed into a **throwaway** environment, never linked
    into this one, and `test_the_example_pack_is_outside_the_uv_workspace` above proves the
    *declaration* half: no `[tool.uv.workspace] members` glob claims it and no `[tool.uv.sources]`
    pin names it. Nothing proved the *runtime* half, and the two are different facts: a pack can
    be correctly declared out-of-workspace and still be sitting in `.venv` because somebody ran
    `uv pip install` on a wheel to drive the binary by hand.

    **That is not hypothetical and it is not rare.** Closing a task requires both a green
    `poe ci-checks` and a run of the shipped binary from outside the repository, and for an
    example pack those two want opposite states of this environment: the binary run needs the pack
    installed, the suite needs it absent. Left installed it silently changes what `discover()`
    returns for the whole tree — five tests failed that way during Phase 5's task 5.4, and a
    commit was made on the resulting red gate before the cause was understood. Uninstalling
    returned all 1,801 to green with no code change.

    So the cleanup stops being something to remember. The failure names the distribution and the
    command that undoes it, because the person reading it is mid-task and has just lost a gate run.
    """
    # Arrange — every distribution this repository ships from `examples/`, read from its own
    # `pyproject.toml` rather than guessed from a directory name.
    out_of_workspace = {distribution_name(example_dir) for example_dir in _ALL_EXAMPLE_DIRS}

    # Act
    installed = sorted(name for name in out_of_workspace if _is_installed(name))

    # Assert
    assert not installed, (
        f"{installed} is installed into this repository's own `.venv`, and fitness function 9(a) "
        f"requires an example pack to be reachable only from a throwaway environment. It changes "
        f"what `discover()` returns for every test in the tree (`docs/lessons.md` L5.31). Undo it "
        f"with `uv pip uninstall " + " ".join(installed) + "`."
    )


def _is_installed(distribution: str) -> bool:
    """Whether `distribution` has installed metadata in the environment running this suite."""
    try:
        metadata.distribution(distribution)
    except metadata.PackageNotFoundError:
        return False
    return True
