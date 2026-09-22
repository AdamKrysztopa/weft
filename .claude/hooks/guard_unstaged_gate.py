"""PreToolUse guard: the canonical gate runs only over the files the next commit will carry.

`docs/internal/lessons.md` `L26.8` (`R32.6`), the third instance of `L11.34` and `L8.10`. The
architecture suite walks `git ls-files`, so a new file left untracked is invisible to it: `32.10`'s
experiment documents passed a local gate and failed FF17 in CI once committed. Two red CI runs in
Phase 32 were this shape.

Refused: `poe ci-checks`, `poe ci-no-tests`, `poe arch` or a pytest run over `tests/architecture`
while an untracked, non-ignored file sits under a top-level directory the repository tracks.
Root-level untracked files are not refused — no fitness function walks the root alone.
**And the full gate is refused while a dispatched agent's worktree is still locked** (`L28.21`,
recurring `L24.3`). A worktree is its own checkout, not its own container: an agent's suite and
this one share Postgres and Qdrant, and a `unit` directory is no promise that a test stays off
them. Both times this cost a phase, the result read as a defect in the change under test.

Exit 2 with the paths on stderr blocks. Runs under bare `python3` (3.9).
"""

import json
import os
import re
import shutil
import subprocess
import sys

_RUNS_GATE = re.compile(
    r"(^|[;&|(]\s*|\s)(poe\s+(ci-checks|ci-no-tests|arch)\b|pytest\b[^;&|]*tests/architecture)"
)
#: A named test file is allowed: the refusal is for the runs that sweep a directory, which is how
#: the one pgvector test under `tests/unit/weft_store` reached the container.
_RUNS_CONTAINER_SUITE = re.compile(
    r"(^|[;&|(]\s*|\s)(poe\s+(ci-checks|test)\b"
    r"|pytest\b[^;&|]*tests/integration"
    r"|pytest\b[^;&|]*tests/unit(/[\w-]+)*/?(?=\s|$|[;&|)]))"
)
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(command):
    kept = []
    pending = []
    for line in command.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        kept.append(line)
        pending.extend(match.group(2) for match in _HEREDOC.finditer(line))
    return "\n".join(kept)


def _git_lines(cwd, *args):
    git = shutil.which("git")
    if git is None:
        return None
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [git, *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        return None
    return [line for line in done.stdout.split("\n") if line]


def unstaged_under_tracked_roots(cwd):
    tracked = _git_lines(cwd, "ls-files")
    untracked = _git_lines(cwd, "ls-files", "--others", "--exclude-standard")
    if tracked is None or untracked is None:
        return []
    roots = {path.split("/", 1)[0] for path in tracked if "/" in path}
    return [path for path in untracked if "/" in path and path.split("/", 1)[0] in roots]


def locked_agent_worktrees(cwd):
    lines = _git_lines(cwd, "worktree", "list", "--porcelain")
    if lines is None:
        return []
    locked = []
    current = None
    for line in lines:
        if line.startswith("worktree "):
            current = line[len("worktree ") :]
        elif line.startswith("locked") and current and "/agent-" in current:
            locked.append(current)
    # An agent running inside its own worktree is the one entitled to the container (L24.3).
    here = os.path.realpath(cwd)
    return [
        path
        for path in locked
        if here != os.path.realpath(path) and not here.startswith(os.path.realpath(path) + os.sep)
    ]


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = strip_heredocs(payload.get("tool_input", {}).get("command", ""))
    cwd = payload.get("cwd") or "."
    if _RUNS_CONTAINER_SUITE.search(command):
        busy = locked_agent_worktrees(cwd)
        if busy:
            sys.stderr.write(
                "Refused: a dispatched agent is still running in "
                + ", ".join(busy)
                + ",\nand its suite shares this Postgres and Qdrant (L28.21, L24.3). Wait for its\n"
                "completion notice, bring its diff back, remove the worktree, then run the gate.\n"
            )
            return 2
    if not _RUNS_GATE.search(command):
        return 0
    missing = unstaged_under_tracked_roots(cwd)
    if not missing:
        return 0
    shown = "\n".join("  " + path for path in missing[:20])
    more = "" if len(missing) <= 20 else "\n  … and {} more".format(len(missing) - 20)
    sys.stderr.write(
        "Refused: the gate walks `git ls-files`, and these files are untracked, so it would\n"
        "pass without seeing them and CI would fail once they are committed (L26.8, R32.6):\n"
        + shown
        + more
        + "\n`git add` them in a command of its own — this hook reads the tree before the command\n"
        "runs, so a `git add` chained in front of the gate has not happened yet — then re-run.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
