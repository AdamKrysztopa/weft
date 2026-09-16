"""Stop — refuse a turn whose visible reply narrates the assistant's own planning.

The owner asked three times, in one session, for this to stop. A fourth sentence would have
been the wrong repair: `docs/internal/lessons.md` `L9.56` is exactly this shape — *a project
prohibition that contradicts generic tool guidance needs a mechanism, not a stronger
sentence.* This is the mechanism.

**What is being refused, and why it kept happening.** The harness appends a reminder asking
the model to *"first privately list what you need next, then request every item that doesn't
depend on another's result"*. That instruction is sound and stays in force — the defect was
printing the list into the user-visible reply instead of keeping it in reasoning. *Privately*
means privately. So this hook does not fight the reminder; it enforces the one word in it the
model kept dropping.

**Why a Stop hook rather than a style note.** A style note is read at the top of a session and
decays; this fires on the artefact itself, every turn, and names the offending line back. It
checks the **last assistant message only** — earlier turns are history and re-blocking them
would make the session unendable.

**`stop_hook_active` is why this cannot loop**, on `lessons_gate.py`'s own reasoning: the
payload carries it, it is true on the continuation this hook caused, and blocking there would
be an unbreakable turn.

**It reads the transcript defensively.** Anything unreadable, absent or unparseable is silence
and exit 0 — a hook that cannot do its job must not break the session that was about to fix
it. It also runs under bare `python3` (3.9 on this machine), so nothing here uses a 3.12 idiom.
"""

import json
import re
import sys
from pathlib import Path

#: Phrases that only ever appear when the reply is narrating its own plan rather than
#: answering. Each was taken from a real offending message in the session that produced this
#: hook, not invented — a pattern nobody has seen fire is a pattern nobody can size.
#:
#: Deliberately anchored to the *opening* of a line or sentence. "What I need" inside a
#: sentence of ordinary prose ("this is what I need to check before claiming it") is not the
#: defect; a line that *begins* by announcing the model's own shopping list is.
_NARRATION = (
    re.compile(r"(?im)^\s*privately[,:\s]"),
    re.compile(r"(?im)^\s*(what|everything)\s+i\s+(still\s+)?need\s+(next|now|before)\b"),
    re.compile(r"(?im)^\s*needed\s+next\b"),
    re.compile(r"(?im)^\s*(let me|i'll)\s+(first\s+)?privately\b"),
    re.compile(r"(?im)^\s*privately\s+list(ing)?\b"),
    re.compile(r"(?im)\bprivately,?\s+(what|the only thing)\s+i\s+need\b"),
)


def _is_real_user_turn(message):
    """Whether `message` is a human turn rather than a tool result.

    **This distinction is the whole reason the first version of this hook never fired once.**
    A tool result is recorded with ``role: "user"`` and a ``tool_result`` content block, so
    "walk back to the last user message" stops at the first tool result — which in an agentic
    turn is a handful of lines back, before any assistant prose exists. Measured against a real
    transcript: the naive walk returned **zero** assistant text blocks.
    """
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if isinstance(content, list):
        return not any(
            isinstance(block, dict) and block.get("type") == "tool_result" for block in content
        )
    return True


def assistant_text_this_turn(transcript_path):
    """Every visible assistant text block since the last genuine human turn.

    **Not just the final message, which is the defect this function was rewritten to fix.** A
    `Stop` hook fires when the turn ends; narration lands in *intermediate* assistant messages,
    the ones followed by tool calls. Reading only the last message inspects the one place the
    narration never is. The owner asked three times for the narration to stop, a hook was written
    to enforce it, and it stayed silent through several more instances for exactly this reason —
    a check that cannot see its own subject is not a check (`phase-step` → *Finish* item 3).

    Only ``text`` blocks count. A tool call's input is not a reply to the user, and matching
    inside one would fire on this very file's own source the moment it is written — the `L12.8`
    trap, where the paragraph documenting a check becomes the check's own input.
    """
    try:
        with Path(transcript_path).open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, TypeError, ValueError):
        return ""
    collected = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        message = entry.get("message") or {}
        if _is_real_user_turn(message):
            break
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            collected.append(content)
        elif isinstance(content, list):
            collected.extend(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
    return "\n".join(reversed(collected))


def offences(text):
    """Every narrating line in ``text``, with the pattern that caught it."""
    found = []
    for pattern in _NARRATION:
        for match in pattern.finditer(text):
            line = text[: match.start()].count("\n") + 1
            snippet = text.splitlines()[line - 1].strip() if text.splitlines() else ""
            found.append((line, snippet[:120]))
    return sorted(set(found))


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("hook_event_name") != "Stop":
        return 0
    if payload.get("stop_hook_active"):
        return 0

    text = assistant_text_this_turn(payload.get("transcript_path"))
    if not text:
        return 0

    hits = offences(text)
    if not hits:
        return 0

    listed = "\n".join("  line {0}: {1}".format(line, snippet) for line, snippet in hits)
    print(
        "This reply narrates its own planning, which the owner has now asked to stop three "
        "times:\n" + listed + "\n\n"
        "The harness reminder that asks you to *privately* list what you need next means "
        "privately — in your reasoning, not in the reply. Keep doing the planning; stop "
        "printing it. Rewrite the reply so it carries the answer, the result, or the "
        "decision, and nothing about what you are about to fetch.\n\n"
        "If you genuinely need something only the owner can decide, do not narrate it — ask, "
        "with AskUserQuestion, and mark exactly one option (Recommended).",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
