"""PreToolUse guard: refuse a `git push` while tracked files differ from HEAD.

`docs/internal/lessons.md` `L28.58`: a batch was gated whole, split into commits by selecting
hunks, and pushed before `git status` was read — two hunks matched no selector, so the pushed
HEAD was a tree no gate had run.

The tree is judged as it stands before the command runs, even when the same command commits
first: a chained `git add -p … && git commit && git push` is the instance's own shape.
Deliberately allowed: untracked files (scratch and ignored `docs/internal/` live beside every
push), `--dry-run`/`-n` (pushes nothing), and a directory git cannot read (not a repository,
so there is no HEAD to differ from).

Exit 2 with the paths on stderr blocks. Runs under bare `python3` (3.9).
"""

import json
import re
import shlex
import sys
from pathlib import Path

from guard_unstaged_gate import _git_lines, strip_heredocs

_CONTINUATION = re.compile(r"\\\n")
_PUSH = re.compile(r"(?:^|[\n;&|(])\s*git\s+((?:-[cC]\s+\S+\s+)*)push\b([^\n;&|()]*)")
_DIRECTORY = re.compile(r"-C\s+(\S+)")


def pushes(command, cwd):
    """The directories each real (non-dry-run) `git push` in `command` would push from."""
    executable = _CONTINUATION.sub(" ", strip_heredocs(command))
    found = []
    for match in _PUSH.finditer(executable):
        try:
            words = shlex.split(match.group(2))
        except ValueError:
            words = match.group(2).split()
        if "--dry-run" in words or "-n" in words:
            continue
        directory = Path(cwd)
        for named in _DIRECTORY.findall(match.group(1)):
            directory = directory / Path(named.strip("'\"")).expanduser()
        found.append(str(directory))
    return found


def modified_tracked(cwd):
    """Tracked paths that differ from HEAD, or None when git cannot answer here."""
    if not Path(cwd).is_dir():
        return None
    return _git_lines(cwd, "diff", "--name-only", "HEAD", "--")


def main():
    """Refuse a `Bash` call that pushes from a tree with tracked changes not in HEAD.

    Returns:
        2 when the command is refused, with the paths on stderr; 0 otherwise.
    """
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        return 0
    cwd = payload.get("cwd") or str(Path.cwd())
    for directory in pushes(command, cwd):
        dirty = modified_tracked(directory)
        if not dirty:
            continue
        shown = "\n".join("  " + path for path in dirty[:20])
        more = "" if len(dirty) <= 20 else "\n  … and {} more".format(len(dirty) - 20)
        sys.stderr.write(
            "Refused: tracked files differ from HEAD in " + directory + ", so the commit you\n"
            "would push is not the tree the gate ran over (docs/internal/lessons.md L28.58):\n"
            + shown
            + more
            + "\nCommit or drop those leftover hunks, re-run the gate over the tree you will"
            " push,\nthen push in a command of its own — this hook reads the tree before the"
            " command\nruns, so a commit chained in front of the push has not happened yet.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
