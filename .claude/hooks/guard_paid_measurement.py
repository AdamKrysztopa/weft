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

REASON = """Refused: a measurement starts only after these are answered.
(L24.4, L24.7, L24.9-L24.13, L25.4, L26.5, L26.7, L28.2, L28.5, L28.6, L28.8, L28.9, L28.66,
 L28.85)
1. Scale smoke: has this harness run on the free embedder and scripted provider with more than 256
   questions, more than five searches per connection, a planted rung failure and an unparseable
   completion — and were its records read?
1b. Shape smoke, for any arm that calls a model: one real input through that arm's own seam, and
   what came back checked against what the consuming code requires — a count, not a status. A 7B
   model returned 49 judgements for 50 passages, valid JSON, and six hours of running excluded 823
   of 830 questions; one call showed it in twenty seconds (L28.9). The smoke keeps every argument
   of the full run it does not have to shrink, and what it shrinks is checked against the full
   input offline: E4's smoke dropped the manifest and the full run failed on it (L28.85).
1c. Progress: what does the command print between its start and its first record? A run that
   prints nothing is watched through open sockets; `weft eval experiment` wrote no line for 25
   minutes of a paid run (L28.66).
1d. Bounded and timed: the run goes through the measurement runner in batches (`--batch-size`),
   never by hand as one batch — a hand-launched `weft eval run` held 227,425 chunks in one batch,
   hung on a dropped request and kept nothing (L28.101). Each account's request timeout is set
   above the per-request latency measured at the run's own concurrency and batch size, on the
   server that will answer: a round 120 s against TEI's 92-114 s queue abandoned every batch it
   timed out (L28.102).
2. Priced in three units: dollars, wall hours (calls / concurrency x seconds per call) and peak
   memory (nodes per batch x vector width) — all three in the approval. Memory on Apple silicon is
   read with `footprint`, never RSS, which misses Metal buffers by ~10x (L28.5); a served model's
   container carries `--memory`, sized from what it allocates at its maximum input length rather
   than from its weights (L28.2).
2b. A floor, watched while it runs: free disk and memory, checked on an interval, the run stopping
   itself when either is crossed. A full disk and exhausted swap wedged the store and stalled a
   nine-hour run for three hours while its log still printed elapsed minutes — so progress reports
   work done since the last sample, never time (L28.8). Touching the container host (a VM resize)
   stops every container: bring the stack back up and check its row counts afterwards (L28.2).
3. Repeats: which arms reach a model? A deterministic arm's repetitions are identical by
   construction.
4. A crash: can the run resume from its written records and finished batches, and if not, what
   would a restart re-pay — and is that in the approval? (L24.13)
5. The host: nothing else heavy runs beside it — no implementer suites, no research fan-out, and
   one served model at a time. Record the load average and the top processes before and after a
   timed run: the OS's own indexers held this host near 8 with nothing of ours running, which is
   +-5-10% on every throughput figure (L28.6).
6. First record: n against the question count, excluded and why, tokens, peak memory — read before
   the rest runs, and the run stopped if any is not what the plan expects.
7. The query side matches the index side. For `weft ask`, `[services] embed` names the index
   pipeline's embedder and model: a free smoke on `hash` uses one default for both, so it cannot
   catch this, and the paid run fails at its first question, after the embedding is paid for
   (L25.4). `weft eval run` and `weft eval experiment` embed each arm's questions with that arm's
   own ingest `Embedder` stage since 20.12, so there the item is the record's `query_embedding`,
   read on the first record (L28.98).
7b. The served model's identity is its name and every setting that changes its numbers — dtype,
   maximum input length, backend — read from the server and recorded with the run. A Metal build
   defaulted to float16 where the same version's container served float32 (L28.5).
8. Every metric the plan names is in the free smoke's record — not only registered and unit-tested:
   a metric no real run has computed may be one the harness cannot produce (L26.5).
9. The change moved what it should: each arm's downstream size caps are read in `weft pipeline
   show`, and the smoke's record differs from baseline in the quantity the change acts on (prompt
   tokens, passages kept) — a widened stage feeding an unchanged cap measures the cap (L26.7).
Answer them, then prefix the command with WEFT_MEASUREMENT_CHECKED=1."""


def strip_heredocs(command):
    """`command` without heredoc bodies, so prose written to a file is not refused.

    `guard_unchecked_commit.py`'s own first false positive, met again by this guard on the commit
    that wrote it — prose being written to a file.
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


_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def offends(command):
    """Whether `command` starts a paid experiment run without the checklist acknowledged.

    Args:
        command: The shell command the `Bash` tool is about to run.

    Returns:
        True when an unquoted experiment run appears, is not `--help`, and lacks the
        acknowledgement variable.
    """
    # Quoted text is a pattern or an argument, not a command: a `pgrep -f "… experiment"` status
    # check was refused (L24.2's shape). A run wrapped in `sh -c '…'` is not seen either.
    command = _QUOTED.sub("", strip_heredocs(command))
    if not _RUNS_EXPERIMENT.search(command):
        return False
    if "--help" in command:
        return False
    return _ACKNOWLEDGED not in command


def main():
    """Refuse a `Bash` call that starts a paid measurement before its checklist is answered.

    Returns:
        2 when the command is refused, with the checklist on stderr; 0 otherwise.
    """
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


def _self_test():
    """Run as `python3 <this file> --self-test`; `.claude/hooks/` is outside `ci-checks` (`R44.22`).

    The run is assembled, as in `guard_history_rewrites.py`, so this file never refuses a grep.
    """
    run = "uv run weft " + "ev" + "al experiment eval/experiments/x.toml --yes"
    cases = (
        (run, True, "a bare run is refused"),
        (_ACKNOWLEDGED + " " + run, False, "an acknowledged run is allowed"),
        (run.replace("--yes", "--help"), False, "help is not a run"),
        ('pgrep -f "' + run + '"', False, "a quoted pattern is not a run"),
        ("cat > notes.md <<'EOF'\n" + run + "\nEOF\n", False, "a heredoc body is prose"),
        ("ls && " + run, True, "a chained run is still refused"),
        ("uv run weft " + "ev" + "al run x", False, "an eval run is not an experiment"),
    )
    failures = [
        "{0!r}: expected {1} — {2}".format(command, "refused" if refuse else "allowed", why)
        for command, refuse, why in cases
        if offends(command) != refuse
    ]
    for failure in failures:
        sys.stderr.write(failure + "\n")
    print("{0} of {1} probes hold".format(len(cases) - len(failures), len(cases)))
    return 1 if failures else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    sys.exit(main())
