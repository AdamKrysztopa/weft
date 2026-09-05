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
    if not member.modules:
        probe = "print('no module to import — ships no code')"
    else:
        imports = "; ".join(f"import {module}" for module in member.modules)
        probe = f"{imports}; print('{member.name} imports standalone ({len(member.modules)})')"

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
                    named = ", ".join(member.modules)
                    sys.stdout.write(f"{member.name}: installs alone and imports {named}.\n")
            else:
                sys.stderr.write(
                    f"\n{member.name} does not install and import in a clean environment. It "
                    f"needs the workspace, a path dependency, or an environment variable to "
                    f"import — see G1, The kernel boundary.\n"
                )
                failures.append(member.name)

    if failures:
        sys.stderr.write(f"\nfailed: {', '.join(sorted(failures))}\n")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
