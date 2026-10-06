"""PreToolUse guard: reading `docs/internal/done/` or `obsolete/` asks the owner first.

Those two folders hold finished work (closed phases, settled gates, closed plans) and superseded
drafts, moved out by `.claude/skills/phase-step/scripts/sort_internal.py` so that a question about
the plan reads the live files alone. Before the split, `build-ledger.md` was 2.1 MB and a status
question read it. Reading the archive is still allowed, but the owner approves it.

Asked about: a `Read`, `Grep` or `Glob` whose path or pattern points into either folder, or a
`Grep`/`Glob` over `docs/internal` itself (which recurses into them); a `Bash` command naming
either folder, or a recursive grep/rg/find over `docs/internal`. `ideas/` is not gated.
Runs under bare `python3` (3.9). `--self-test` checks the matcher.
"""

import json
import re
import sys

_ARCHIVE = re.compile(r"docs/internal/(done|obsolete)(/|\b)")
_INTERNAL_ROOT = re.compile(r"docs/internal/?$")
_RECURSIVE_OVER_ROOT = re.compile(
    r"\b(grep\s+[^|;&]*-[a-zA-Z]*[rR][a-zA-Z]*|rg|find|ugrep)\s[^|;&]*docs/internal/?(\s|$|[|;&])"
)

REASON = (
    "This reads docs/internal/done/ or obsolete/: finished phases, settled gates, closed plans "
    "and superseded drafts. The live files (README.md, build-ledger.md, 12-roadmap.md, ideas/) "
    "answer questions about the plan. Allow reading the archive?"
)


def targets_archive(tool_name, tool_input):
    """Whether this tool call would read the archive folders.

    Args:
        tool_name: The tool about to run.
        tool_input: Its input.

    Returns:
        True when the call names `done/` or `obsolete/`, or searches `docs/internal` recursively.
    """
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        return bool(_ARCHIVE.search(command) or _RECURSIVE_OVER_ROOT.search(command))
    fields = [str(tool_input.get(key, "")) for key in ("file_path", "path", "pattern", "glob")]
    if any(_ARCHIVE.search(value) for value in fields):
        return True
    path = str(tool_input.get("path", ""))
    return tool_name in ("Grep", "Glob") and bool(_INTERNAL_ROOT.search(path.rstrip()))


def self_test():
    """Check the matcher on the calls it exists for and the ones it must leave alone."""
    asked = [
        ("Read", {"file_path": "/x/weft/docs/internal/done/build-ledger.md"}),
        ("Grep", {"pattern": "R44", "path": "docs/internal"}),
        ("Glob", {"pattern": "docs/internal/obsolete/**"}),
        ("Bash", {"command": "sed -n 1,40p docs/internal/done/12-roadmap.md"}),
        ("Bash", {"command": "grep -rn 'G12' docs/internal"}),
        ("Bash", {"command": "rg G12 docs/internal/ | head"}),
    ]
    passed = [
        ("Read", {"file_path": "/x/weft/docs/internal/build-ledger.md"}),
        ("Grep", {"pattern": "R44", "path": "docs/internal/ideas"}),
        ("Bash", {"command": "python3 .claude/skills/phase-step/scripts/next_task.py"}),
        ("Bash", {"command": "grep -n Status docs/internal/README.md"}),
    ]
    wrong = [call for call in asked if not targets_archive(*call)]
    wrong += [call for call in passed if targets_archive(*call)]
    for call in wrong:
        print(f"self-test FAIL: {call}")
    print("self-test ok" if not wrong else "")
    return 1 if wrong else 0


def main():
    """Ask the owner before a call that reads the archive; stay silent otherwise.

    Returns:
        0 always; the decision travels in the JSON on stdout.
    """
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    payload = json.load(sys.stdin)
    if targets_archive(payload.get("tool_name", ""), payload.get("tool_input", {})):
        decision = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": REASON,
            }
        }
        sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
