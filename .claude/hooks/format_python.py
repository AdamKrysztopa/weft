"""PostToolUse: format and auto-fix a Python file the moment it is written.

Ruff runs in the canonical gate anyway, so this changes nothing about what is
enforced — it changes *when* you find out. Without it, a formatting nit or an
auto-fixable lint surfaces minutes later at `poe ci-checks`, after the reasoning
that produced the file is gone, and each round trip costs a full gate run.

Deliberately limited to formatting and fixes ruff can apply itself. Type
checking and the architecture checks stay in the gate: they are slower, they are
whole-tree properties rather than file properties, and a check that runs on every
keystroke is a check people learn to ignore.

Never blocks. A file that cannot be formatted is a file with a syntax error, and
the gate will say so more clearly than a hook can.

**`F401` is reported and never fixed here — Phase 5's `lessons.md` L5.17.** An
unused-import fix is the one auto-fix that cannot tell *"no usage yet"* from *"no
usage ever"*, and mid-edit the two are the same file. Introducing an import in one
edit and its first reference in the next is the natural order — a docstring or an
annotation is written before the call site — and this hook silently deleted the
import in four files across one task, surfacing minutes later as `F821 Undefined
name` with nothing in the edit's own result to show what happened.

Nothing is weakened by the exemption: `F401` is still selected, still reported by
this hook, and still fails `poe ci-checks`, so a genuinely unused import is caught
exactly as before. Only the silent deletion stops — which is the difference between
a hook that tells you something and a hook that edits your file behind you.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    raw = payload.get("tool_input", {}).get("file_path")
    if not raw or not raw.endswith(".py"):
        return 0

    target = Path(raw).expanduser().resolve()
    if not target.is_file() or REPO not in target.parents:
        return 0

    # Resolved rather than looked up per call: a hook that runs whichever `uv`
    # happens to be on PATH is a hook whose behaviour depends on the shell that
    # launched the session. Absent, it simply does nothing and the gate catches it.
    uv = shutil.which("uv")
    if uv is None:
        return 0

    for arguments in (["format"], ["check", "--fix", "--unfixable", "F401", "--quiet"]):
        # Fixed argv, no shell, absolute executable, path resolved above.
        subprocess.run(  # noqa: S603
            [uv, "run", "ruff", *arguments, str(target)],
            cwd=REPO,
            capture_output=True,
            check=False,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
