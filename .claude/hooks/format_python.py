"""PostToolUse: format and auto-fix a Python file the moment it is written.

**Two writing paths, not one — `docs/internal/lessons.md` `L18.1`.** This hook matched
`Edit|Write` alone for its whole life, while `CLAUDE.md` → *Automation* opened by saying "Python
files are formatted and auto-fixed the moment they are written". A file written through a `Bash`
heredoc — `cat >> x.py <<'EOF'` — is written and was not formatted, and the sentence was false for
whichever path a session happened to prefer. Task 24.0 wrote four test files that way, staged them
unformatted, and a dispatched implementer spent part of its one turn proving the resulting diff was
not its own. So this also answers `Bash`, where it cannot know which files a command touched and
therefore asks git: every changed or untracked `.py` file under the repository, formatted the same
way a directly-written one is. A hook's guarantee is scoped to the matchers it declares, and a
sentence claiming *whenever a file is written* is a claim about every way one can be.

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

    # Resolved rather than looked up per call: a hook that runs whichever `uv`
    # happens to be on PATH is a hook whose behaviour depends on the shell that
    # launched the session. Absent, it simply does nothing and the gate catches it.
    uv = shutil.which("uv")
    if uv is None:
        return 0

    if payload.get("tool_name") == "Bash":
        targets = _changed_python_files()
    else:
        raw = payload.get("tool_input", {}).get("file_path")
        if not raw or not raw.endswith(".py"):
            return 0
        target = Path(raw).expanduser().resolve()
        targets = [target] if target.is_file() and REPO in target.parents else []

    for target in targets:
        for arguments in (["format"], ["check", "--fix", "--unfixable", "F401", "--quiet"]):
            # Fixed argv, no shell, absolute executable, paths resolved above.
            subprocess.run(  # noqa: S603
                [uv, "run", "ruff", *arguments, str(target)],
                cwd=REPO,
                capture_output=True,
                check=False,
            )

    return 0


def _changed_python_files():
    """Every changed or untracked `.py` file under the repository, from git.

    A `PostToolUse` on `Bash` is handed a command string, not a file list, and parsing one to
    guess what it wrote would be wrong the first time somebody used a variable. git already knows
    what moved, which is both exact and cheap — and it is deliberately the *working tree*, not the
    index, because the case this exists for is a file written and not yet staged.
    """
    git = shutil.which("git")
    if git is None:
        return []
    # Fixed argv, no shell, absolute executable.
    result = subprocess.run(  # noqa: S603
        [git, "status", "--porcelain", "--untracked-files=all"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    found = []
    for line in result.stdout.splitlines():
        name = line[3:].split(" -> ")[-1].strip().strip('"')
        if not name.endswith(".py"):
            continue
        path = (REPO / name).resolve()
        if path.is_file() and REPO in path.parents:
            found.append(path)
    return found


if __name__ == "__main__":
    raise SystemExit(main())
