"""Fitness function 1, generalised — ledger task **6.6**.

`docs/09-release.md` §5.2, *Install path*, first item: fitness function 1 holds for **every**
published distribution, not only the kernel — each installs alone into a clean environment and
imports. Fails if any distribution needs the workspace, a path dependency, or an environment
variable to import.

Modelled directly on `scripts/check_kernel_isolated.py`, which has done exactly this for
`weft-kernel` alone since Phase 0. This script generalises it to every distribution
`scripts/publish_set.py` names as published, building all of them into one wheelhouse first so a
sibling requirement (`weft-cli` needing `weft-kernel`, for instance) resolves from that
wheelhouse rather than from an index none of these distributions is published to yet (ledger task
6.13).

Fixed argv, no shell, nothing user-controlled — the two `subprocess.run` calls below carry
`# noqa: S603` with the same justification `scripts/check_kernel_isolated.py` already carries: the
command list is built entirely from constants and validated `Member` fields, never from
unsanitised external input.
"""

import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from publish_set import Member, PublishSetUnreadableError, publishing_members

#: Packs whose module cannot import without an extra, and the extra that supplies it — **G19,
#: 2026-09-09**. Each was its own distribution until that session, so importing it bare worked
#: because the distribution declared its own library. They ship inside `weft-rag` now with the
#: library behind an extra, so importing one from a bare install is *supposed* to fail. Written out
#: rather than derived: this list is what the check compares the tree against, and a list derived
#: from the tree could not disagree with it (`docs/internal/lessons.md` `L5.6`).
EXTRA_BACKED_MODULES: dict[str, str] = {
    "weft_cross_encoder": "cross-encoder",
    "weft_docling": "docling",
    "weft_openai": "openai",
    # **The sixth, and it was missing.** `weft_openai_compatible` imports `weft_openai.embedder`
    # and `weft_openai.llm` at module scope, and both import `openai` at module scope — so it
    # degrades on a bare install exactly as `weft_openai` does, for the same reason and behind
    # the same extra. Phase 20a added the pack and not this line, so the converse clause below
    # reported it as a pack that should have registered and did not, and CI was red on `main`
    # from 2026-09-12 until it was added. `L8.12`'s shape: a new member owes every list keyed on
    # the property it joins, and a pack behind an extra joins this one.
    "weft_openai_compatible": "openai",
    "weft_otel": "otel",
    "weft_pdf": "pdf",
    "weft_qdrant": "qdrant",
}


#: Packs that report `FAILED` on a bare install because a **required setting** is absent, and
#: the field that supplies it — carried repair **R10.6**. This is a different degradation from
#: a missing extra and it is equally correct: `weft-store` and `weft-blob` cannot invent where an
#: operator's data lives, so both refuse rather than guessing (`weft_blob.Settings.root`'s own
#: docstring follows `[packs.store] dsn`'s precedent). Written out rather than derived, for
#: `EXTRA_BACKED_MODULES`' reason: a list derived from the tree could not disagree with it.
SETTINGS_BACKED_PACKS: dict[str, str] = {
    "blob": "root",
    "store": "dsn",
}

#: Packs that report `PARTIAL` on a bare install because they registered, and then declared one
#: **surface** unavailable and said why — carried repair **R10.6**. `weft_eval` registers
#: twenty-eight plugins and declares `bertscore` unavailable without the `bertscore` extra,
#: which is fitness function 5's second half working exactly as written. A pack in this list is
#: healthy; it is here so the check can tell it apart from one that failed.
UNAVAILABLE_SURFACE_PACKS: dict[str, str] = {
    "eval": "bertscore",
}


def _build(name: str, out_dir: Path) -> subprocess.CompletedProcess[str]:
    command = ["uv", "build", "--package", name, "--out-dir", str(out_dir)]
    # Fixed argv, no shell, nothing user-controlled.
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


def _install_and_check(member: Member, wheelhouse: Path) -> subprocess.CompletedProcess[str]:
    """Install one distribution alone into a clean environment and import everything it ships.

    **What this covers for the fourteen packs inside `weft-rag`, and how it is weaker.** Task 6.6
    generalised fitness function 1 to every published distribution: each installs alone and
    imports. Fourteen of them stopped being separately installable on 2026-09-05, so what they
    get instead is this — every module `weft-rag` ships, imported from `weft-rag` installed
    alone. That still catches an import that needs the workspace, a path dependency or an
    undeclared third-party package, which is what the check was for. What it can no longer catch
    is one pack depending on another *without declaring it*, because there is no longer a
    declaration between them to omit: `weft_generate` importing `weft_retrieve` is now an
    intra-wheel import and always resolves. That is a real loss of coverage and it is stated
    here rather than counted as the same check.
    """
    bare = [module for module in member.modules if module not in EXTRA_BACKED_MODULES]
    bare += [m for m in PUBLISHED_SUBMODULES.get(member.name, ()) if m.split(".")[0] in bare]
    if not member.modules:
        probe = "print('no module to import — ships no code')"
    else:
        imports = "; ".join(f"import {module}" for module in bare)
        probe = f"{imports}; print('{member.name} imports standalone ({len(bare)})')"

    command = [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        "--find-links",
        str(wheelhouse),
        "--with",
        member.name,
        "python",
        "-c",
        probe,
    ]

    # Fixed argv, no shell, nothing user-controlled.
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


def pack_of(module: str) -> str:
    """`weft_openai` -> `openai`, `weft_openai_compatible` -> `openai-compatible`.

    **The pack name a module's `weft.packs` entry point declares, and it is not the extra.**
    `EXTRA_BACKED_MODULES`' value is the *extra* — `weft_openai_compatible` is behind `[openai]`,
    the same extra `weft_openai` is behind — and the probe below needs the *pack*. Those two
    strings coincide for every single-word pack and diverge for the first multi-word one, so
    using the extra as the pack name worked for five entries and silently dropped the sixth:
    the set deduplicated to `{'openai'}` and `openai-compatible` was never declared, which is
    what kept CI red after that entry was added (`docs/internal/lessons.md` `L17.19`'s shape, a
    second time in one day).

    A Python module is underscored and a pack name is hyphenated; that is the whole convention,
    and `tests/architecture/test_isolated_installs.py` reads it from here rather than keeping a
    second copy.
    """
    return module.removeprefix("weft_").replace("_", "-")


#: Submodules a *caller outside this repository* imports by name, which importing the package root
#: does not reach — so they need their own probe here or nothing checks them on a bare install.
#:
#: **`docs/internal/lessons.md` `L21.1`, and it cost this twice.** Task `26.4` published
#: `weft_store.conformance`, whose corpus attached `weft_pdf`'s `PdfPages`. A pack's `__init__` is
#: where `register()` lives, so it imports every plugin the pack registers and therefore every
#: driver those need — `weft_pdf` reaches `pdfplumber`, behind `[pdf]`. Neither `from weft_pdf
#: import PdfPages` nor `from weft_pdf.document import PdfPages` survives a plain install, because
#: importing a submodule executes the package. Nothing in this repository could have caught it:
#: every test runs with `[all]`, and fitness function 1 installs the *kernel* alone rather than
#: `weft-rag`.
#:
#: The first fix was wrong too, which is why the rule is mechanical now rather than remembered: a
#: probe that tried both spellings in one interpreter reported the second as fine, because the
#: failed package import had left a partial `weft_pdf` in `sys.modules` and the next attempt sailed
#: past it. This script gets it right for free — one fresh environment and one fresh interpreter.
PUBLISHED_SUBMODULES: Final[Mapping[str, tuple[str, ...]]] = {
    "weft-rag": ("weft_store.conformance", "weft_store.memory"),
}


def _degradation_probe(member: Member, wheelhouse: Path) -> subprocess.CompletedProcess[str] | None:
    """Install `member` bare and check every extra-backed pack it ships reports `FAILED`.

    **The clause G19 turns on, checked rather than argued.** That session folded six add-ons into
    this wheel on the reading that an extra makes a dependency declinable just as a separate
    distribution did. That is only true if a pack whose library is absent *degrades* — names itself
    and what is missing through `weft plugins doctor` — rather than crashing the run. The mechanism
    exists by design (`weft_kernel.discovery`: "a pack's import can raise anything; that is FAILED,
    not a crash"), and a mechanism that exists is not one that fired (`L5.15`), so this runs it.

    Returns `None` for a distribution shipping no extra-backed pack, which is every one but
    `weft-rag`.
    """
    expected = sorted(m for m in member.modules if m in EXTRA_BACKED_MODULES)
    if not expected:
        return None

    packs = ", ".join(repr(pack_of(m)) for m in expected)
    probe = (
        "from weft_kernel.discovery import discover, PackStatus\n"
        "from weft_kernel.registry import Registry\n"
        f"expected = {{{packs}}}\n"
        "reports = {r.pack: r for r in discover(Registry())}\n"
        "missing = sorted(expected - set(reports))\n"
        "assert not missing, f'no report at all for {missing} — the pack vanished rather than "
        "failing'\n"
        "wrong = sorted(p for p in expected if reports[p].status is not PackStatus.FAILED)\n"
        "assert not wrong, f'{wrong} did not report FAILED without their extra'\n"
        "silent = sorted(p for p in expected if not (reports[p].reason or '').strip())\n"
        "assert not silent, f'{silent} reported FAILED with no reason — an operator reading "
        "doctor learns nothing'\n"
        # **Carried repair `R10.6`, and the clause that was missing.** Everything above inspects the
        # five packs expected to fail. Nothing asserted the converse — that the rest *registered* —
        # and `docs/internal/lessons.md` `L10.41` is precisely that gap: `weft-openai` imported
        # cleanly on a clean install and registered **zero** of its three plugins, because it used
        # Pillow without declaring it. An import that succeeds is not a pack that registered, and
        # until now this check watched only the import. Three categories of legitimate degradation,
        # each named above with its reason; every pack outside them must be `ACTIVE`. Measured when
        # this was written: 13 of 21.
        "degraded = expected | "
        + repr(set(SETTINGS_BACKED_PACKS))
        + " | "
        + repr(set(UNAVAILABLE_SURFACE_PACKS))
        + "\n"
        "should_run = sorted(p for p in reports if p not in degraded)\n"
        "assert should_run, 'no pack was expected to be ACTIVE, so the clause below asserts "
        "nothing'\n"
        "inert = sorted(p for p in should_run if reports[p].status is not PackStatus.ACTIVE)\n"
        "assert not inert, f'{inert} did not register on a bare install, and none of them is a "
        "declared degradation — an import that succeeds is not a pack that registered'\n"
        "print(f'registered on a bare install: {len(should_run)} pack(s); degraded by design: "
        "{sorted(degraded)}')\n"
    )
    command = [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        "--find-links",
        str(wheelhouse),
        "--with",
        member.name,
        "python",
        "-c",
        probe,
    ]
    # Fixed argv, no shell, nothing user-controlled. No `--no-index`: the wheelhouse holds this
    # repository's own wheels and nothing else, so blocking the index would fail on `ftfy` long
    # before reaching the question this probe asks.
    return subprocess.run(  # noqa: S603
        command, capture_output=True, text=True, check=False
    )


EXAMPLE_APP_DIR: Final[Path] = Path(__file__).resolve().parents[1] / "examples" / "weft-example-app"

#: The bridge this script supplies on the application's behalf. It is *here*, in a command
#: string, rather than in `app.py`, because fitness function 7(a) asserts there is exactly one
#: `asyncio.run` in this tree and `01` → *Fitness functions* states that as settled text. An
#: example application that carried its own would be a second one, and adding a waiver for it
#: would be exactly the proviso `phase-step` refuses in place of reopening the decision. The
#: shape is also the truer one: the realistic embedding already has a loop.
_BRIDGE: Final[str] = (
    "import asyncio, sys; sys.path.insert(0, {directory!r}); import app; asyncio.run(app.main())"
)

#: What `examples/weft-example-app/app.py` exits when `WEFT_DATABASE_URL` is unset. It is a
#: distinct code rather than `1` so this script can tell *the wheel does not work* from *this
#: machine has no Postgres* — the first is a failure, the second is an environment, and a check
#: that conflated them would be green on a laptop and meaningless in CI, or the reverse.
NO_DATABASE: Final[int] = 2


def _run_example_app(wheelhouse: Path) -> subprocess.CompletedProcess[str]:
    """Install the two published wheels alone and run an application that extends nothing.

    **The other half of fitness function 9, and the half no example covered until task 24.3.**
    Every other directory under `examples/` is a pack: it registers a plugin through a
    `weft.packs` entry point and proves that a capability can be *added* from outside. This
    proves that Weft can be *consumed* from outside — that somebody who writes no plugin, declares
    no entry point and is never seen by the registry can install the wheel and drive it. The two
    are different claims about the same boundary and only one of them was checked.

    It is run from the wheelhouse rather than from the checkout deliberately (`L7.6`): an editable
    install answers a packaging question differently from a real one, and the packaging question
    is the whole subject here.
    """
    command = [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        "--find-links",
        str(wheelhouse),
        "--with",
        "weft-rag",
        "--with",
        "weft-kernel",
        "python",
        "-c",
        _BRIDGE.format(directory=str(EXAMPLE_APP_DIR)),
    ]

    # Fixed argv, no shell, nothing user-controlled.
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


def _report_example_app(wheelhouse: Path) -> list[str]:
    """Run the example application and say which of its three outcomes happened.

    Extracted rather than inlined into `main`: it is three branches, and `main` was one under
    ruff's complexity ceiling before this task added them (`implementer-brief.md` check 5 — the
    choice between extracting and writing `# noqa: C901` is one of them visible in a diff).
    """
    app = _run_example_app(wheelhouse)
    sys.stdout.write(app.stdout)
    sys.stderr.write(app.stderr)
    if app.returncode == 0:
        sys.stdout.write(
            "weft-example-app: an application that is not a pack installed the published "
            "wheels and ran to an answer.\n"
        )
        return []
    if app.returncode == NO_DATABASE:
        sys.stdout.write(
            "weft-example-app: installed and assembled from the wheels; the answer half needs "
            "WEFT_DATABASE_URL and this environment has none. Not a failure, and not a pass "
            "either — say so rather than reporting one of them.\n"
        )
        return []
    sys.stderr.write(
        "\nweft-example-app does not run against the published wheels. An application that "
        "extends nothing is the consumer side of fitness function 9, and it is the one a reader "
        "of the manual actually is.\n"
    )
    return ["weft-example-app"]


def _build_all(members: tuple[Member, ...], wheelhouse: Path, failures: list[str]) -> list[Member]:
    built_ok: list[Member] = []
    for member in members:
        built = _build(member.name, wheelhouse)
        sys.stdout.write(built.stdout)
        sys.stderr.write(built.stderr)
        if built.returncode != 0:
            sys.stderr.write(
                f"\n{member.name} could not be built. It needs the workspace, a path "
                f"dependency, or an environment variable that a clean build does not have.\n"
            )
            failures.append(member.name)
            continue
        built_ok.append(member)
    return built_ok


def _report_imported(member: Member) -> None:
    if not member.modules:
        sys.stdout.write(f"{member.name}: installed alone, ships no code — nothing to import.\n")
        return
    bare = [m for m in member.modules if m not in EXTRA_BACKED_MODULES]
    deferred = [m for m in member.modules if m in EXTRA_BACKED_MODULES]
    sys.stdout.write(f"{member.name}: installs alone and imports {', '.join(bare)}.\n")
    if deferred:
        extras = ", ".join(f"{m} (needs [{EXTRA_BACKED_MODULES[m]}])" for m in deferred)
        sys.stdout.write(
            f"{member.name}: not imported bare, by design — {extras}. A bare "
            f"install leaves each present and unimportable, and discovery folds "
            f"that into a FAILED pack report rather than a crash; the probe below "
            f"is what checks it rather than assuming it.\n"
        )


def _install_all(built_ok: list[Member], wheelhouse: Path, failures: list[str]) -> None:
    for member in built_ok:
        checked = _install_and_check(member, wheelhouse)
        sys.stdout.write(checked.stdout)
        sys.stderr.write(checked.stderr)

        if checked.returncode == 0:
            _report_imported(member)
        else:
            sys.stderr.write(
                f"\n{member.name} does not install and import in a clean environment. It "
                f"needs the workspace, a path dependency, or an environment variable to "
                f"import — see G1, The kernel boundary.\n"
            )
            failures.append(member.name)


def _probe_all(built_ok: list[Member], wheelhouse: Path, failures: list[str]) -> None:
    for member in built_ok:
        degraded = _degradation_probe(member, wheelhouse)
        if degraded is None:
            continue
        sys.stdout.write(degraded.stdout)
        sys.stderr.write(degraded.stderr)
        if degraded.returncode != 0:
            sys.stderr.write(
                f"\n{member.name}: a pack whose extra is absent did not degrade. G19 turns on "
                f"this being true — the code ships and only the library is optional — so a "
                f"pack that crashes discovery instead of reporting FAILED takes the whole run "
                f"down for a capability the operator never asked for.\n"
            )
            failures.append(f"{member.name} (degradation)")


def main() -> int:
    """Build every published distribution, then install and import each one alone.

    Returns:
        0 when every distribution builds, imports and degrades as designed; 1 otherwise.
    """
    try:
        members = publishing_members()
    except PublishSetUnreadableError as error:
        sys.stderr.write(f"could not enumerate the published set: {error}\n")
        return 1

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        wheelhouse = Path(tmp_dir)

        # Every member is built into the one wheelhouse *before* any member is installed — a
        # sibling requirement (`weft-chunk` needing `weft-kernel`, for instance) must be able to
        # resolve against a wheel that already exists there, regardless of where either name
        # falls in sorted order.
        built_ok = _build_all(members, wheelhouse, failures)
        _install_all(built_ok, wheelhouse, failures)
        _probe_all(built_ok, wheelhouse, failures)
        failures.extend(_report_example_app(wheelhouse))

    if failures:
        sys.stderr.write(f"\nfailed: {', '.join(sorted(failures))}\n")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
