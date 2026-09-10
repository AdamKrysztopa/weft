"""PreToolUse guard: refuse a shell expansion that can print the value of a credential.

**`docs/lessons.md` `L11.31`, and it is the most expensive lesson this repository has bought.**
Task 11.6 needed to show that a rung ran with *no credential present*. The line written to prove it
was:

    echo "OPENAI_API_KEY=${OPENAI_API_KEY:-<unset>}"

`${VAR:-fallback}` expands to **the value** whenever the variable is set, and shows the fallback
only in the case nobody was worried about. The key was set. It went into a transcript and had to be
rotated.

**The rule the author already knew.** Ask about the *name*, never the value:

    if [ -n "${OPENAI_API_KEY+x}" ]; then echo "set"; else echo "unset"; fi

`${VAR+x}` expands to `x` or to nothing and can never render a secret. So can `${VAR:+set}`. Both
are allowed here; only the forms that expand to the value are refused.

**Why a hook rather than a sentence.** The sentence exists — `phase-step` → *Finish* carries it —
and the moment it governs is *while a command is being typed*, which is exactly the moment
`implement-ll` says a hook owns and a document does not. And the cost of being forgotten once is
not a failed gate: it is a live credential in a log that may already have been read, and a rotation
somebody else has to perform. There is no cheaper place to put this.

**What is refused, deliberately narrowly.** A parameter expansion whose *variable name* looks like a
credential — it contains `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `CREDENTIAL`, `API` or
`AUTH`, case-insensitively — **and** whose operator is one of the value-rendering forms `:-`, `-`,
`:=`, `=`, `:?` or `?`, or which is a bare `${VAR}` / `$VAR` inside a command that also writes
output (`echo`, `printf`, `>`, `tee`). A name that does not look like a credential is untouched,
and so is every `${VAR+x}` / `${VAR:+…}` test, which is the idiom this guard exists to leave as the
obvious alternative.

A bare `${VAR}` on its own is *not* refused: passing a credential to a program that needs it is the
normal case and refusing it would make the guard useless. What is refused is rendering it into
output a person or a transcript reads.

**A false refusal costs one turn**, and the message says which spelling to use instead; a missed
one costs a rotation. That asymmetry is why the matching is loose, per `CLAUDE.md`'s rule for a
machine parsing what a model wrote.

Blocking is a PreToolUse convention: exit 2, with the reason on stderr. Runs under bare `python3`
(3.9 on the development machine), so nothing here uses 3.10+ syntax.
"""

import json
import re
import sys

#: A variable name that plausibly holds a credential. Substring match, case-insensitive: this is
#: deliberately generous, because the cost of a false positive is one turn and the cost of a false
#: negative is a rotation. `API` is included on its own because `OPENAI_API_KEY`'s sibling
#: `..._API_BASE` is harmless while `..._API_TOKEN` is not, and the operator test below is what
#: keeps the generosity from being noisy.
_SECRETISH = (
    r"[A-Za-z_][A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API|AUTH)[A-Za-z0-9_]*"
)

#: `${NAME:-…}`, `${NAME-…}`, `${NAME:=…}`, `${NAME=…}`, `${NAME:?…}`, `${NAME?…}` — every
#: expansion form that yields the variable's own value when it is set. `${NAME+x}` and
#: `${NAME:+x}` are absent on purpose: they yield a constant and are the remedy this guard names.
_RENDERS_VALUE = re.compile(r"\$\{\s*" + _SECRETISH + r"\s*:?[-=?]", re.IGNORECASE)

#: A bare `${NAME}` or `$NAME` reference to a credential-shaped variable.
_BARE_REFERENCE = re.compile(r"\$\{\s*" + _SECRETISH + r"\s*\}|\$" + _SECRETISH, re.IGNORECASE)

#: Commands and redirections that put their argument somewhere a person or a file will read it.
_WRITES_OUTPUT = re.compile(r"\b(?:echo|printf|tee)\b|>>?\s*\S", re.IGNORECASE)

REASON = (
    "Refused: this command can print the value of a credential.\n"
    "\n"
    "`${VAR:-fallback}` (and `-`, `:=`, `=`, `:?`, `?`) expands to the variable's own VALUE "
    "whenever it is set, and shows the fallback only in the case you were not worried about. "
    "A bare `${VAR}` passed to echo/printf/tee or into a redirect does the same thing.\n"
    "\n"
    "docs/lessons.md L11.31: the line written to prove no credential was present printed the "
    "owner's API key into a transcript, and it had to be rotated.\n"
    "\n"
    "Ask about the NAME, never the value:\n"
    '    if [ -n "${VAR+x}" ]; then echo "set"; else echo "unset"; fi\n'
    "`${VAR+x}` expands to `x` or to nothing and can never render the secret. `${VAR:+set}` is "
    "the same idea.\n"
    "\n"
    "If you genuinely need to hand the credential to a program, pass it without echoing it — "
    '`prog --key "$VAR"` with no redirect is not refused.'
)


def offends(command):
    """Whether `command` contains an expansion that can render a credential's value.

    Two shapes, and the second is deliberately conditional. A value-rendering operator on a
    credential-shaped name is refused outright — there is no correct use of `${API_KEY:-…}` that
    would not be better written as a `+x` test. A *bare* reference is refused only when the same
    command also writes output, because passing a secret to the program that needs it is the
    ordinary case and a guard that refused it would be routed around within a day.
    """
    if _RENDERS_VALUE.search(command):
        return True
    return bool(_BARE_REFERENCE.search(command) and _WRITES_OUTPUT.search(command))


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        return 0
    if not offends(command):
        return 0
    sys.stderr.write(REASON + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
