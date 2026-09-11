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
from pathlib import Path

from publish_set import Member, PublishSetUnreadableError, publishing_members

#: Packs whose module cannot import without an extra, and the extra that supplies it — **G19,
#: 2026-09-09**. Each was its own distribution until that session, so importing it bare worked
#: because the distribution declared its own library. They ship inside `weft-rag` now with the
#: library behind an extra, so importing one from a bare install is *supposed* to fail. Written out
#: rather than derived: this list is what the check compares the tree against, and a list derived
#: from the tree could not disagree with it (`docs/internal/lessons.md` `L5.6`).
EXTRA_BACKED_MODULES: dict[str, str] = {
    "weft_docling": "docling",
    "weft_openai": "openai",
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

    packs = ", ".join(repr(EXTRA_BACKED_MODULES[m]) for m in expected)
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


def main() -> int:
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

        for member in built_ok:
            checked = _install_and_check(member, wheelhouse)
            sys.stdout.write(checked.stdout)
            sys.stderr.write(checked.stderr)

            if checked.returncode == 0:
                if not member.modules:
                    sys.stdout.write(
                        f"{member.name}: installed alone, ships no code — nothing to import.\n"
                    )
                else:
                    bare = [m for m in member.modules if m not in EXTRA_BACKED_MODULES]
                    deferred = [m for m in member.modules if m in EXTRA_BACKED_MODULES]
                    sys.stdout.write(
                        f"{member.name}: installs alone and imports {', '.join(bare)}.\n"
                    )
                    if deferred:
                        extras = ", ".join(
                            f"{m} (needs [{EXTRA_BACKED_MODULES[m]}])" for m in deferred
                        )
                        sys.stdout.write(
                            f"{member.name}: not imported bare, by design — {extras}. A bare "
                            f"install leaves each present and unimportable, and discovery folds "
                            f"that into a FAILED pack report rather than a crash; the probe below "
                            f"is what checks it rather than assuming it.\n"
                        )
            else:
                sys.stderr.write(
                    f"\n{member.name} does not install and import in a clean environment. It "
                    f"needs the workspace, a path dependency, or an environment variable to "
                    f"import — see G1, The kernel boundary.\n"
                )
                failures.append(member.name)

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

    if failures:
        sys.stderr.write(f"\nfailed: {', '.join(sorted(failures))}\n")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
