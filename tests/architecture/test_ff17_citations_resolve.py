"""Fitness function 17 — every citation resolves. `01` -> *Fitness functions* item 17.

**Two clauses, categorical, no tuning constant.** A `path:line` citation in a tracked file must
name a path that exists in this repository, and must not name the file it appears in.

**Why this exists, and it is the most expensive lesson in `lessons.md` made mechanical.** This
project was built while reading another codebase, and its own rules — *measure before asserting*,
*every factual claim carries a `path:line`* — were followed diligently for eight phases. The
result was hundreds of citations pointing at a tree that existed only behind one developer's
untracked symlink, **thirteen of them inside published wheels**, where a stranger who installed
the package read a pointer to a repository they did not have. The rule that demanded the evidence
is the same rule that spread it, and every individual citation looked like diligence because it
*was* diligence. `docs/internal/lessons.md` L8.7.

**Removing them took four agents and three failed scopings, and that is what this file prevents.**
The searcher graded their own search three times, and missed three different ways
(`docs/internal/lessons.md` L8.8): a pattern requiring a two-segment path fragment when the question
was the bare word (13 sites reported, 277 actual); a scope written as three directory names, missing
four more populations that only `git ls-files` could enumerate; and every grep case-sensitive, so
six capitalised headings were invisible to all of them. Each miss was found by somebody else. **A
search cannot report what its own pattern excludes, which is why the durable form of this rule is a
property rather than a better grep.**

**Clause (a): the citation resolves.** Matched on *basename*, not full path, because this
codebase abbreviates — `runner.py` at line 167 and `packages/weft-kernel/src/weft_kernel/runner.py`
at the same line
are the same claim and both are written. Basename matching is therefore deliberately generous:
it accepts a citation this project could plausibly mean, and refuses only one that names a file
nothing here has. That is the whole of what it can honestly check, and the docstring says so
rather than implying the line number was verified too.

**Clause (b): a self-citation is refused.** A comment citing a line of the very file it is written
in is either redundant — it is pointing at code the reader is already looking at, and should name
the constant — or it is wrong, because it is quoting somebody else's file that happens to share the
name. The second is not hypothetical: three were found in this tree, including
`unicode_normalizer.py`'s **"Verified at source: `unicode_normalizer.py` lines 12-37's `process`
calls…"**, describing a `process` method this file has never had (`docs/internal/lessons.md` L8.9).
It read for three phases as an ordinary self-reference, and **it is the one form clause (a) is
structurally blind to** — the path resolves, precisely because the basename collides. Clause (b)
exists because clause (a) would have waved all three through.

**What this cannot check, and what carried repair `R11.8` changed about that.** Whether the cited
*line* says what the citing comment **claims** is a judgement no walk can make, and that is still
true. What a walk *can* do is verify that the line still says what the person citing it **read** —
so clauses (c) and (d) below require every citation outside an append-only record to carry a short
quoted fragment of the line it names, and refuse it when the fragment is no longer there. An
unjudgeable claim becomes a refusable one: a citation that drifts stops being silently wrong and
becomes loudly wrong.

**Every line number written in this docstring is spelled out in words rather than as `path:line`,
and that is not a style choice.** `docs/internal/lessons.md` `L12.8`: the paragraph that documents a
document-reading check is the most dangerous line on the page, because it is where the convention's
own syntax appears in illustration — written by whoever knows the parser and is therefore least
likely to reread it as input. One of the examples below is a citation this project *knows to be
wrong*, quoted as an anecdote; annotating it with a fragment that is currently true would falsify
the very story it is told to carry.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import cache
from pathlib import Path
from typing import Final

from tests.conftest import UNTRACKED_BY_DESIGN

from .conftest import REPO_ROOT

#: A `path:line` citation: a filename with a known text extension, a colon, a line number.
#: Ranges (`:12-37`) match on their first number, which is all this check needs.
_CITATION: Final[re.Pattern[str]] = re.compile(r"([A-Za-z0-9_./-]+\.(?:py|md|toml|yaml|yml)):(\d+)")

#: A citation with the quoted fragment carried repair **R11.8** requires: `path:line "text"`.
#: The fragment sits inside the same backtick span in every site this repository writes, which
#: is what keeps it from being separated by a line wrap.
#:
#: **Either quote, and the choice is not cosmetic.** A citation inside a Python file very often
#: sits inside a string — an assertion message, an f-string — and a `"` fragment closes it. The
#: first retrofit did exactly that to **29 files**, all of which stopped parsing and were caught
#: by `ruff format` in the same minute. So `.py` sites are written with `'` and everything else
#: with `"`, and the check accepts both rather than making authors remember which: the rule an
#: author has to hold is "use the quote your file is not already using", and the rule the check
#: holds is "either". A fragment never contains its own delimiter, which is what keeps the
#: pattern unambiguous without an escape nobody would remember.
_CITATION_WITH_FRAGMENT: Final[re.Pattern[str]] = re.compile(
    r"([A-Za-z0-9_./-]+\.(?:py|md|toml|yaml|yml)):(\d+)(?:-\d+)?"
    r"(?: (?:\"([^\"]{8,})\"|'([^']{8,})'))?"
)

#: How far from the cited line the fragment may sit before the citation counts as stale.
#: **Five**, and the number is a judgement about maintenance rather than about correctness: at
#: zero, any insertion above a cited line breaks every citation below it in that file and the
#: check becomes a tax people route around (`CLAUDE.md`: "a guard that fires on safe commands is
#: one people learn to route around"); unbounded, the line number stops being checked at all and
#: the claim reverts to the one clause (a) already makes. Five absorbs an ordinary edit and
#: refuses a move into a different construct — and when it does fire, the message says which line
#: the fragment is actually on, so the repair is the one-number edit the failure hands you.
_FRAGMENT_WINDOW: Final[int] = 5

#: Files whose citations are **records rather than claims about the current tree**, and so carry
#: no fragment. A ledger entry cites the code as it stood at the commit that wrote the entry, and
#: `git blame` on the ticked box is what resolves it — re-pointing those at today's lines would
#: falsify the record it exists to keep. The same for a drained lesson and for the archive.
#: This is a **scope**, not a waiver: nothing here is exempted from a rule it should meet, and
#: adding a fourth name means arguing that a whole document has stopped making claims about the
#: tree, which is a much louder act than adding one path to a list.
_APPEND_ONLY_RECORDS: Final[frozenset[str]] = frozenset(
    {
        "docs/internal/build-ledger.md",
        "docs/internal/lessons.md",
        "docs/internal/lessons-archive.md",
    }
)

#: Basenames of `tests.conftest.UNTRACKED_BY_DESIGN` — the eight files under `docs/internal/`.
#: **A named allowance for clause (a), not the scope above**: `_APPEND_ONLY_RECORDS` says a
#: *source* file's own citations are records rather than live claims; this says a citation's
#: *target* may resolve nowhere because the file is untracked by design. A citation to any other
#: missing file still fails. Basenames, because clause (a) itself matches basenames.
_UNTRACKED_TARGETS: Final[frozenset[str]] = frozenset(Path(p).name for p in UNTRACKED_BY_DESIGN)

#: Directories excluded from the search for a cited basename: reading material kept on disk and out
#: of version control. A citation that resolves only inside one of these is exactly the defect this
#: check exists for, so they must not count as a hit. **`worktrees` joined this list at Phase 9's
#: drain, and it was not a tidy-up** — `docs/internal/lessons.md` `L9.90`. `git worktree add` puts a
#: whole second checkout under `.claude/worktrees/`, and this repository had three, unmerged,
#: carrying 174, 115 and 111 unique commits: **12,365 of the 12,976 Python files under the
#: repository root lived inside them**. Because each worktree holds its own older copy of
#: `_external-src` and `_external-reading`, the three names above were being smuggled straight back
#: into the population they exclude — **39 basenames resolved only through a stale worktree**, among
#: them `_BRIEFING.md`, `04-donor-inventory.md`, `08-salvage.md` and a dozen `ax-*.pdf`: reading
#: material about somebody else's project. A citation naming one of them would have passed, which is
#: the precise defect the sentence above says this list prevents. Measured the same day: **zero**
#: tracked citations actually did, so this was a latent hole and not an active failure — recorded
#: that way rather than dressed up as a catch.
_NOT_THIS_REPO: Final[tuple[str, ...]] = (
    ".venv",
    "_external-src",
    "_external-reading",
    ".git",
    "worktrees",
)

#: A citation permitted to name a path this repository does not have, or to name its own file.
#: **Pinned empty**, and it reached empty by the violations being *fixed* rather than recorded:
#: the two dangling citations were repaired (one malformed dotted path, one example rewritten
#: so it no longer looks like a citation) and the two self-citations were replaced by the names
#: of the constants they pointed at, which is what a self-citation should have said in the first
#: place. An entry here is a visible act in a diff and needs a fact behind it — never "this one
#: is fine".
CITATIONS_WAIVED: Final[frozenset[tuple[str, str]]] = frozenset()


def _tracked_text_files() -> tuple[Path, ...]:
    """Every tracked file, from `git ls-files` — **the derivation, not a directory list**.

    This is the half of `L8.8` that is not about grep patterns. The cleanup that produced this
    check was scoped as "packages, tests, docs" and silently excluded `.claude/`, `.github/`,
    `eval/`, `scripts/`, the dotfiles and seven `NOTICE` files. A hand-written list of roots is
    a claim about the repository's shape that stops being true the moment somebody adds a
    directory, and nothing announces it. `git ls-files` cannot be wrong about what is tracked.
    """
    # `shutil.which` rather than a bare "git": ruff's S607 refuses a partial executable path,
    # and it is right to — a relative name resolves through whatever `PATH` happens to hold.
    git = shutil.which("git")
    assert git is not None, "git is not on PATH, so this check cannot enumerate tracked files"
    listing = subprocess.run(  # noqa: S603 — a literal argv, no shell, nothing interpolated
        [git, "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return tuple(
        path for name in listing.split("\0") if name and (path := REPO_ROOT / name).is_file()
    )


@cache
def _basenames_present() -> frozenset[str]:
    """Every filename in the part of the tree this repository owns, collected in one walk.

    Cached and built once rather than an `rglob` per citation: the naive form re-walked the
    whole tree 120 times and cost 25 seconds of every gate run — the kind of price a check
    quietly starts charging and nobody attributes to it.
    """
    return frozenset(
        path.name for path in REPO_ROOT.rglob("*") if path.is_file() and _owned_by_this_repo(path)
    )


def _owned_by_this_repo(path: Path) -> bool:
    """Whether `path` is in the part of the tree this repository owns — see `_NOT_THIS_REPO`.

    Factored out of the walk so it can be self-tested against synthetic paths. Testing the
    exclusion by asserting a known worktree file is absent would be vacuous on a clean checkout,
    which is the shape `phase-step` → *Finish* item 3 refuses.
    """
    return not any(part in _NOT_THIS_REPO for part in path.parts)


def _basename_exists(basename: str) -> bool:
    """Whether any file with this basename exists in the part of the tree this repository owns."""
    return basename in _basenames_present()


def _violations() -> tuple[list[str], list[str]]:
    """`(dangling, self_citing)` — the check itself, factored out so the self-tests drive it."""
    dangling: list[str] = []
    self_citing: list[str] = []
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # a binary or unreadable tracked file cites nothing
        relative = str(path.relative_to(REPO_ROOT))
        for match in _CITATION.finditer(text):
            cited = match.group(1)
            if (relative, match.group(0)) in CITATIONS_WAIVED:
                continue
            basename = Path(cited).name
            if basename == path.name:
                self_citing.append(f"{relative}: cites itself as '{match.group(0)}'")
            elif not _basename_exists(basename) and basename not in _UNTRACKED_TARGETS:
                dangling.append(
                    f"{relative}: cites '{match.group(0)}', which is nowhere in this repo"
                )
    return dangling, self_citing


@cache
def _paths_by_basename() -> dict[str, tuple[Path, ...]]:
    """Every owned file, indexed by basename — clause (c)/(d) needs the *file*, not a yes/no.

    Cached for `_basenames_present`'s own reason: the naive form re-walked the tree once per
    citation and cost 25 seconds of every gate run.
    """
    index: dict[str, list[Path]] = {}
    for path in REPO_ROOT.rglob("*"):
        if path.is_file() and _owned_by_this_repo(path):
            index.setdefault(path.name, []).append(path)
    return {name: tuple(paths) for name, paths in index.items()}


def _targets_of(cited: str) -> tuple[Path, ...]:
    """Every file a citation could name — the exact path first, then the basename's others.

    **Plural, and for clause (a)'s own reason.** This codebase abbreviates: `runner.py` at line
    167 and the full path are the same claim, and clause (a) is deliberately generous about
    which. Clause (d) has to be generous in exactly the same way or the two clauses disagree
    about what a citation means — a file whose basename is shared (`__init__.py` is shared
    thirty ways here) would resolve to whichever path the walk happened to reach first, and the
    fragment would be looked for in a file the citer never opened. The path that literally ends
    with what was written is tried first, so a citation that spelled out its directory is
    answered by that file and not by a namesake.
    """
    candidates = _paths_by_basename().get(Path(cited).name, ())
    exact = tuple(p for p in candidates if str(p).endswith(cited))
    return exact + tuple(p for p in candidates if p not in exact)


def _without_quotes(text: str) -> str:
    """Both sides of the fragment comparison, with `"` removed.

    A cited line is very often a string literal, and a fragment delimited by `"` cannot carry
    one. Rather than invent an escape nobody would remember, the comparison simply ignores the
    character on both sides: `TABLE = table` matches `    TABLE = "table"`. Stated here because
    it is the one non-obvious thing about writing a fragment by hand.
    """
    return text.replace('"', "")


def _fragment_violations() -> tuple[list[str], list[str]]:
    """`(missing, stale)` — clauses (c) and (d), carried repair **R11.8**.

    **(c) every citation outside an append-only record carries a fragment.** Categorical, with no
    grandfathering ratchet: the population was measured at **160** and retrofitted in one commit,
    which is affordable exactly once and is why it was done rather than pinned. A waiver constant
    holding 160 entries is a table nobody reads, which is the failure a ratchet is meant to
    prevent.

    **(d) the fragment is still there.** This is the clause `L11.39` bought and the one this
    file's own docstring said could not exist — *"whether the cited line says what the citing
    comment claims... is a judgement no walk can make"*. That remains true, and it is not what
    this checks. What a walk **can** do is verify that the line still says what the person citing
    it read, which turns an unjudgeable claim into a refusable one: the citation stops being
    silently wrong and starts being loudly wrong.

    **Measured when this was written**: of the 160, **24** already pointed at a blank or missing
    line and **six more** at a line that could yield no fragment at all — a closing `\"\"\"`, an
    import continuation, a `del ctx`, a ``` fence opener. Thirty stale citations, under a fitness
    function that had been green on every run, and two of them (`seam.py` at lines 211-229 for a
    claim about emitting `DeprecationWarning`, `context.py` at line 105 for one about exact-type
    lookup) were not off by two lines but pointing at an unrelated class more than a hundred lines
    away. `docs/internal/lessons.md` `L9.34` measured the same drift from the other end: three
    agents citing one paragraph at three different line numbers on one day.
    """
    missing: list[str] = []
    stale: list[str] = []
    for path in _tracked_text_files():
        relative = str(path.relative_to(REPO_ROOT))
        if relative in _APPEND_ONLY_RECORDS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in _CITATION_WITH_FRAGMENT.finditer(text):
            cited, line_no = match.group(1), int(match.group(2))
            fragment = match.group(3) if match.group(3) is not None else match.group(4)
            if Path(cited).name == path.name:
                continue  # clause (b) already refuses this, and says so better
            if fragment is None:
                missing.append(
                    f"{relative}: cites '{cited}:{line_no}' with no quoted fragment. Write it as "
                    f'`{cited}:{line_no} "<text from that line>"` so the citation can be refused '
                    f"when what it points at changes."
                )
                continue
            targets = _targets_of(cited)
            if not targets:
                continue  # clause (a) already refuses this
            wanted = _without_quotes(fragment)
            elsewhere: list[int] = []
            satisfied = False
            for target in targets:
                lines = target.read_text(encoding="utf-8").split("\n")
                found = [
                    n for n, body in enumerate(lines, start=1) if wanted in _without_quotes(body)
                ]
                if any(abs(n - line_no) <= _FRAGMENT_WINDOW for n in found):
                    satisfied = True
                    break
                elsewhere.extend(found)
            if satisfied:
                continue
            where = (
                f"it is at line(s) {sorted(set(elsewhere))[:3]}"
                if elsewhere
                else "it is in no file of that name"
            )
            stale.append(
                f"{relative}: cites '{cited}:{line_no}' quoting {fragment!r}, and {where}."
            )
    return missing, stale


def test_every_citation_carries_the_fragment_that_makes_it_checkable() -> None:
    # Clause (c), carried repair **R11.8**. `L11.39`, declined at Phase 11's drain to be designed
    # beside `R11.7` — both are the same idea, a claim written in a shape a checker can refuse,
    # one about a section and one about a line.
    missing, _stale = _fragment_violations()
    assert not missing, (
        "a citation names a line and gives nothing that can be checked against it:\n  "
        + "\n  ".join(sorted(missing))
    )


def test_every_cited_line_still_says_what_the_citation_quotes() -> None:
    # Clause (d) — the one this file's docstring said could not exist. It still cannot judge
    # whether the line *supports* the claim; it refuses a citation whose line no longer says what
    # the person writing it read, which is every mechanically detectable form of the drift.
    _missing, stale = _fragment_violations()
    assert not stale, (
        "a citation quotes a line that has moved or gone:\n  "
        + "\n  ".join(sorted(stale))
        + f"\nThe window is ±{_FRAGMENT_WINDOW} lines; where the message names the line the "
        "fragment is actually on, correcting the citation is that one number."
    )


def test_a_second_checkout_under_this_root_does_not_answer_for_this_repository() -> None:
    """The exclusion `L9.90` bought, driven through the predicate the walk actually uses.

    A `git worktree` puts a whole second checkout inside this tree, carrying its own older copy
    of `_external-src` and `_external-reading` — so without this, the three directories
    `_NOT_THIS_REPO` names to exclude were reachable again one level down, and a citation into
    another project's reading material resolved green.
    """
    # Arrange — a path that **only** the worktree rule can exclude. Picking one under
    # `_external-reading` inside a worktree would be excluded by the older rule too, so the
    # test would pass with this repair reverted: that exact case was written first, planted,
    # and passed. It is kept in the comment because the trap is the point — a disagreeing
    # case must disagree for the reason under test and no other.
    smuggled = REPO_ROOT / ".claude" / "worktrees" / "old" / "docs" / "01-high-level-plan.md"
    ours = REPO_ROOT / "docs" / "01-high-level-plan.md"

    # Act / Assert
    assert not _owned_by_this_repo(smuggled)
    assert _owned_by_this_repo(ours)


def test_the_waiver_is_empty() -> None:
    assert frozenset() == CITATIONS_WAIVED, (
        "CITATIONS_WAIVED is no longer empty. A citation that goes nowhere, or that goes in a "
        "circle, is a pointer a reader cannot follow — fix the citation rather than recording "
        "it here. If an entry is genuinely right, it needs the fact that makes it right, in "
        "this constant's own docstring and in docs/internal/README.md's decision log."
    )


def test_at_least_one_citation_is_checked() -> None:
    # Floor — a walk that found nothing would pass by asking nothing, which is the vacuous
    # shape `08` §3 refuses. This tree carries ~120 `path:line` citations.
    found = sum(
        len(_CITATION.findall(path.read_text(encoding="utf-8", errors="ignore")))
        for path in _tracked_text_files()
    )
    assert found > 50, (
        f"only {found} path:line citations found across every tracked file. This project cites "
        f"heavily by convention; a number this low means the pattern stopped matching, not that "
        f"the citations went away."
    )


def test_every_citation_resolves_to_a_path_this_repository_has() -> None:
    """Clause (a)."""
    dangling, _ = _violations()
    assert not dangling, (
        "these citations name a file that exists nowhere in this repository, so a reader "
        "cannot follow them:\n  "
        + "\n  ".join(dangling)
        + "\n\nA pointer into a tree the reader does not have is worse than no pointer: it "
        "reads as evidence. Fix the path, or state the fact without the citation."
    )


def test_the_untracked_allowance_is_scoped_to_docs_internal_and_nothing_else() -> None:
    """`_UNTRACKED_TARGETS` names exactly the basenames under `docs/internal/`, and a missing
    basename outside that set still dangles — otherwise an allowance meant for one owner's
    decision quietly covers every other broken citation too.

    `README.md` is in the set and carries nothing, because clause (a) matches basenames and the
    repository root has a `README.md` of its own: that citation resolves with or without this.
    """
    assert {
        "README.md",
        "build-ledger.md",
        "lessons.md",
        "lessons-archive.md",
        "05-grilling-sessions.md",
        "12-roadmap.md",
        "product-direction.md",
        "ADAM_TODO.md",
    } == _UNTRACKED_TARGETS
    assert "totally-fake-basename-nobody-cites.md" not in _UNTRACKED_TARGETS
    assert not _basename_exists("totally-fake-basename-nobody-cites.md")


def test_no_citation_names_the_file_it_appears_in() -> None:
    """Clause (b) — the form clause (a) is blind to, because the path resolves."""
    _, self_citing = _violations()
    assert not self_citing, (
        "these comments cite the file they are written in:\n  "
        + "\n  ".join(self_citing)
        + "\n\nThat is either redundant — name the constant or function instead of a line "
        "number the reader is already looking at — or it is quoting a different file that "
        "happens to share the name, which is how 'verified at source' ended up attached to a "
        "method this tree never had (docs/internal/lessons.md L8.9)."
    )


def test_a_dangling_citation_would_be_caught(tmp_path: Path) -> None:
    """Prove clause (a) can fail, on a planted file rather than the real tree."""
    # Arrange
    # Assembled from parts rather than written as a literal. **This file is itself a tracked
    # file that this check scans**, so a fixture spelled out here would be a violation of the
    # very rule it is testing — which is exactly what happened: the first green came from a run
    # made before `git add`, when the file was untracked and therefore excluded from its own
    # subject. A check whose population is "tracked files" does not include itself until it is
    # committed, so its first pass proves nothing.
    absent = "no_such_module_anywhere" + ".py"
    planted = tmp_path / "note.md"
    planted.write_text(f"see `{absent}:42` for the argument", encoding="utf-8")

    # Act
    match = _CITATION.search(planted.read_text(encoding="utf-8"))

    # Assert
    assert match is not None
    assert not _basename_exists(Path(match.group(1)).name)


def test_a_self_citation_would_be_caught() -> None:
    """Prove clause (b) can fail — and that clause (a) alone would *not* have caught it,
    which is the whole reason there are two clauses."""
    # Arrange — a citation naming a file that really does exist here: this one. Built from
    # `Path(__file__).name` rather than written out, for the reason `test_a_dangling_citation_
    # would_be_caught` above explains at length.
    text = f"the guard at `{Path(__file__).name}:12` explains it"

    # Act
    match = _CITATION.search(text)

    # Assert
    assert match is not None
    basename = Path(match.group(1)).name
    assert basename == Path(__file__).name, "clause (b) sees it"
    assert _basename_exists(basename), "clause (a) does not — the path resolves"


def test_the_check_can_actually_fail() -> None:
    """Clauses (c) and (d), driven through the same comparison the walk uses.

    Both are set-difference-shaped and both would pass on an empty subject, so the floor is two:
    the population is non-empty, and a disagreeing input is refused. **Watched red before this
    was written** — clause (c) named seven citations with no fragment, and clause (d) named the
    one whose fragment had been generated against a namesake file.
    """
    annotated = 0
    for path in _tracked_text_files():
        if str(path.relative_to(REPO_ROOT)) in _APPEND_ONLY_RECORDS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        annotated += sum(
            1
            for m in _CITATION_WITH_FRAGMENT.finditer(text)
            if m.group(3) is not None or m.group(4) is not None
        )
    assert annotated > 100, (
        f"only {annotated} citations carry a fragment. The retrofit landed 160; a number this "
        f"low means the pattern stopped matching, not that the citations went away."
    )

    # A fragment that is not on the cited line, in a file that genuinely has that line.
    target = REPO_ROOT / "tests" / "architecture" / "test_ff17_citations_resolve.py"
    lines = target.read_text(encoding="utf-8").split("\n")
    # Assembled at run time rather than written out: a literal plant string is, by the act of
    # writing it, present in this very file — which is `L12.8` in miniature and cost one red run.
    absent = "-".join(("nowhere", "in", "this", "tree", "at", "all", "\u00a7\u00b6"))
    assert not any(absent in line for line in lines), "the plant is not a plant"
    found = [n for n, body in enumerate(lines, start=1) if _without_quotes(absent) in body]
    assert not found, "clause (d) would have nothing to refuse"

    # And the quote-insensitive comparison is doing real work rather than matching everything.
    assert _without_quotes('TABLE = "table"') == "TABLE = table"
    assert _without_quotes("TABLE = table") in _without_quotes('    TABLE = "table"')
    assert "definitely-not-here" not in _without_quotes('    TABLE = "table"')


# --- Clause (e), `docs/internal/lessons.md` `L17.1`: a citation to a *section number*.

#: A `§` citation carries neither a path nor a quoted fragment, so clauses (a) through (d) are
#: all blind to it — it is a third population, and `L16.3`'s measurement of *19 bare relative
#: citations* was about **line** citations and did not include it. Four sites cited `09` §4.4 as
#: the argument that a model download is kept out of the gate; that section argues against
#: inventing quality thresholds and says nothing about downloads, and `git log -S` found the
#: argument was never written in `09` in any commit.
_SECTION_CITATION: Final[re.Pattern[str]] = re.compile(r"`(\d{2})`\s*§\s*(\d+(?:\.\d+)*)")


def _numbered_document(number: str) -> Path | None:
    """`docs/NN-*.md` for `NN`, or `None` when this checkout does not hold one.

    `None` is the normal answer for `12` and `13`: `docs/internal/` is untracked by design, so a
    clone genuinely does not have them and a citation into one is unresolvable here rather than
    wrong. `tests/conftest.py`'s `UNTRACKED_BY_DESIGN` is the list every such check reads.
    """
    found = sorted(REPO_ROOT.glob(f"docs/{number}-*.md"))
    return found[0] if found else None


def test_every_section_citation_resolves_to_a_heading() -> None:
    """Clause (e) — a `§n.n` citation names a section the cited document actually has.

    The cheapest half of the three populations `L17.1` named, and the only one that is purely
    structural: the target's own headings are already parsed for other purposes here, so this
    costs a regex and a lookup. It says nothing about whether the section *supports* the claim —
    clause (d) cannot do that either — only that a reader following the citation arrives
    somewhere.

    **Measured before adopting, per `implement-ll`'s sizing rule: 1,069 citations walked, one
    failing.** That one was `02` citing section 1 of the high-level plan, which carries no
    numbered sections at all — every document in this tree with no numbers is cited by heading
    name instead. Five further citations name the roadmap, which is untracked by design and is
    skipped rather than failed.

    **The examples above are written so this check cannot match them** — *"section 1 of the
    high-level plan"* rather than the citation form — which is `L12.8`'s rule: a convention
    illustrated in a form its own parser matches becomes a phantom member of the population the
    parser counts.
    """
    # Arrange
    stale: list[str] = []

    # Act
    for path in _tracked_text_files():
        text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        for match in _SECTION_CITATION.finditer(text):
            number, section = match.group(1), match.group(2)
            target = _numbered_document(number)
            if target is None:
                continue
            headings = target.read_text(encoding="utf-8", errors="replace")
            if not re.search(rf"^#+\s*{re.escape(section)}[\s.]", headings, re.MULTILINE):
                stale.append(
                    f"{path}: cites `{number}` §{section}, and "
                    f"{target.relative_to(REPO_ROOT)} has no heading numbered {section}"
                )

    # Assert
    assert not stale, (
        "a section citation names a section its document has not got:\n  "
        + "\n  ".join(sorted(set(stale)))
        + "\nA `§` citation carries neither a path nor a quoted fragment, so nothing else here "
        "can see it — cite the heading by name where a document has no numbered sections."
    )


def test_the_section_check_can_actually_fail(tmp_path: Path) -> None:
    """Non-vacuity: the walk finds citations at all, and the comparison refuses a bad one."""
    # Arrange — the real population, and a fabricated miss against a real document.
    found = 0
    for path in _tracked_text_files():
        text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        found += len(_SECTION_CITATION.findall(text))

    # Assert
    assert found > 100, f"the section-citation walk found {found} sites; it is not looking"
    target = _numbered_document("09")
    assert target is not None
    headings = target.read_text(encoding="utf-8", errors="replace")
    # A section number no document has, built rather than written as a citation — writing it as
    # one would make this test a member of the population it is checking (`L12.8`).
    absent = "99.99"
    assert not re.search(rf"^#+\s*{re.escape(absent)}[\s.]", headings, re.MULTILINE), (
        f"the release document has a heading numbered {absent}, so this check cannot tell a "
        f"real miss from a hit"
    )
