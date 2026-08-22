"""Walk `docs/lessons-archive.md` and report what a flat reading cannot see.

The archive is a graph because the loop's worst failure is a *sequence*, not an
entry: a rule is added, a later drain finds it noisy and reverses it, and a
third re-learns the original lesson. Every step is defensible alone. Only the
chain is wrong, and by then the queue that would have shown it has been emptied
twice.

Three reports, in descending order of how much they should stop you:

1. **Oscillation** — a `reverses` edge onto an entry that itself reverses
   something. Per the archive's own rule this is a stop: the subject is an
   unsettled decision wearing a lesson's clothes, and it belongs in a grilling
   session with the chain as its evidence. Exit 1.
2. **Recurrence** — a rule that has been re-learned. The rule did not bite, so
   it is in the wrong artefact; the repair is to `move` it, not to write a
   second rule saying the same thing louder. Exit 1 at two or more.
3. **Dangling references** — an edge naming an id the archive does not hold.
   Usually a typo, occasionally an entry deleted when it should have been kept.

`implement-ll` runs this before applying anything. It reads one file and has no
dependencies, so it costs nothing to run and there is no excuse not to.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parents[1] / "docs" / "lessons-archive.md"

_DRAIN = re.compile(r"^## (\d{4}-\d{2}-\d{2}) — (.+)$")
_ENTRY = re.compile(r"^- \*\*(L[\d.]+)\*\*\s+(.*)$")
_EDGE = re.compile(r"`(refines|supersedes|moves|recurs|reverses|caused-by) (L[\d.]+)`")
# The format block inside the prose uses the same shapes; skip the fenced example.
_FENCE = re.compile(r"^```")

EDGES = ("refines", "supersedes", "moves", "recurs", "reverses", "caused-by")


def parse(text: str) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """Return `{id: drain-date}` and a list of `(source, edge, target)`."""
    entries: dict[str, str] = {}
    edges: list[tuple[str, str, str]] = []
    drain = "?"
    fenced = False

    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        if match := _DRAIN.match(line):
            drain = match.group(1)
            continue
        if match := _ENTRY.match(line):
            lesson_id, rest = match.group(1), match.group(2)
            entries[lesson_id] = drain
            edges += [(lesson_id, kind, target) for kind, target in _EDGE.findall(rest)]

    return entries, edges


def _report_oscillation(reverses: dict[str, list[str]]) -> int:
    """A reversal of a reversal. The archive's own rule makes this a stop."""
    reversers = {source for sources in reverses.values() for source in sources}
    pairs = sorted(
        (source, target)
        for target, sources in reverses.items()
        for source in sources
        if target in reversers
    )
    if not pairs:
        return 0

    print("OSCILLATION — a reversal of a reversal. This is a stop, not an entry.")
    print("  The subject is an unsettled decision, not a lesson. Take the whole")
    print("  chain to a grilling session rather than applying either side again.\n")
    reversed_by = {source: target for target, ss in reverses.items() for source in ss}
    for source, target in pairs:
        chain, node = [source, target], target
        while (node := reversed_by.get(node)) and node not in chain:
            chain.append(node)
        print(f"  {' reverses '.join(chain)}")
    print()
    return 1


def _report_recurrence(recurs: dict[str, list[str]]) -> int:
    """A rule that was applied and re-learned anyway is in the wrong artefact."""
    problems = 0
    for target, sources in sorted(recurs.items()):
        count = len(sources)
        if count >= 2:
            problems += 1
        verdict = "MOVE IT" if count >= 2 else "check where it landed"
        print(
            f"RECURRENCE — {target} re-learned {count}x "
            f"(by {', '.join(sorted(sources))}): {verdict}."
        )
        print("  A rule that was applied and did not bite is in the wrong artefact.")
        print("  The repair is `moves`, not a second rule saying the same thing louder.\n")
    return problems


def main() -> int:
    try:
        text = ARCHIVE.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read {ARCHIVE}: {exc}", file=sys.stderr)
        return 2

    entries, edges = parse(text)
    if not entries:
        print("archive holds no drained entries yet — nothing to check.")
        return 0

    reverses: dict[str, list[str]] = defaultdict(list)
    recurs: dict[str, list[str]] = defaultdict(list)
    dangling: list[tuple[str, str, str]] = []

    for source, kind, target in edges:
        if target not in entries:
            dangling.append((source, kind, target))
        elif kind == "reverses":
            reverses[target].append(source)
        elif kind == "recurs":
            recurs[target].append(source)

    problems = _report_oscillation(reverses) + _report_recurrence(recurs)

    for source, kind, target in sorted(dangling):
        print(f"DANGLING — {source} `{kind} {target}` but {target} is not in the archive.")

    if not problems and not dangling:
        print(f"{len(entries)} entries, {len(edges)} edges — no oscillation, no recurrence.")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
