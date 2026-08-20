"""Warn when running the shipped binary leaves an artefact in the repository root.

`PostToolUse`, after `Bash`. Phase 3's own repairs were all found by running `weft`
rather than by reading code — `phase-step` → *Finish* now requires it — and `weft init`
is exactly the command that writes a `weft.toml` into whatever directory you happened
to be in. One was left at the repository root during Phase 3 and had to be chased down
afterwards, which is the whole reason this file exists.

**It warns; it never deletes.** An artefact might be deliberate, and a hook that removed
a file someone meant to keep would be worse than the mess it tidied. For the same
reason `weft.toml` is deliberately *not* gitignored: making it invisible hides the
mistake instead of surfacing it, which is the failure `docs/README.md` opens by
describing.

Existence at the root is the whole test, and no `git` call is needed to decide it: this
repository ships `weft.toml.example` and never a `weft.toml`, so one appearing here is
always someone's working directory being wrong.
"""

import json
import sys
from pathlib import Path

#: Artefacts a verification run legitimately produces, which belong in a project
#: directory and never in this repository. Extend only with files that are never
#: wanted here — anything ambiguous belongs in `.gitignore` or in review, not in a hook.
STRAY_NAMES = ("weft.toml",)


def main() -> None:
    root = Path(sys.argv[0]).resolve().parents[2]
    stray = [name for name in STRAY_NAMES if (root / name).exists()]
    if not stray:
        return

    listed = ", ".join(stray)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"Untracked {listed} at the repository root. Running `weft init` writes "
                        "one into the current directory — run it from a temporary directory "
                        "instead, and delete this before committing. Do not gitignore it; that "
                        "hides the mistake rather than fixing it."
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    main()
