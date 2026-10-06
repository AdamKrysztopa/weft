#!/usr/bin/env python3
"""Sort `docs/internal/` into what is live, what is done, and what is only an idea.

Live work stays where it is. Finished work moves to `docs/internal/done/` and conditional or
unopened work to `docs/internal/ideas/`, each under the same file name it left, so a reader that
needs the whole record reads the live file plus its two namesakes (`next_task.full_text`).

    python3 .claude/skills/phase-step/scripts/sort_internal.py            # move, then _report
    python3 .claude/skills/phase-step/scripts/sort_internal.py --dry-run  # _report only

Idempotent: run it at every phase close. It moves whole units, never edits one:

- `build-ledger.md`: a `## Phase …` or `## Carried repairs …` section with no unticked box → done.
- `12-roadmap.md`: each §1 row by its status cell (DONE, CLOSED or declined → done; WON'T yet,
  COULD, SHOULD → ideas; anything else stays), each `## n · Phase X` section with its row, §0 and
  §8 → done, §6 and §7 → ideas.
- `05-grilling-sessions.md`: a `## G<n>` session whose decision-log row says Settled → done,
  Deferred → ideas; the Ordering section → done.
- `README.md` → *Execution path*: a `**Phase X — …**` block whose ledger section left → done.
- `fix-plans/NN-phase-<id>-*.md`: with its roadmap row.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

DONE = "done"
IDEAS = "ideas"
LIVE = "live"
BUCKETS = (DONE, IDEAS)

UNTICKED = re.compile(r"^\s*- \[ \] \*\*")
PHASE_ID = re.compile(r"\bPhase (\d+[a-z]?)\b")
ROW_ID = re.compile(r"^\| \*\*([0-9]+[a-z]?)\*\* \|")
LOG_ROW = re.compile(r"^\| \*\*(G\d+)\*\* \|(.*)$", re.MULTILINE)
ROADMAP_SECTION = re.compile(r"^## (\d+[a-z]*) · ")
FIX_PLAN_PHASE = re.compile(r"^[0-9]{2}-phase-([0-9]+[a-z]?)-")


@dataclass
class _Document:
    preamble: list[str]
    sections: list[list[str]] = field(default_factory=list)

    def render(self) -> str:
        lines = list(self.preamble)
        for section in self.sections:
            lines.extend(section)
        return "\n".join(lines).rstrip("\n") + "\n"


def _split_sections(text: str, prefix: str = "## ") -> _Document:
    """Split on headings starting with `prefix`, outside fenced blocks."""
    document = _Document(preamble=[])
    current = document.preamble
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith(prefix):
            current = [line]
            document.sections.append(current)
        else:
            current.append(line)
    return document


def _heading_key(section: list[str]) -> str:
    return section[0].strip()


def _has_unticked(section: list[str]) -> bool:
    in_fence = False
    for line in section:
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and UNTICKED.match(line):
            return True
    return False


@dataclass
class _Move:
    """What one run takes out of a live file, keyed by bucket."""

    keep: _Document
    moved: dict[str, list[list[str]]]


def _partition(document: _Document, classify) -> _Move:
    keep = _Document(preamble=document.preamble)
    moved: dict[str, list[list[str]]] = {bucket: [] for bucket in BUCKETS}
    for section in document.sections:
        bucket = classify(section)
        if bucket == LIVE:
            keep.sections.append(section)
        else:
            moved[bucket].append(section)
    return _Move(keep=keep, moved=moved)


def _bucket_header(name: str, bucket: str) -> list[str]:
    what = "finished" if bucket == DONE else "conditional or not yet opened"
    return [
        f"# {name} — {bucket}",
        "",
        f"The {what} half of `docs/internal/{name}`, moved there unedited by",
        "`.claude/skills/phase-step/scripts/sort_internal.py`. The live file holds the rest.",
        "",
    ]


def _merge_sections(
    root: Path, name: str, moved: dict[str, list[list[str]]], *, write: bool
) -> None:
    for bucket, sections in moved.items():
        if not sections:
            continue
        target = root / bucket / name
        if target.is_file():
            existing = _split_sections(target.read_text(encoding="utf-8"))
        else:
            existing = _Document(preamble=_bucket_header(name, bucket))
        known = {_heading_key(section) for section in existing.sections}
        existing.sections.extend(s for s in sections if _heading_key(s) not in known)
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(existing.render(), encoding="utf-8")


def _sort_ledger(root: Path) -> _Move:
    ledger = _split_sections((root / "build-ledger.md").read_text(encoding="utf-8"))

    def classify(section: list[str]) -> str:
        title = section[0][3:]
        if not (title.startswith("Phase ") or title.startswith("Carried repairs")):
            return LIVE
        return LIVE if _has_unticked(section) else DONE

    return _partition(ledger, classify)


def _row_bucket(status: str) -> str:
    upper = status.upper()
    if "DONE" in upper or "CLOSED" in upper or "DECLINED" in upper:
        return DONE
    if "WON'T" in upper or "COULD" in upper or "SHOULD" in upper:
        return IDEAS
    return LIVE


@dataclass
class _Table:
    head: list[str]
    header: list[str]
    rows: list[str]
    tail: list[str]


def _split_table(section: list[str]) -> _Table:
    """§1 around its one table: the lines before it, its two header lines, its rows, the rest."""
    separator = next(i for i, line in enumerate(section) if line.startswith("|---"))
    end = separator + 1
    while end < len(section) and section[end].startswith("|"):
        end += 1
    return _Table(
        head=section[: separator - 1],
        header=section[separator - 1 : separator + 1],
        rows=section[separator + 1 : end],
        tail=section[end:],
    )


def _status_cell(row: str) -> str:
    return row.split("|")[-3]


def _row_buckets(rows: list[str]) -> dict[str, str]:
    return {
        match.group(1): _row_bucket(_status_cell(row))
        for row in rows
        if (match := ROW_ID.match(row)) is not None
    }


def _roadmap_section_bucket(section: list[str], buckets: dict[str, str]) -> str:
    number = ROADMAP_SECTION.match(section[0])
    if number is None:
        return LIVE
    if number.group(1) in {"0", "8"}:
        return DONE
    if number.group(1) in {"6", "7"}:
        return IDEAS
    phase = PHASE_ID.search(section[0])
    if phase is None:
        return LIVE
    return buckets.get(phase.group(1), LIVE)


def _table_section(heading: str, header: list[str], rows: list[str]) -> list[str]:
    return [heading, "", *header, *rows, ""]


@dataclass
class _RoadmapMove:
    move: _Move
    buckets: dict[str, str]
    rows: dict[str, list[str]]
    header: list[str]


def _sort_roadmap(root: Path) -> _RoadmapMove:
    roadmap = _split_sections((root / "12-roadmap.md").read_text(encoding="utf-8"))
    phases = next(s for s in roadmap.sections if s[0].startswith("## 1 · "))
    table = _split_table(phases)
    by_bucket: dict[str, list[str]] = {bucket: [] for bucket in (LIVE, *BUCKETS)}
    for row in table.rows:
        by_bucket[_row_bucket(_status_cell(row))].append(row)
    phases[:] = [*table.head, *table.header, *by_bucket[LIVE], *table.tail]
    buckets = _row_buckets(table.rows)
    for bucket in BUCKETS:
        target = root / bucket / "12-roadmap.md"
        if target.is_file():
            moved_before = _split_table(
                next(
                    s
                    for s in _split_sections(target.read_text(encoding="utf-8")).sections
                    if s[0].startswith("## 1 · ")
                )
            )
            buckets = {**_row_buckets(moved_before.rows), **buckets}
    move = _partition(roadmap, lambda section: _roadmap_section_bucket(section, buckets))
    return _RoadmapMove(
        move=move,
        buckets=buckets,
        rows={bucket: by_bucket[bucket] for bucket in BUCKETS},
        header=table.header,
    )


def _load_bucket(target: Path, bucket: str) -> _Document:
    if target.is_file():
        return _split_sections(target.read_text(encoding="utf-8"))
    return _Document(preamble=_bucket_header(target.name, bucket))


def _phases_table(document: _Document, header: list[str]) -> list[str]:
    table = next((s for s in document.sections if s[0].startswith("## 1 · ")), None)
    if table is None:
        table = _table_section("## 1 · The phases", header, [])
        document.sections.insert(0, table)
    return table


def _merge_roadmap_rows(
    root: Path, rows: dict[str, list[str]], header: list[str], *, write: bool
) -> None:
    for bucket, new_rows in rows.items():
        if not new_rows:
            continue
        target = root / bucket / "12-roadmap.md"
        existing = _load_bucket(target, bucket)
        table = _phases_table(existing, header)
        present = set(table)
        insert_at = max(i for i, line in enumerate(table) if line.startswith("|")) + 1
        table[insert_at:insert_at] = [row for row in new_rows if row not in present]
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(existing.render(), encoding="utf-8")


def _gate_buckets(readme: str) -> dict[str, str]:
    buckets = {}
    for gate, rest in LOG_ROW.findall(readme):
        status = rest.split("|")[1] if rest.count("|") > 1 else rest
        if "Settled" in status:
            buckets[gate] = DONE
        elif "Deferred" in status:
            buckets[gate] = IDEAS
    return buckets


def _sort_grilling(root: Path) -> _Move:
    sessions = _split_sections((root / "05-grilling-sessions.md").read_text(encoding="utf-8"))
    buckets = _gate_buckets((root / "README.md").read_text(encoding="utf-8"))

    def classify(section: list[str]) -> str:
        if section[0].startswith("## Ordering"):
            return DONE
        gate = re.match(r"^## (G\d+) ", section[0])
        return buckets.get(gate.group(1), LIVE) if gate else LIVE

    return _partition(sessions, classify)


def _sort_execution_path(root: Path, live_ledger: str) -> tuple[str, list[list[str]]]:
    """_Move each closed phase's block out of the README's *Execution path*."""
    readme = _split_sections((root / "README.md").read_text(encoding="utf-8"))
    path = next(s for s in readme.sections if s[0].startswith("## Execution path"))
    blocks = _split_sections("\n".join(path[1:]), prefix="**Phase ")
    live_phases = set(
        PHASE_ID.findall(
            "\n".join(line for line in live_ledger.splitlines() if line.startswith("## Phase "))
        )
    )
    kept, moved = [], []
    for block in blocks.sections:
        phase = PHASE_ID.search(block[0])
        (kept if phase and phase.group(1) in live_phases else moved).append(block)
    path[1:] = [*blocks.preamble] + [line for block in kept for line in block]
    if not kept:
        path.append("")
    return readme.render(), [
        ["## Execution path", ""] + [line for b in moved for line in b]
    ] if moved else []


def _sort_fix_plans(root: Path, buckets: dict[str, str], *, write: bool) -> list[str]:
    moved = []
    plans = root / "fix-plans"
    for plan in sorted(plans.glob("[0-9][0-9]-phase-*.md")) if plans.is_dir() else []:
        match = FIX_PLAN_PHASE.match(plan.name)
        bucket = buckets.get(match.group(1), LIVE) if match else LIVE
        if bucket == LIVE:
            continue
        moved.append(f"fix-plans/{plan.name} → {bucket}/")
        if write:
            (root / bucket / "fix-plans").mkdir(parents=True, exist_ok=True)
            plan.rename(root / bucket / "fix-plans" / plan.name)
    return moved


def _report(name: str, moved: dict[str, list[list[str]]]) -> list[str]:
    return [
        f"{name}: {len(sections)} section(s) → {bucket}/  "
        f"({', '.join(s[0][3:40] for s in sections)})"
        for bucket, sections in moved.items()
        if sections
    ]


def run(root: Path, *, write: bool) -> list[str]:
    """Sort every unit under `root`; return one line per move. `write=False` only reports."""
    lines: list[str] = []
    ledger = _sort_ledger(root)
    _merge_sections(root, "build-ledger.md", ledger.moved, write=write)
    lines += _report("build-ledger.md", ledger.moved)

    roadmap = _sort_roadmap(root)
    _merge_roadmap_rows(root, roadmap.rows, roadmap.header, write=write)
    _merge_sections(root, "12-roadmap.md", roadmap.move.moved, write=write)
    lines += [f"12-roadmap.md: {len(r)} §1 row(s) → {b}/" for b, r in roadmap.rows.items() if r]
    lines += _report("12-roadmap.md", roadmap.move.moved)

    grilling = _sort_grilling(root)
    _merge_sections(root, "05-grilling-sessions.md", grilling.moved, write=write)
    lines += _report("05-grilling-sessions.md", grilling.moved)

    readme, path_moved = _sort_execution_path(root, ledger.keep.render())
    lines += _report("README.md", {DONE: path_moved})
    lines += _sort_fix_plans(root, roadmap.buckets, write=write)

    if write:
        (root / "build-ledger.md").write_text(ledger.keep.render(), encoding="utf-8")
        (root / "12-roadmap.md").write_text(roadmap.move.keep.render(), encoding="utf-8")
        (root / "05-grilling-sessions.md").write_text(grilling.keep.render(), encoding="utf-8")
        _merge_execution_path(root, path_moved)
        (root / "README.md").write_text(readme, encoding="utf-8")
    return lines


def _merge_execution_path(root: Path, moved: list[list[str]]) -> None:
    if not moved:
        return
    target = root / DONE / "README.md"
    if target.is_file():
        existing = _split_sections(target.read_text(encoding="utf-8"))
        path = next(s for s in existing.sections if s[0].startswith("## Execution path"))
        path.extend(moved[0][2:])
    else:
        existing = _Document(preamble=_bucket_header("README.md", DONE), sections=moved)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(existing.render(), encoding="utf-8")


def main() -> int:
    """Run against `--root`, by default `docs/internal`; exit 2 when no ledger is there."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default="docs/internal")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    if not (root / "build-ledger.md").is_file():
        print(f"no build-ledger.md under {root}", file=sys.stderr)
        return 2
    lines = run(root, write=not args.dry_run)
    print("\n".join(lines) if lines else "nothing to move")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
