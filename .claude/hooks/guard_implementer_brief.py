"""PreToolUse guard: a `weft-implementer` brief carries measured facts, not a reading.

`docs/internal/lessons.md` `L24.1` and `L24.6`, drained 2026-09-17. Both were rules already
Applied in `phase-step/references/implementer-brief.md` — check 4 (`L22.13`: group a red file's
errors by message) and check 13 (`L23.15`: say who re-points citations into a heavily cited file)
— and both recurred in Phase 38, three times between them, each time sending an implementer to
build a whole task and return blocked on something the dispatcher could have measured in seconds:
a red test's own typing defect hidden inside "the import cascade", and a `path:line` citation into
the module the brief named as the fix's home. A sentence in a reference that is read before
writing a brief did not bite; the moment it must bite is the dispatch itself, which is detectable.

**What is refused.** An `Agent` call whose `subagent_type` is `weft-implementer` and whose prompt
does not carry the block `.claude/skills/phase-step/scripts/brief_facts.py` prints — the line
`## Brief facts` and a `brief_facts_head:` line. The script groups the red files' pyright errors by
the symbol they name, marking those naming no missing symbol, and lists every citation into the
owner modules. Presence is all that is checked: the point is that the numbers were produced by a
command, and the dispatcher still reads them.

Every other agent type is untouched. Exit 2 with the reason on stderr blocks, per the PreToolUse
convention. Runs under bare `python3` (3.9): nothing here uses 3.10+ syntax.
"""

import json
import sys

REASON = (
    "Refused: a weft-implementer brief must carry the `## Brief facts` block (L24.1, L24.6).\n"
    "Run, from the repository root:\n"
    "  python3 .claude/skills/phase-step/scripts/brief_facts.py "
    "--red <red test files> --owners <modules the change edits>\n"
    "then paste its output into the brief: account for every OTHER error group, and say who "
    "re-points each citation the change will move."
)


def needs_facts(tool_input):
    if tool_input.get("subagent_type") != "weft-implementer":
        return False
    prompt = tool_input.get("prompt", "")
    if not isinstance(prompt, str):
        return False
    return "## Brief facts" not in prompt or "brief_facts_head:" not in prompt


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") not in ("Agent", "Task"):
        return 0
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, dict) and needs_facts(tool_input):
        sys.stderr.write(REASON + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
