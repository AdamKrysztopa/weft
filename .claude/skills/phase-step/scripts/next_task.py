#!/usr/bin/env python3
"""Print the first unticked task in `docs/internal/build-ledger.md`, the task after it, and its gate
state.

`phase-step` → *Orient* opens by asking for the first unticked box, the task after it, and whether
the phase carries a block. Done by hand that is a scan of a 2,400-line file, and it has a trap in
it: **`build-ledger.md` → *How to read a task line* contains an unticked task line inside a fenced
block** — a shape rather than a real task, placed there deliberately so no worked example could
drift from the list below it. `grep -n '^- \\[ \\]'` finds that line first, every time, and an agent
that trusts the grep starts work on a task whose id is the placeholder `N.M`. Two things stop that
here — fences are skipped, and a task id must be numeric — and the self-test plants a *numeric* id
inside the fence so the fence tracking is the half being proved rather than the id regex.

So the parse is here rather than in prose: fences are tracked, continuation lines are joined (a
task line may wrap — 7.1 and 7.3 both do), and the phase preamble the task sits under is carried
along so a block can be reported with it.

**What this decides and what it does not.** It decides which line is next, deterministically. It
does *not* decide whether the phase is workable: a preamble carrying ⛔ may be recording a block
that is live (Phase 7, *"⛔ Blocked by G12"*) or one that was lifted (Phase 6 opens with
*"✅ Unblocked 2026-08-22"*, and the phases before it discuss ⛔ in the past tense). Text cannot
tell those apart reliably, so every ⛔-carrying preamble line is printed verbatim and the exit code
says "look at this", never "stop". Reading it is the orchestrator's, per `phase-step` → *Orient*.

    python3 .claude/skills/phase-step/scripts/next_task.py
    python3 .claude/skills/phase-step/scripts/next_task.py --json
    python3 .claude/skills/phase-step/scripts/next_task.py --self-test

Exit codes: 0 next task found, phase preamble clean · 1 next task found, preamble carries ⛔ ·
2 nothing unticked · 3 the ledger could not be read or parsed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BLOCKED = "⛔"
PROVISIONAL = "⚠"

FENCE = re.compile(r"^\s*```")
PHASE_HEADER = re.compile(r"^##\s+(Phase\s+\S+.*)$")
TASK_START = re.compile(r"^- \[([ xX])\]\s+(.*)$")
# `[a-z]?`: the ledger writes lettered sub-tasks (`5.1a`…`5.2g`, `7.2a`). Without it this
# read thirteen of them as two ids, found on its first run by the cross-parser check in
# `tests/docs/test_ledger_records_a_sha.py` (`docs/internal/lessons.md` `L13.3`).
TASK_ID = re.compile(
    r"^\*\*(?P<id>[0-9]+(?:\.[0-9]+)?[a-z]?)\s*(?P<flag>[^*]*)\*\*\s*(?P<rest>.*)$"
)

# A joined task line is `property · owner … · turns on … · sha …`. The separator is a middle dot
# with spaces either side; it never appears inside a field in this ledger.
SEPARATOR = " · "


@dataclass
class Task:
    """One `- [ ]`/`- [x]` line, with its wrapped continuation lines joined back on."""

    lineno: int
    checked: bool
    identifier: str
    provisional: bool
    text: str
    phase: str
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def property_sentence(self) -> str:
        """What is true when the task is done — the first field, before `owner`."""
        return self.text.split(SEPARATOR, 1)[0].strip()


@dataclass
class Phase:
    title: str
    lineno: int
    preamble: list[tuple[int, str]] = field(default_factory=list)

    @property
    def blocked_lines(self) -> list[tuple[int, str]]:
        return [(n, line) for n, line in self.preamble if BLOCKED in line]


def parse(ledger: str) -> tuple[list[Task], dict[str, Phase]]:
    """Return every task in file order, and the phase each one sits under.

    Lines inside ``` fences are skipped wholesale, which is the point of the function.
    """
    tasks: list[Task] = []
    phases: dict[str, Phase] = {}
    in_fence = False
    phase: Phase | None = None
    seen_task_in_phase = False
    open_task: Task | None = None

    for lineno, raw in enumerate(ledger.splitlines(), start=1):
        if FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        header = PHASE_HEADER.match(raw)
        if header:
            phase = Phase(title=header.group(1).strip(), lineno=lineno)
            phases[phase.title] = phase
            seen_task_in_phase = False
            open_task = None
            continue

        start = TASK_START.match(raw)
        if start:
            open_task = _new_task(lineno, start, phase)
            if open_task is not None:
                tasks.append(open_task)
            seen_task_in_phase = True
            continue

        stripped = raw.strip()
        # **A list marker is the character *plus a space*; `-` and `*` alone are not.** A
        # continuation line opening with emphasis — `*Read* face · ... · sha \`7976e97\` · ...`,
        # which is exactly how task 10.23's own line wraps — was read as a new block, so the
        # task closed early and every field on that line, the sha among them, went missing.
        # `tests/docs/test_ledger_records_a_sha.py` saw the sha because it parses the whole
        # entry; this parser did not, and the two disagreeing about one field is the defect
        # (`docs/internal/lessons.md` L10.38).
        is_continuation = bool(stripped) and not (
            stripped.startswith(("#", ">", "|"))
            or stripped[:2] in ("- ", "* ")
            or stripped in ("-", "*")
        )
        if open_task is not None and is_continuation:
            open_task.text = f"{open_task.text} {stripped}"
            open_task.fields = _split_fields(open_task.text)
            continue

        open_task = None
        # Preamble is everything between the phase header and its first task line. A ⛔ further
        # down (a retrospective aside, as in Phase 3) is not this phase's gate state.
        if phase is not None and not seen_task_in_phase and stripped:
            phase.preamble.append((lineno, stripped))

    return tasks, phases


def _new_task(lineno: int, start: re.Match[str], phase: Phase | None) -> Task | None:
    body = start.group(2).strip()
    ident = TASK_ID.match(body)
    if ident is None:
        return None  # a bullet that happens to be a checkbox but carries no task id
    text = ident.group("rest").strip()
    return Task(
        lineno=lineno,
        checked=start.group(1).lower() == "x",
        identifier=ident.group("id"),
        provisional=PROVISIONAL in ident.group("flag"),
        text=text,
        phase=phase.title if phase else "(no phase heading)",
        fields=_split_fields(text),
    )


def _split_fields(text: str) -> dict[str, str]:
    """Pull `owner`, `turns on` and `sha` out of the ` · `-separated tail."""
    out: dict[str, str] = {}
    for chunk in text.split(SEPARATOR)[1:]:
        chunk = chunk.strip()
        for key in ("owner", "turns on", "sha"):
            if chunk.lower().startswith(key):
                out[key] = chunk[len(key) :].strip()
                break
    return out


STATUS_ROW = re.compile(
    r"^\|\s*\*\*(?P<key>Phase|Next action|Lessons queue|Carried repairs)\*\*\s*\|"
    r"\s*(?P<value>.+?)\s*\|\s*$"
)

#: The phase a string *declares*, by its leading `Phase <n>`. `docs/internal/lessons.md` L8.1: the
#: Status cell is prose that legitimately mentions other phases, so only the one it opens with is a
#: claim about where the project is.
PHASE_IN_STATUS = re.compile(r"Phase\s+(?P<number>\d+)")

#: `docs/internal/lessons.md` L8.15. The queue's depth was stated by hand in a prose cell and was
#: wrong in both directions — stale before anyone touched it, and wrong again after arithmetic was
#: done on it rather than a count. It gets its own row so it can be parsed structurally rather than
#: grepped out of a sentence, which is the "test of prose" shape this repository already refuses
#: elsewhere.
QUEUE_DEPTH_IN_STATUS = re.compile(r"^(?P<count>\d+)\b")

#: The ledger task `docs/internal/README.md`'s Next action row points at — the row that outranks
#: ledger order, so it is what the Status phase must agree with. See `live_checks`.
#:
#: **The delimiter class is the whole repair, 2026-09-07 (`docs/internal/lessons.md` L10.7).** This
#: pattern allowed bold (`task **9.14**`) and bare (`task 9.14`) and not backticks, and every
#: Next action row this project has ever written spells the identifier in backticks — twelve
#: consecutive revisions of `docs/internal/README.md` checked, twelve no-matches. So the branch
#: `live_checks` calls "the whole question" had never once run against the live document: the
#: comparison silently fell back to ledger order, which that function's own comment says
#: "fails on a correct tree". It went unnoticed because falling back agreed by coincidence
#: while the Next action row happened to point inside the same phase the first unticked box
#: was in. A regex is a claim about a document's shape and is checked against the document.
NEXT_ACTION_TASK = re.compile(r"[Tt]ask\s+[*`]{0,2}(?P<identifier>\d+\.\d+)")

#: A **carried repair** the Next action row may point at instead of a task —
#: `build-ledger.md` → *Carried repairs*, whose own heading says they are "owned by no phase's
#: content". Added 2026-09-10 at Phase 11's close, the first time the project's position was a
#: repair rather than a task: every phase in the plan was closed, and the check refused the
#: Status block because it fell back to ledger order and found the first unticked box three
#: phases behind. A routing target this ledger has always had, that this script could not name.
#: The carried repair — or **group** of them — a Next action row names. `docs/internal/lessons.md`
#: `L12.10`: the singular form matched nothing the day the remaining backlog stopped being a
#: list and became four groups, so a row reading "Carried repairs `R9.4` and `R9.6` together"
#: fell through to ledger order and reported the Status block as disagreeing with the ledger.
#: The fix is to widen the vocabulary rather than to reword the plan to fit it.
#:
#: Anchored on the word and then consuming only a *run* of ids joined by punctuation and the
#: words that join a list — never every `R\d+\.\d+` in the cell, which would collect one
#: mentioned later in prose (this row routinely explains why some other repair is closed) and
#: fail on a correct tree, the loosening `_phase_agreement_failures` above records as how a
#: check earns the slack that then hides real drift.
NEXT_ACTION_REPAIR = re.compile(r"[Rr]epairs?\s+[*`]{0,2}(?P<identifier>R\d+\.\d+)")

#: One more id in the same named group: `, `R9.6`` / ` and `R9.6`` / ` together with `R9.6``.
#: No `\G` — Python's `re` has none; `named_repairs` calls `.match(text, position)`, which
#: anchors at exactly that offset and is what makes the run contiguous.
NEXT_ACTION_REPAIR_MORE = re.compile(
    r"[*`]{0,2}(?:\s*(?:,|and|together with|taken together with)\s*)+[*`]{0,2}"
    r"(?P<identifier>R\d+\.\d+)"
)

#: The Status block's **Carried repairs** row must open with its two cardinalities.
#: `docs/internal/lessons.md` `L12.2`: the Blocked-by row said "three carried repairs are open"
#: about a section holding nineteen, and the row it replaced was wrong the same way — each author
#: listing what they happened to be holding. Nobody had ever measured it. A row of its own, opening
#: with the numbers, is the shape the lessons-queue depth already uses, and that is the one
#: cardinality in this file that has never been wrong twice.
REPAIR_COUNTS_IN_STATUS = re.compile(r"^(?P<open>\d+)\s+open,\s*(?P<closed>\d+)\s+closed\b")

#: One carried-repair line, ticked or not — `- [ ] **R11.6** …`. `TASK_ID` deliberately does not
#: match these (its id is `\d+(\.\d+)?`), so they are parsed here and nowhere else.
REPAIR_LINE = re.compile(r"^- \[([ xX])\]\s+\*\*(?P<identifier>R\d+\.\d+)\*\*", re.MULTILINE)

#: One `### L<id> — <title>` entry in `docs/internal/lessons.md`'s own `## Queue` section — the
#: identical shape `.claude/hooks/lessons_context.py` counts, so the two cannot disagree about what
#: an entry is.
QUEUE_ENTRY = re.compile(r"^### (L[\d.]+) — ", re.MULTILINE)


def queue_section(lessons: Path) -> str:
    """The text of `docs/internal/lessons.md`'s own `## Queue` section, and nothing after it.

    `docs/internal/lessons.md` L8.15. Bounded at the next `## ` heading exactly the way
    `.claude/hooks/lessons_context.py` bounds it, so the two readers of this file cannot
    disagree about which entries are open. Returns `""` for a file with no Queue heading —
    the caller then counts zero and the assertion says so, rather than this raising.
    """
    try:
        text = lessons.read_text(encoding="utf-8")
    except OSError:
        return ""
    start = text.find("## Queue")
    if start == -1:
        return ""
    rest = text[start + len("## Queue") :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def status_block(readme: Path) -> dict[str, str]:
    """Pull `Phase` and `Next action` out of `docs/internal/README.md`'s Status table.

    Ledger order is the default; that table is where the project says otherwise, and right now it
    does — Phase 6's row reorders four tasks around a dependency the ledger's own sequence cannot
    express. Printing it beside the task is what stops the override from depending on someone
    remembering to go and read it.

    A missing or renamed table is not an error: the caller prints what it got and the rest of the
    report stands. Silence here would be the worse failure, so an empty result is reported as one.
    """
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return {}
    found: dict[str, str] = {}
    for line in text.splitlines():
        row = STATUS_ROW.match(line)
        if row and row.group("key") not in found:
            found[row.group("key")] = row.group("value")
    return found


def last_unticked_in_phase(tasks: list[Task], index: int) -> bool:
    """Is `tasks[index]` the last unticked task of its phase?

    This is the phase-close signal. `phase-step` → *Close the phase* fires on it, so that the
    boundary work — the whole-phase quality reading, draining the lessons queue
    — is reached by a detected condition rather than by someone remembering that a phase ended.
    That is the failure `.claude/hooks/lessons_context.py` already exists to prevent, applied one
    level up.

    Ticked tasks after this one do not count: a phase whose tail was closed out of order is still
    finished when nothing unticked remains in it.
    """
    phase = tasks[index].phase
    return not any(t.phase == phase and not t.checked for t in tasks[index + 1 :])


def find_ledger(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs" / "internal" / "build-ledger.md"
        if candidate.is_file():
            return candidate
    return Path("docs/internal/build-ledger.md")


def named_repairs(next_action: str) -> list[str]:
    """Every carried repair the Next action row names *as its subject* — `docs/internal/lessons.md`
    L12.10.

    One id, or a group: "Carried repairs `R9.4` and `R9.6` together", "Carried repair `R9.4`,
    taken together with `R9.6`". The run is consumed from the anchor forward, so an id mentioned
    later in the cell's prose — this row routinely explains why some *other* repair closed — is
    not collected and cannot fail a correct tree.
    """
    first = NEXT_ACTION_REPAIR.search(next_action)
    if first is None:
        return []
    found = [first.group("identifier")]
    position = first.end()
    while True:
        more = NEXT_ACTION_REPAIR_MORE.match(next_action, position)
        if more is None:
            return found
        found.append(more.group("identifier"))
        position = more.end()


def _repair_count_failures(path: Path, status: dict[str, str]) -> list[str]:
    """Does the Status block's stated repair tally equal the ledger's own two counts?

    `docs/internal/lessons.md` `L12.2`. The Blocked-by row said *"three carried repairs are open"*
    about a section holding **nineteen** — the three that session had touched — and the row it
    replaced was wrong in the same direction. Each author listed what they were holding; nobody had
    ever run the count. This is `_queue_depth_failures`'s shape applied to the other cardinality
    this file states, and that one has never been wrong twice.
    """
    failures: list[str] = []
    if "Carried repairs" not in status:
        failures.append(
            "the Status block has no 'Carried repairs' row — the open and closed counts are "
            "counts of docs/internal/build-ledger.md, and writing them into prose from memory is "
            "what"
            "L12.2 was paid for"
        )
        return failures
    declared = REPAIR_COUNTS_IN_STATUS.match(status["Carried repairs"].strip())
    if declared is None:
        failures.append(
            f"the Status block's 'Carried repairs' row must open '<n> open, <n> closed', got "
            f"{status['Carried repairs'][:60]!r}"
        )
        return failures
    text = find_ledger(None).read_text(encoding="utf-8")
    states = [match.group(1).strip() for match in REPAIR_LINE.finditer(text)]
    counted_open = sum(1 for state in states if not state)
    counted_closed = sum(1 for state in states if state)
    if int(declared.group("open")) != counted_open:
        failures.append(
            f"Status says {declared.group('open')} carried repair(s) are open and the ledger "
            f"holds {counted_open} unticked — the number is a count of that file (L12.2)"
        )
    if int(declared.group("closed")) != counted_closed:
        failures.append(
            f"Status says {declared.group('closed')} carried repair(s) are closed and the "
            f"ledger holds {counted_closed} ticked — the number is a count of that file (L12.2)"
        )
    return failures


def _documents_manifest_failures(path: Path) -> list[str]:
    """Does `docs/internal/README.md`'s Documents manifest name every numbered document on disk?

    `docs/internal/lessons.md` `L12.14`. Asked which phases the project has, I grepped two documents
    chosen from memory, got a correct answer to the wrong question, and said there was no roadmap
    past Phase 11 while `docs/internal/12-roadmap.md` sat tracked and **routed from that very
    manifest**. The manifest was right; I had read the Status block above it all session and never
    the routing half below.

    This could not have caught that — the row was there. What it protects is the router itself:
    a manifest with a hole in it makes "read the manifest and pick the row" wrong advice, and
    the hole is invisible to everyone who already knows what is missing.
    """
    docs = path.parent
    try:
        manifest = (docs / "README.md").read_text(encoding="utf-8")
    except OSError:
        return [
            "docs/internal/README.md could not be read, so its Documents manifest was not checked"
        ]
    on_disk = {candidate.name for candidate in docs.glob("[0-9][0-9]-*.md")}
    missing = sorted(name for name in on_disk if name not in manifest)
    if missing:
        return [
            "docs/internal/README.md's Documents manifest names no row for "
            + ", ".join(missing)
            + " — it is the half of that file that answers *which document owns this question*, "
            "and a document absent from it is reachable only by recall (L12.14)"
        ]
    return []


def _repair_failures(identifier: str) -> list[str]:
    """Does the carried repair the Next action names exist, and is it still open?

    A Next action pointing at a repair that is already ticked is `L11.14`'s defect in the other
    kind of target: the row names something done, and a reader routed by it starts on finished
    work. A repair the ledger does not hold at all is a pointer nobody can follow.
    """
    text = find_ledger(None).read_text(encoding="utf-8")
    for state, found in ((m.group(1), m.group("identifier")) for m in REPAIR_LINE.finditer(text)):
        if found != identifier:
            continue
        if state.strip():
            return [
                f"the Status block's Next action row points at carried repair {identifier!r}, "
                f"and that repair is already ticked in the ledger"
            ]
        return []
    return [
        f"the Status block's Next action row points at carried repair {identifier!r}, which "
        f"appears in no carried-repair line of the ledger"
    ]


def _phase_agreement_failures(
    tasks: list[Task], task: Task | None, status: dict[str, str]
) -> list[str]:
    """Does the Status block's declared phase agree with the task it points at?

    Extracted from `live_checks` when that function crossed ruff's complexity ceiling — the two
    clauses below and `_queue_depth_failures` are each a whole question, and a function holding
    every question this script asks is one nobody reads before adding the next.

    **`task is None` when every box is ticked** — `L17.6`. There is then no live task to agree
    with, so the Status block's own *Next action* row is still read (it may point at a task that
    exists, which is checkable), and the phase-number comparison is skipped rather than crashing.
    Found by running `--check-live` immediately after the repair that introduced this case, which
    is the repair's own argument working on itself.
    """
    failures: list[str] = []
    stated = status.get("Phase", "")
    if stated:
        # `docs/internal/lessons.md` L8.1, and this is the third defect in this one comparison
        # (L6.3, L6.4 are the other two). It read `... not in stated` — containment over
        # the whole free-text cell — so it agreed whenever the *prose* happened to mention
        # the other phase's name. That is not hypothetical: the live Status row says
        # "Phase 8 ... It runs before Phase 7, which G12 still gates", the first unticked
        # task is 7.1, and containment reported agreement on a tree where the two are
        # deliberately different. Compare the phase the cell *declares* — the first
        # `Phase <n>` it names — against the one the ledger gives, by equality.
        # **Which task the Status phase is compared against is the whole question**, and
        # getting it wrong is why the old check was written loosely enough to pass. Ledger
        # order is only the default: `docs/internal/README.md`'s own Next action row is documented
        # as outranking it, and it is doing that right now — Phase 8 runs *before* Phase 7,
        # which G12 still gates. So the first unticked ledger task is the wrong subject; a
        # comparison against it fails on a correct tree, which is how a check earns a
        # loosening that then hides real drift. Compare against the task the Next action
        # row actually names, and fall back to ledger order only when it names none.
        next_action = status.get("Next action", "")
        # **A repair is a legitimate destination and belongs to no phase**, so naming one
        # settles this question rather than deferring it: there is nothing to compare a phase
        # against. What is checked instead is that the repair exists and is still open — the
        # same property the task branch checks, asked of the other kind of target.
        repairs = named_repairs(next_action)
        if repairs:
            for identifier in repairs:
                failures.extend(_repair_failures(identifier))
            return failures
        pointed = NEXT_ACTION_TASK.search(next_action)
        subject = task
        if pointed is not None:
            named = next((t for t in tasks if t.identifier == pointed.group("identifier")), None)
            if named is None:
                failures.append(
                    f"the Status block's Next action row points at task "
                    f"{pointed.group('identifier')!r}, which is in no phase of the ledger"
                )
            else:
                subject = named
        declared = PHASE_IN_STATUS.search(stated)
        wanted = PHASE_IN_STATUS.search(subject.phase) if subject is not None else None
        if declared is None:
            failures.append(
                f"the Status block's Phase row names no phase at all: {stated[:80]!r}… — "
                f"it must open with the phase it is claiming, e.g. '**Phase 8 — ...**'"
            )
        elif wanted is not None and declared.group("number") != wanted.group("number"):
            failures.append(
                f"Status declares Phase {declared.group('number')} and the task it "
                f"points at ({subject.identifier}) is in {subject.phase!r} — one of the "
                f"two is stale, and the ledger cannot tell you which"
            )
    return failures


def _queue_depth_failures(path: Path, status: dict[str, str]) -> list[str]:
    """Does the Status block's stated queue depth equal the count of `lessons.md`'s own Queue?"""
    failures: list[str] = []
    # `docs/internal/lessons.md` L8.15. The depth is a count of a file, so a human-written number
    # is a second source that drifts — it was stale before this session and wrong again
    # after somebody (me) did arithmetic on it instead of counting. Parsed from its own
    # row rather than grepped out of the Next action prose, because a check that hunts a
    # number out of free text passes the moment somebody writes a plausible sentence.
    if "Lessons queue" not in status:
        failures.append(
            "the Status block has no 'Lessons queue' row — the queue's depth is a count of "
            "docs/internal/lessons.md, and stating it in prose is what L8.15 was paid for"
        )
    else:
        declared_depth = QUEUE_DEPTH_IN_STATUS.match(status["Lessons queue"].strip())
        counted = len(QUEUE_ENTRY.findall(queue_section(path.parent / "lessons.md")))
        if declared_depth is None:
            failures.append(
                f"the Status block's 'Lessons queue' row must open with the number of open "
                f"entries, got {status['Lessons queue'][:60]!r}"
            )
        elif int(declared_depth.group("count")) != counted:
            failures.append(
                f"Status says the lessons queue holds {declared_depth.group('count')} and "
                f"docs/internal/lessons.md's own '## Queue' section holds {counted} — the number "
                f"is"
                f"a count of that file, never a figure carried forward (L8.15)"
            )
    return failures


def live_checks(
    path: Path,
    tasks: list[Task],
    phases: dict[str, Phase],
    task: Task | None,
    status: dict[str, str],
) -> list[str]:
    """Assertions only the **live** tree can falsify — the half a fixture cannot reach.

    `self_test()` below runs against `SELF_TEST`, a synthetic ledger, and that is the right subject
    for the parser: it can plant the fenced-shape trap and watch it caught. What a fixture
    structurally cannot catch is an input the script never reads at all, because the fixture does
    not have that input either. Both of this script's known defects were exactly that shape
    (`docs/internal/lessons.md` L6.3, L6.4): the first rewrite computed the next task from
    `build-ledger.md` alone and never opened `docs/internal/README.md`, so the Status block's own
    **Next action** row — where the project overrides ledger order — was silently dropped, and a
    fixture-only self-test reported everything fine.

    So these run against the real `docs/internal/README.md` and the real
    `docs/internal/build-ledger.md`, two files that can genuinely disagree (`L5.6` — a check whose
    two sides come from one source cannot fail), and they run on **every invocation** rather than
    behind a flag someone has to remember, which is `CLAUDE.md`'s own "cross-cutting concerns live
    at the registration seam" applied to this skill's own tooling. `--check-live` only changes the
    exit code.
    """
    failures: list[str] = []

    # The floor. A walk that silently found nothing must not pass by having nothing to check.
    if not tasks:
        failures.append("no task lines parsed from the live ledger at all")
        return failures

    # L6.3's own defect, made checkable: the Status block is an input this script must read.
    if not status:
        failures.append(
            f"no Status block read from {path.parent / 'README.md'} — ledger order is only the "
            f"default, and that table is where the project overrides it"
        )
    else:
        for row in ("Phase", "Next action"):
            if row not in status:
                failures.append(f"the Status block has no {row!r} row — it may have been renamed")
        failures.extend(_phase_agreement_failures(tasks, task, status))
        failures.extend(_queue_depth_failures(path, status))
        failures.extend(_repair_count_failures(path, status))
    failures.extend(_documents_manifest_failures(path))

    # L6.4's own defect, made checkable. A mark is only readable when the phase preamble says
    # what happened to the gate behind it; without that, a reader can only guess whether a
    # provisional task is blocked or is carrying a record of a gate that has since closed.
    # `task is None` at a phase close, when every box is ticked — `L17.6`. The mark check is
    # keyed on the live task's phase and has nothing to key on; every check above it is about
    # the ledger and the Status block and runs regardless.
    provisional = (
        []
        if task is None
        else [t.identifier for t in tasks if t.phase == task.phase and t.provisional]
    )
    if provisional and task is not None:
        phase = phases.get(task.phase)
        preamble = "\n".join(line for _n, line in (phase.preamble if phase else []))
        if PROVISIONAL not in preamble:
            failures.append(
                f"{task.phase} carries {len(provisional)} provisional task(s) "
                f"({', '.join(provisional)}) and its preamble never mentions {PROVISIONAL} — "
                f"so nothing says whether those gates are open or are closed and recorded"
            )
    return failures


def report(path: Path, as_json: bool) -> int:
    try:
        ledger = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read the ledger at {path}: {exc}", file=sys.stderr)
        return 3

    tasks, phases = parse(ledger)
    if not tasks:
        print(f"no task lines parsed out of {path} — has the line format changed?", file=sys.stderr)
        return 3

    index = next((i for i, t in enumerate(tasks) if not t.checked), None)
    if index is None:
        print("every box in the ledger is ticked.")
        return 2

    task = tasks[index]
    following = tasks[index + 1] if index + 1 < len(tasks) else None
    blocked = phases[task.phase].blocked_lines if task.phase in phases else []
    closes_phase = last_unticked_in_phase(tasks, index)
    status = status_block(path.parent / "README.md")

    if as_json:
        print(
            json.dumps(
                {
                    "ledger": str(path),
                    "phase": task.phase,
                    "blocked_preamble_lines": [{"line": n, "text": t} for n, t in blocked],
                    "closes_the_phase": closes_phase,
                    "status_block": status or None,
                    "live_check_failures": live_checks(path, tasks, phases, task, status),
                    "task": _as_dict(task),
                    "next_task": _as_dict(following) if following else None,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 1 if blocked else 0

    _print_task(path, task, following)
    _print_status(status, task)
    _print_live_checks(live_checks(path, tasks, phases, task, status))

    if closes_phase:
        print(f"\n\u2691 last unticked task in {task.phase}.")
        print("  When it closes, run phase-step \u2192 *Close the phase* before the next one.")
    if blocked:
        print(f"\n{BLOCKED} the phase preamble carries a block. Read these and decide:")
        for n, line in blocked:
            print(f"  {path}:{n}  {line}")
        return 1
    return 0


def _print_task(path: Path, task: Task, following: Task | None) -> None:
    """The task itself: where it is, what it makes true, and what comes after it."""
    print(f"{path}:{task.lineno}")
    print(f"phase   {task.phase}")
    print(f"task    {task.identifier}{'  (PROVISIONAL)' if task.provisional else ''}")
    print(f"makes true\n        {task.property_sentence}")
    for key in ("owner", "turns on"):
        if key in task.fields:
            print(f"{key:<9}{task.fields[key]}")
    if following:
        print(f"\nnext    {following.identifier}  {following.property_sentence}")
        print("        (read it — it often shows what this task has to leave room for)")


def _print_status(status: dict[str, str], task: Task) -> None:
    """`docs/internal/README.md`'s own position, which outranks ledger order — see `live_checks`."""
    if "Next action" in status:
        print("\nthe project's own next action — this outranks ledger order:")
        for chunk in _wrap(status["Next action"]):
            print(f"  {chunk}")
        stated = status.get("Phase", "")
        if stated and task.phase.split("—")[0].strip() not in stated:
            print(f"  ⚠ Status says {stated!r}; the next task is in {task.phase!r}. One is stale.")
    elif not status:
        print(
            "\n(no Status block read from docs/internal/README.md — check its Next action row by "
            "hand)"
        )


def _print_live_checks(problems: list[str]) -> None:
    """What the plan and the tree disagree about, if anything — see `live_checks`."""
    if not problems:
        return
    print("\n\u2717 live check — the plan and this script disagree about the tree as it stands:")
    for problem in problems:
        for chunk in _wrap(problem):
            print(f"  {chunk}")
    print("  Fix the document, not the reading. Ledger order is the default; the Status")
    print("  block is where the project overrides it, and a stale one misroutes the phase.")


def _wrap(text: str, width: int = 94) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def _as_dict(task: Task) -> dict[str, object]:
    return {
        "id": task.identifier,
        "line": task.lineno,
        "provisional": task.provisional,
        "makes_true": task.property_sentence,
        "owner": task.fields.get("owner"),
        "turns_on": task.fields.get("turns on"),
    }


SELF_TEST = f"""\
## How to read a task line

```
- [ ] **9.0 {PROVISIONAL}** the shape, not a real task · owner `02` · turns on — · sha —
```

## Phase 9 — A blocked phase

{BLOCKED} Blocked by G99 — the thing nobody settled.

- [x] **9.1** a done thing · owner `01` · turns on — · sha `abc1234`
- [ ] **9.2 {PROVISIONAL}** a wrapped property that continues
  onto a second line · owner `03` · turns on FF11 · sha —
- [ ] **9.3** the one after · owner `04` · turns on — · sha —
"""


def _fixture_failures(
    tasks: list[Task], phases: dict[str, Phase], first_unticked: Task, ids: list[str]
) -> list[str]:
    """Every way the fixture parse came out wrong — collected, not raised on the first one.

    A parser check that stops at its first disagreement tells you one thing per run; this one
    tells you all of them, which is what makes a broken change cheap to read rather than a
    sequence of single-fact runs.
    """
    failures: list[str] = []
    if "9.0" in ids:
        failures.append("the fenced shape line was parsed as a real task")
    if ids != ["9.1", "9.2", "9.3"]:
        failures.append(f"expected 9.1/9.2/9.3, parsed {ids}")
    if first_unticked.identifier != "9.2":
        failures.append(f"first unticked is {first_unticked.identifier}, expected 9.2")
    if "onto a second line" not in first_unticked.property_sentence:
        failures.append("the wrapped continuation line was not joined back on")
    if first_unticked.fields.get("turns on") != "FF11":
        failures.append(f"turns on parsed as {first_unticked.fields.get('turns on')!r}")
    if not first_unticked.provisional:
        failures.append("the provisional mark was not read")
    phase = phases.get(first_unticked.phase)
    if phase is None or not phase.blocked_lines:
        failures.append("the blocked preamble line was not seen")
    del tasks
    return failures


def _live_check_failures(
    tasks: list[Task], phases: dict[str, Phase], first_unticked: Task
) -> list[str]:
    """Prove `live_checks` can both fire and stay quiet, against the fixture.

    Added after an adversarial review pointed out that `self_test` covered `parse()` thoroughly and
    asserted **nothing** about `live_checks` — the function this script gained specifically to catch
    `docs/internal/lessons.md` L6.3 and L6.4. A regression reintroducing the exact defect it was
    written for would have left `--self-test` printing "ok", which is the false confidence L5.19
    forbids in as many words. Both directions are asserted here, because a check that only ever
    fires and a check that never fires are equally useless.

    The fixture's own phase carries a provisional task and a preamble with no ⚠ in it, so the
    provisional clause fires on it as written — which is what makes the negative case below
    (the same call with a ⚠ added to the preamble) a real second reading rather than a repeat.
    """
    failures: list[str] = []
    path = Path("docs/internal/build-ledger.md")

    fired = live_checks(path, tasks, phases, first_unticked, {})
    if not any("no Status block read" in f for f in fired):
        failures.append("live_checks stayed silent about an unreadable Status block")
    if not any("provisional task" in f for f in fired):
        failures.append("live_checks stayed silent about a ⚠ its preamble never explains")

    # The queue-depth clause reads the real `docs/internal/lessons.md`, so the fixture states
    # whatever that file currently holds — the assertion under test is *agreement*, not a number,
    # and hard-coding one here would be the second hand-written count `L8.15` is about.
    live_depth = len(QUEUE_ENTRY.findall(queue_section(path.parent / "lessons.md")))
    #: Same reasoning one row over (`L12.2`): the clause reads the real ledger, so the fixture
    #: states whatever that file currently holds and the assertion under test is agreement.
    live_states = [m.group(1).strip() for m in REPAIR_LINE.finditer(path.read_text("utf-8"))]
    live_open = sum(1 for state in live_states if not state)
    live_closed = sum(1 for state in live_states if state)
    agreeing = {
        "Phase": first_unticked.phase,
        "Next action": f"carry on with task {first_unticked.identifier}",
        "Lessons queue": f"{live_depth} — counted, not stated",
        "Carried repairs": f"{live_open} open, {live_closed} closed — counted, not stated",
    }
    phase = phases.get(first_unticked.phase)
    explained = dict(phases)
    if phase is not None:
        explained[first_unticked.phase] = Phase(
            title=phase.title,
            lineno=phase.lineno,
            preamble=[*phase.preamble, (0, f"every {PROVISIONAL} here has a closed gate")],
        )
    quiet = live_checks(path, tasks, explained, first_unticked, agreeing)
    if quiet:
        failures.append(f"live_checks fired on a tree it should have passed: {quiet}")

    stale = live_checks(path, tasks, explained, first_unticked, {**agreeing, "Phase": "Phase 0"})
    if not any("stale" in f for f in stale):
        failures.append("live_checks stayed silent about a Status phase that disagrees")

    # `docs/internal/lessons.md` L8.1, planted. The old comparison was `not in stated` — containment
    # over the whole cell — so a Status row whose *prose* mentioned another phase agreed with it.
    # This is that exact shape: the cell declares one phase and names a different one in passing,
    # and the check must read the declaration, not the mention.
    mentioning = {
        **agreeing,
        "Phase": f"**Phase 0 — something else**, which runs before {first_unticked.phase}",
    }
    substring = live_checks(path, tasks, explained, first_unticked, mentioning)
    if not any("stale" in f for f in substring):
        failures.append(
            "live_checks agreed with a Status row that merely mentions the right phase while "
            "declaring a different one — L8.1's own defect, reintroduced"
        )

    # `docs/internal/lessons.md` L8.15, planted both ways: a missing row, and a number that
    # disagrees.
    missing_row = live_checks(
        path,
        tasks,
        explained,
        first_unticked,
        {k: v for k, v in agreeing.items() if k != "Lessons queue"},
    )
    if not any("Lessons queue" in f for f in missing_row):
        failures.append("live_checks stayed silent about a Status block with no queue-depth row")

    wrong_count = live_checks(
        path,
        tasks,
        explained,
        first_unticked,
        {**agreeing, "Lessons queue": f"{live_depth + 7} entries"},
    )
    if not any("lessons queue holds" in f for f in wrong_count):
        failures.append(
            "live_checks stayed silent about a queue depth that disagrees with the file"
        )

    failures.extend(_repair_clause_failures(path, tasks, explained, first_unticked, agreeing))
    return failures


def _repair_clause_failures(
    path: Path,
    tasks: list[Task],
    explained: dict[str, Phase],
    first_unticked: Task,
    agreeing: dict[str, str],
) -> list[str]:
    """The two Phase 12 clauses, planted — `L12.2`'s tally and `L12.10`'s group.

    Split out of `_live_check_failures` rather than appended to it, for the reason that
    function's own header already gives: each clause is a whole question, and a function holding
    every question this script asks is one nobody reads before adding the next. `ruff` said so
    first, at complexity 13.
    """
    failures: list[str] = []
    live_states = [m.group(1).strip() for m in REPAIR_LINE.finditer(path.read_text("utf-8"))]
    live_open = sum(1 for state in live_states if not state)

    # `docs/internal/lessons.md` L12.2, planted both ways, exactly as L8.15 is planted above — the
    # cardinality this file got wrong by sixteen, and the reason it now has a row of its own.
    without_row = {k: v for k, v in agreeing.items() if k != "Carried repairs"}
    no_repair_row = live_checks(path, tasks, explained, first_unticked, without_row)
    if not any("Carried repairs" in f for f in no_repair_row):
        failures.append("live_checks stayed silent about a Status block with no repair-count row")

    disagreeing = dict(agreeing)
    disagreeing["Carried repairs"] = re.sub(
        r"^\d+", str(live_open + 5), disagreeing["Carried repairs"]
    )
    wrong_repairs = live_checks(path, tasks, explained, first_unticked, disagreeing)
    if not any("carried repair(s) are open" in f for f in wrong_repairs):
        failures.append(
            "live_checks stayed silent about an open-repair count that disagrees with the ledger"
        )

    # `docs/internal/lessons.md` L12.10: a Next action naming a *group* must route, and an id merely
    # mentioned in the cell's prose must not be collected into it.
    group = named_repairs("**Carried repairs `R9.4` and `R9.6` together** — one cause.")
    if group != ["R9.4", "R9.6"]:
        failures.append(f"a Next action naming a group of repairs parsed as {group}")
    mentioned = named_repairs("**Carried repair `R9.1`.** Note `R11.6` closed, which is why.")
    if mentioned != ["R9.1"]:
        failures.append(f"a repair mentioned in passing was collected into the group: {mentioned}")
    return failures


def self_test() -> int:
    """Prove the parse can tell the fenced shape from a real task, and that it can fail.

    `CLAUDE.md` → *Quality gates*: a check nobody has watched fail is not evidence. The planted
    disagreement here is the fenced `N.M` line — the exact trap this script exists for.
    """
    tasks, phases = parse(SELF_TEST)
    ids = [t.identifier for t in tasks]

    first_unticked = next((t for t in tasks if not t.checked), None)
    if first_unticked is None:
        print("FAIL  nothing unticked in the fixture — the parse found no work at all")
        return 3

    failures = _fixture_failures(tasks, phases, first_unticked, ids)
    failures += _live_check_failures(tasks, phases, first_unticked)

    # 9.2 has 9.3 unticked behind it; 9.3 is the phase's last. Both directions, so neither a
    # hardwired True nor a hardwired False would pass.
    if last_unticked_in_phase(tasks, ids.index("9.2")):
        failures.append("9.2 was called the phase's last, but 9.3 is still unticked behind it")
    if not last_unticked_in_phase(tasks, ids.index("9.3")):
        failures.append("9.3 is the phase's last unticked task and was not reported as one")

    for line in failures:
        print(f"FAIL  {line}")
    if failures:
        return 3
    print(
        "self-test ok — fenced shape ignored, wrap joined, fields and marks read, block "
        "seen, and live_checks watched both firing and staying quiet."
    )
    return 0


def check_live(path: Path) -> int:
    """`live_checks` as a pass/fail gate rather than a warning printed beside the task.

    `report()` already runs the same assertions on every invocation — nobody has to remember
    this flag for the checks to happen. What the flag adds is an exit code, so the pairing can
    be asserted from somewhere other than a person reading the output: a phase close, a commit
    hook, or `phase-step` → *Close the phase*, which is where a stale Status block does the
    most damage because the next phase is about to be routed off it.
    """
    try:
        ledger = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"cannot read the ledger at {path}: {exc}", file=sys.stderr)
        return 3
    tasks, phases = parse(ledger)
    index = next((i for i, t in enumerate(tasks) if not t.checked), None)
    if index is None:
        # **`L17.6`: this returned 0 by having nothing to check, which is exactly when it is
        # asked.** `phase-step` -> *Close the phase* runs `--check-live` at a phase close — the
        # moment every box in the phase has just been ticked — so the one invocation the
        # instruction exists for was the one guaranteed to be vacuous. The checks that do not
        # need a live task run anyway; only the ones keyed on it are skipped, and the skip is
        # said out loud rather than reported as a pass.
        status = status_block(path.parent / "README.md")
        problems = live_checks(path, tasks, phases, None, status)
        for problem in problems:
            print(f"FAIL  {problem}")
        if problems:
            return 1
        print(
            "every box is ticked, so the checks keyed on a live task did not run; "
            "the Status block and the phase marks were checked and hold."
        )
        return 0
    status = status_block(path.parent / "README.md")
    problems = live_checks(path, tasks, phases, tasks[index], status)
    for problem in problems:
        print(f"FAIL  {problem}")
    if problems:
        return 3
    # Name the task actually compared against, not the first unticked one. `live_checks` reads the
    # Status block's own Next action row and compares the phase against *that* task, because that
    # row outranks ledger order — so a message naming `tasks[index]` describes a comparison this
    # script did not make. `docs/internal/lessons.md` L8.1 was a comparison that agreed for the
    # wrong reason; a success line that misreports its own subject is the same defect one layer out,
    # and it is the line a reader trusts when deciding not to look further. **And the message says
    # which of the three subjects it actually used.** A Next action may name a task, a carried
    # repair (which belongs to no phase, so there is no phase comparison to report), or nothing at
    # all — and printing the task-shaped sentence for all three is the same defect this comment's
    # own paragraph describes, one case wider. Added 2026-09-10 with the repair branch, after the
    # first version of it printed "its phase agrees with 9.15 (the task its own Next action row
    # names)" about a row naming `R11.6` and no task whatever.
    next_action = status.get("Next action", "")
    repairs = named_repairs(next_action)
    pointed = NEXT_ACTION_TASK.search(next_action)
    queue_depth = len(QUEUE_ENTRY.findall(queue_section(path.parent / "lessons.md")))
    if repairs:
        subject = (
            f"its Next action row names carried repair{'s' if len(repairs) > 1 else ''} "
            f"{', '.join(repairs)}, which belong{'' if len(repairs) > 1 else 's'} to no phase "
            f"and {'are' if len(repairs) > 1 else 'is'} open, so no phase comparison was owed"
        )
    elif pointed is not None:
        subject = f"its phase agrees with {pointed.group('identifier')}, the task that row names"
    else:
        subject = (
            f"its Next action row names neither a task nor a repair, so the phase was compared "
            f"against ledger order — {tasks[index].identifier}"
        )
    print(
        f"live check ok — Status block read, {subject}, the lessons queue holds "
        f"{queue_depth}, and every provisional mark in that phase is accounted for in the "
        f"preamble."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", help="path to build-ledger.md (default: found from this file)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--self-test", action="store_true", help="check the parser against a fixture"
    )
    parser.add_argument(
        "--check-live",
        action="store_true",
        help="exit non-zero if the live ledger and docs/internal/README.md disagree",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.check_live:
        return check_live(find_ledger(args.ledger))
    return report(find_ledger(args.ledger), args.json)


if __name__ == "__main__":
    sys.exit(main())
