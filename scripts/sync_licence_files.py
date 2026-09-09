"""Copy the root `LICENSE` and `NOTICE` into every publishing distribution — `poe licence-sync`.

**Why nine real copies rather than one file.** `tests/architecture/test_release_licensing.py`'s
docstring carries the measurements: hatchling cannot `force-include` a path outside a distribution's
own directory, and PEP 639's `license-files` resolves relative to that directory, so the root files
are unreachable from a per-distribution build. Symlinking them was measured on 2026-09-09 and is
worse than useless — the sdist carries a symlinked entry at size 0 and the wheel built from it
carries no licence at all, while every check in this repository stays green because `is_file()` and
`read_bytes()` both follow the link (`docs/lessons.md` `L11.8`).

**So the duplication is load-bearing, and this script is what makes it cheap.** Editing the root
`NOTICE` was a nine-file edit done by hand, whose only feedback was a full `poe ci-checks` run some
ten minutes later. Now it is one edit and one command.

**This is deliberately not part of `ci-checks`.** The gate's job is to *fail* when the copies have
drifted; a gate that silently repaired them would convert a check into a workflow and the drift
would stop being visible in a diff — the same reason a fitness function's waiver is an entry
somebody has to write rather than something the run tops up. Run this, then read the diff.

Exits non-zero and writes nothing when the expected members cannot be found, because a sync that
quietly copies to zero directories reports success for having done nothing.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LICENCE_FILES = ("LICENSE", "NOTICE")


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from publish_set import publishing_members

    members = publishing_members()
    if not members:
        print("no publishing member was found — nothing was copied", file=sys.stderr)
        return 1

    originals = {name: REPO_ROOT / name for name in LICENCE_FILES}
    for path in originals.values():
        if not path.is_file() or path.is_symlink():
            print(f"{path} is not a regular file — refusing to propagate it", file=sys.stderr)
            return 1

    changed: list[str] = []
    for member in members:
        for name, original in originals.items():
            target = member.directory / name
            if target.is_symlink():
                print(f"{target} is a link, not a file — remove it by hand", file=sys.stderr)
                return 1
            if not target.is_file() or target.read_bytes() != original.read_bytes():
                shutil.copyfile(original, target)
                changed.append(f"{member.name}/{name}")

    print(
        f"{len(members)} distributions checked; "
        + (f"updated {len(changed)}: {', '.join(changed)}" if changed else "all already in step")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
