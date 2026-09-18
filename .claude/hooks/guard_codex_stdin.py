"""PreToolUse guard: `codex exec` runs with stdin closed.

`docs/internal/lessons.md` `L25.3`. `codex exec` reads stdin whenever stdin is not a terminal, and a
command the harness runs in the background never closes it: a fixture review printed `Reading
additional input from stdin...` and sat for ten minutes with an empty output file until the owner
asked why. The same command with `< /dev/null` started reading its files at once.

Refused: a command that runs `codex exec` without a `< /dev/null` (or `</dev/null`) redirect.
Heredoc bodies are stripped first, so prose that mentions the command is not refused.
Exit 2 with the reason on stderr blocks. Runs under bare `python3` (3.9).
"""

import json
import re
import sys

_RUNS_CODEX = re.compile(r"(^|[;&|(]\s*|\s)codex\s+exec\b")
_STDIN_CLOSED = re.compile(r"<\s*/dev/null")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

REASON = """Refused: `codex exec` without stdin closed waits for input forever when the harness runs
it in the background, printing only "Reading additional input from stdin..." (L25.3).
Add `< /dev/null` to the codex command."""


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


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = strip_heredocs(payload.get("tool_input", {}).get("command", ""))
    if _RUNS_CODEX.search(command) and not _STDIN_CLOSED.search(command):
        sys.stderr.write(REASON + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
