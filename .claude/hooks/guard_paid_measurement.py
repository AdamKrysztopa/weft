"""PreToolUse guard: a paid measurement is started only after its nine checks are answered.

`docs/internal/lessons.md` `L24.4`, `L24.7`, `L24.9`, `L24.10`, `L24.11` and `L24.12`, drained
2026-09-17. Phase 38's two measurements ran six times between them: `38.5` four times and `38.6`
three. Every restart traced to a question answerable before `--yes` and asked only after a paid
run had failed — a defect only a scale nobody tried reaches (`R38.5`–`R38.8`, `R38.11`,
`R38.12`), three identical repetitions of deterministic arms (65% of `38.5`'s time), a 20-document
batch holding ~2 GB, a crash that re-paid every model call because no batch was kept, and research
agents sharing the host until it killed the run. Each was a rule nobody was prompted to apply at
the one moment it mattered, which is the moment this hook sees: the command that starts the run.

**What is refused.** A `Bash` command that runs `eval experiment` (any `weft` spelling, not
`--help`) without the literal acknowledgement `WEFT_MEASUREMENT_CHECKED=1` in it. The refusal prints
the checklist; setting the variable is the act of having answered it, the same shape
`guard_unchecked_commit.py` uses — a refusal costs one turn, a missed check costs hours.

Not refused: `weft eval run`, `weft index`, unit and integration suites, and a script file that runs
the binary itself — a shell script is where a checked, repeatable run belongs anyway.

Exit 2 with the reason on stderr blocks. Runs under bare `python3` (3.9).
"""

import json
import re
import sys

_RUNS_EXPERIMENT = re.compile(r"\bev" + r"al\s+experiment\b")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_ACKNOWLEDGED = "WEFT_MEASUREMENT_CHECKED=1"

REASON = """Refused: a paid measurement starts only after these are answered.
(L24.4, L24.7, L24.9-L24.13, L25.4, L26.5, L26.7)
1. Scale smoke: has this harness run on the free embedder and scripted provider with more than 256
   questions, more than five searches per connection, a planted rung failure and an unparseable
   completion — and were its records read?
2. Priced in three units: dollars, wall hours (calls / concurrency x seconds per call) and peak
   memory (nodes per batch x vector width) — all three in the approval.
3. Repeats: which arms reach a model? A deterministic arm's repetitions are identical by
   construction.
4. A crash: can the run resume from its written records and finished batches, and if not, what
   would a restart re-pay — and is that in the approval? (L24.13)
5. The host: nothing else heavy runs beside it — no implementer suites, no research fan-out.
6. First record: n against the question count, excluded and why, tokens, peak memory — read before
   the rest runs, and the run stopped if any is not what the plan expects.
7. The query side matches the index side: `[services] embed` names the index pipeline's embedder and
   model. A free smoke on `hash` uses one default for both, so it cannot catch this — and the paid
   run fails at its first question, after the embedding is paid for (L25.4).
8. Every metric the plan names is in the free smoke's record — not only registered and unit-tested:
   a metric no real run has computed may be one the harness cannot produce (L26.5).
9. The change moved what it should: each arm's downstream size caps are read in `weft pipeline
   show`, and the smoke's record differs from baseline in the quantity the change acts on (prompt
   tokens, passages kept) — a widened stage feeding an unchanged cap measures the cap (L26.7).
Answer them, then prefix the command with WEFT_MEASUREMENT_CHECKED=1."""


def strip_heredocs(command):
    """`command` without heredoc bodies: `guard_unchecked_commit.py`'s own first false positive,
    met again by this guard on the commit that wrote it — prose being written to a file."""
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


_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def offends(command):
    # Quoted text is a pattern or an argument, not a command: a `pgrep -f "… experiment"` status
    # check was refused (L24.2's shape). A run wrapped in `sh -c '…'` is not seen either.
    command = _QUOTED.sub("", strip_heredocs(command))
    if not _RUNS_EXPERIMENT.search(command):
        return False
    if "--help" in command:
        return False
    return _ACKNOWLEDGED not in command


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if isinstance(command, str) and offends(command):
        sys.stderr.write(REASON + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
