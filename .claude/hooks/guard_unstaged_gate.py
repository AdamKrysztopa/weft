"""PreToolUse guard: the canonical gate runs only over the files the next commit will carry.

`docs/internal/lessons.md` `L26.8` (`R32.6`), the third instance of `L11.34` and `L8.10`. The
architecture suite walks `git ls-files`, so a new file left untracked is invisible to it: `32.10`'s
experiment documents passed a local gate and failed FF17 in CI once committed. Two red CI runs in
Phase 32 were this shape.

Refused: `poe ci-checks`, `poe ci-no-tests`, `poe arch` or a pytest run over `tests/architecture`
while an untracked, non-ignored file sits under a top-level directory the repository tracks.
Root-level untracked files are not refused — no fitness function walks the root alone.
Exit 2 with the paths on stderr blocks. Runs under bare `python3` (3.9).
"""

import json
import re
import shutil
import subprocess
import sys

_RUNS_GATE = re.compile(
    r"(^|[;&|(]\s*|\s)(poe\s+(ci-checks|ci-no-tests|arch)\b|pytest\b[^;&|]*tests/architecture)"
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


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = strip_heredocs(payload.get("tool_input", {}).get("command", ""))
    if not _RUNS_GATE.search(command):
        return 0
    missing = unstaged_under_tracked_roots(payload.get("cwd") or ".")
    if not missing:
        return 0
    shown = "\n".join("  " + path for path in missing[:20])
    more = "" if len(missing) <= 20 else "\n  … and {} more".format(len(missing) - 20)
    sys.stderr.write(
        "Refused: the gate walks `git ls-files`, and these files are untracked, so it would\n"
        "pass without seeing them and CI would fail once they are committed (L26.8, R32.6):\n"
        + shown
        + more
        + "\n`git add` them (or add them to .gitignore if they are not the tree's), then re-run.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
