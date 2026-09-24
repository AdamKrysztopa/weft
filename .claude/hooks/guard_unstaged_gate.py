r"""PreToolUse guard: the canonical gate runs only over the files the next commit will carry.

`docs/internal/lessons.md` `L26.8` (`R32.6`), the third instance of `L11.34` and `L8.10`. The
architecture suite walks `git ls-files`, so a new file left untracked is invisible to it: `32.10`'s
experiment documents passed a local gate and failed FF17 in CI once committed. Two red CI runs in
Phase 32 were this shape.

Refused: `poe ci-checks`, `poe ci-task`, `poe ci-no-tests`, `poe arch` or a pytest run over
`tests/architecture` while an untracked, non-ignored file sits under a top-level directory the
repository tracks. Root-level untracked files are not refused — no fitness function walks the
root alone.
**And the full gate is refused while a dispatched agent's worktree is still locked** (`L28.21`,
recurring `L24.3`). A worktree is its own checkout, not its own container: an agent's suite and
this one share Postgres and Qdrant, and a `unit` directory is no promise that a test stays off
them. Both times this cost a phase, the result read as a defect in the change under test.

**That refusal is keyed on what a pytest run reaches, not on how it is spelled** (`L28.34`,
`L28.30`). Matching `tests/unit/<dir>` refused a directory that opens no connection and let
`tests/unit/<dir>/*.py` through, so an operator learned the unsafe spelling. Every file a path
argument reaches — a directory walked, a glob expanded — is judged by `tests/conftest.py`'s
`_CONTAINER_TOKENS`, read from that file so the two cannot drift. A run with no path sweeps
`testpaths`, and a path that cannot be read counts as reaching the container, as there.
Only a `pytest` in command position is a run, and `\`-continued lines are joined first
(`L28.41`): a `grep pytest` refused two agents, and a continuation dropped every path.
`pytest.raises` in text being written is not a run, and a `$(cat <file>)` path list is read from
the file (`L28.46`); a path behind any other expansion is named as unreadable, never as "no path".

Exit 2 with the paths on stderr blocks. Runs under bare `python3` (3.9).
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

_RUNS_GATE = re.compile(
    r"(^|[;&|(]\s*|\s)(poe\s+(ci-checks|ci-task|ci-no-tests|arch)\b|pytest\b[^;&|]*tests/architecture)"
)
_CONTAINER_TASK = re.compile(r"(^|[;&|(]\s*|\s)poe\s+(ci-checks|ci-task|test)\b")
# Command position only (`L28.41`): a `grep pytest` or a quoted string naming it runs nothing.
_PYTEST = re.compile(
    r"^\s*(?:\w+=\S*\s+)*(?:uv\s+run\s+(?:--?\S+\s+)*)?(?:\S*python3?\s+-m\s+)?"
    r"(?:\S*/)?pytest(?![\w.-])(.*)"
)
_CONTINUATION = re.compile(r"\\\n")
_SEGMENT_BREAK = re.compile(r"[;&|\n()]")
_TOKENS_LITERAL = re.compile(r"^_CONTAINER_TOKENS\b[^=]*=\s*\((.*?)\)", re.MULTILINE | re.DOTALL)
_CAT_EXPANSION = re.compile(r"\$\(\s*cat\s+([^()\s;&|]+)\s*\)")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(command):
    """Drop heredoc bodies from a shell command, so text being written is not read as a run.

    Args:
        command: The shell command the `Bash` tool is about to run.

    Returns:
        The command's lines with every heredoc body and its closing delimiter removed.
    """
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
    """The untracked, non-ignored files the gate's `git ls-files` walk would miss.

    Args:
        cwd: The directory the command runs in.

    Returns:
        Every untracked path under a top-level directory the repository tracks; empty when git
        cannot answer.
    """
    tracked = _git_lines(cwd, "ls-files")
    untracked = _git_lines(cwd, "ls-files", "--others", "--exclude-standard")
    if tracked is None or untracked is None:
        return []
    roots = {path.split("/", 1)[0] for path in tracked if "/" in path}
    return [path for path in untracked if "/" in path and path.split("/", 1)[0] in roots]


def _container_tokens(root):
    try:
        found = _TOKENS_LITERAL.search((root / "tests" / "conftest.py").read_text(encoding="utf-8"))
    except OSError:
        return None
    return tuple(re.findall(r"\"([^\"]+)\"", found.group(1))) if found else None


def _path_arguments(segment):
    try:
        words = shlex.split(segment)
    except ValueError:
        words = segment.split()
    return [
        word.split("::", 1)[0]
        for word in words
        if not word.startswith("-") and ("/" in word or word.endswith(".py") or word == "tests")
    ]


def _reaches_a_container(path, root, tokens):
    if os.path.relpath(path, root).replace(os.sep, "/").startswith("tests/integration"):
        return True
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True
    return tokens is None or any(token in source for token in tokens)


def _files_under(cwd, argument):
    if any(char in argument for char in "*?["):
        if Path(argument).is_absolute():
            return list(Path(argument).parent.glob(Path(argument).name))
        return list(cwd.glob(argument))
    target = cwd / argument
    return list(target.rglob("*.py")) if target.is_dir() else [target]


def _read_words(cwd, name):
    path = Path(name) if Path(name).is_absolute() else cwd / name
    try:
        return " ".join(path.read_text(encoding="utf-8").split())
    except (OSError, UnicodeDecodeError):
        return "$(cat " + name + ")"


def container_reaching(command, cwd):
    """What a pytest run or gate task in `command` would open that reaches Postgres or Qdrant."""
    root = Path((_git_lines(cwd, "rev-parse", "--show-toplevel") or [cwd])[0])
    tokens = _container_tokens(root)
    reached = []
    command = _CAT_EXPANSION.sub(lambda match: _read_words(Path(cwd), match.group(1)), command)
    for segment in _SEGMENT_BREAK.split(_CONTINUATION.sub(" ", command)):
        if _CONTAINER_TASK.search(segment):
            reached.append(segment.strip())
            continue
        call = _PYTEST.search(segment)
        if call is not None:
            reached.extend(_pytest_reaching(call.group(1), Path(cwd), root, tokens))
    return reached


def _pytest_reaching(arguments, cwd, root, tokens):
    """The files one pytest run's `arguments` reach that open a container, relative to `root`."""
    named = _path_arguments(arguments)
    swept = [
        os.path.relpath(found, root)
        for argument in named or [str(root / "tests")]
        for found in _files_under(cwd, argument)
        if _reaches_a_container(found, root, tokens)
    ]
    reached = []
    if swept and not named and "$" in arguments:
        reached.append("(its test paths come from a shell expansion this guard cannot read)")
    elif swept and not named:
        reached.append("(the run named no test path, so all of tests/ was assumed)")
    reached.extend(swept)
    return reached


def locked_agent_worktrees(cwd):
    """The locked worktrees of dispatched agents other than the one running this command.

    Args:
        cwd: The directory the command runs in.

    Returns:
        The paths of locked `agent-` worktrees that do not contain `cwd`.
    """
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
    """Refuse a run that shares a busy agent's containers, or a gate over untracked files.

    Returns:
        2 when the command is refused, with the paths on stderr; 0 otherwise.
    """
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = strip_heredocs(payload.get("tool_input", {}).get("command", ""))
    cwd = payload.get("cwd") or "."
    busy = locked_agent_worktrees(cwd)
    reached = container_reaching(command, cwd) if busy else []
    if reached:
        shown = ", ".join(reached[:5]) + (" …" if len(reached) > 5 else "")
        sys.stderr.write(
            "Refused: a dispatched agent is still running in "
            + ", ".join(busy)
            + ",\nand this run reaches the Postgres and Qdrant its suite shares"
            " (L28.21, L24.3):\n  "
            + shown
            + "\nName test files that open no container (tests/conftest.py _CONTAINER_TOKENS\n"
            "decides, L28.34), or wait for its completion notice, bring its diff back, remove\n"
            "the worktree, then run.\n"
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
