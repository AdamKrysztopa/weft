#!/usr/bin/env python3
"""Print the first unticked task in `docs/build-ledger.md`, the task after it, and its gate state.

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
TASK_ID = re.compile(r"^\*\*(?P<id>[0-9]+(?:\.[0-9]+)?)\s*(?P<flag>[^*]*)\*\*\s*(?P<rest>.*)$")

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
        is_continuation = bool(stripped) and not stripped.startswith(("#", ">", "|", "-", "*"))
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


STATUS_ROW = re.compile(r"^\|\s*\*\*(?P<key>Phase|Next action)\*\*\s*\|\s*(?P<value>.+?)\s*\|\s*$")


def status_block(readme: Path) -> dict[str, str]:
    """Pull `Phase` and `Next action` out of `docs/README.md`'s Status table.

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
    boundary work — the whole-phase quality reading, the reference re-check, draining the lessons queue
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
        candidate = parent / "docs" / "build-ledger.md"
        if candidate.is_file():
            return candidate
    return Path("docs/build-ledger.md")


def live_checks(
    path: Path, tasks: list[Task], phases: dict[str, Phase], task: Task, status: dict[str, str]
) -> list[str]:
    """Assertions only the **live** tree can falsify — the half a fixture cannot reach.

    `self_test()` below runs against `SELF_TEST`, a synthetic ledger, and that is the right
    subject for the parser: it can plant the fenced-shape trap and watch it caught. What a
    fixture structurally cannot catch is an input the script never reads at all, because the
    fixture does not have that input either. Both of this script's known defects were exactly
    that shape (`docs/lessons.md` L6.3, L6.4): the first rewrite computed the next task from
    `build-ledger.md` alone and never opened `docs/README.md`, so the Status block's own
    **Next action** row — where the project overrides ledger order — was silently dropped,
    and a fixture-only self-test reported everything fine.

    So these run against the real `docs/README.md` and the real `docs/build-ledger.md`, two
    files that can genuinely disagree (`L5.6` — a check whose two sides come from one source
    cannot fail), and they run on **every invocation** rather than behind a flag someone has
    to remember, which is `CLAUDE.md`'s own "cross-cutting concerns live at the registration
    seam" applied to this skill's own tooling. `--check-live` only changes the exit code.
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
        stated = status.get("Phase", "")
        if stated and task.phase.split("\u2014")[0].strip() not in stated:
            failures.append(
                f"Status says Phase {stated!r} and the first unticked task is in {task.phase!r} "
                f"— one of the two is stale, and the ledger cannot tell you which"
            )

    # L6.4's own defect, made checkable. A mark is only readable when the phase preamble says
    # what happened to the gate behind it; without that, a reader can only guess whether a
    # provisional task is blocked or is carrying a record of a gate that has since closed.
    provisional = [t.identifier for t in tasks if t.phase == task.phase and t.provisional]
    if provisional:
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
    """`docs/README.md`'s own position, which outranks ledger order — see `live_checks`."""
    if "Next action" in status:
        print("\nthe project's own next action — this outranks ledger order:")
        for chunk in _wrap(status["Next action"]):
            print(f"  {chunk}")
        stated = status.get("Phase", "")
        if stated and task.phase.split("—")[0].strip() not in stated:
            print(f"  ⚠ Status says {stated!r}; the next task is in {task.phase!r}. One is stale.")
    elif not status:
        print("\n(no Status block read from docs/README.md — check its Next action row by hand)")


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

    Added after an adversarial review pointed out that `self_test` covered `parse()` thoroughly
    and asserted **nothing** about `live_checks` — the function this script gained specifically
    to catch `docs/lessons.md` L6.3 and L6.4. A regression reintroducing the exact defect it was
    written for would have left `--self-test` printing "ok", which is the false confidence L5.19
    forbids in as many words. Both directions are asserted here, because a check that only ever
    fires and a check that never fires are equally useless.

    The fixture's own phase carries a provisional task and a preamble with no ⚠ in it, so the
    provisional clause fires on it as written — which is what makes the negative case below
    (the same call with a ⚠ added to the preamble) a real second reading rather than a repeat.
    """
    failures: list[str] = []
    path = Path("docs/build-ledger.md")

    fired = live_checks(path, tasks, phases, first_unticked, {})
    if not any("no Status block read" in f for f in fired):
        failures.append("live_checks stayed silent about an unreadable Status block")
    if not any("provisional task" in f for f in fired):
        failures.append("live_checks stayed silent about a ⚠ its preamble never explains")

    agreeing = {"Phase": first_unticked.phase, "Next action": "carry on"}
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
        print("every box is ticked — nothing live to check against.")
        return 0
    status = status_block(path.parent / "README.md")
    problems = live_checks(path, tasks, phases, tasks[index], status)
    for problem in problems:
        print(f"FAIL  {problem}")
    if problems:
        return 3
    print(
        f"live check ok — Status block read, its phase agrees with {tasks[index].identifier}, "
        f"and every provisional mark in that phase is accounted for in the preamble."
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
        help="exit non-zero if the live ledger and docs/README.md disagree (see live_checks)",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.check_live:
        return check_live(find_ledger(args.ledger))
    return report(find_ledger(args.ledger), args.json)


if __name__ == "__main__":
    sys.exit(main())
