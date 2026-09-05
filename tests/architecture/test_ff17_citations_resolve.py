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
*was* diligence. `docs/lessons.md` L8.7.

**Removing them took four agents and three failed scopings, and that is what this file prevents.**
The searcher graded their own search three times, and missed three different ways
(`docs/lessons.md` L8.8): a pattern requiring a two-segment path fragment when the question was
the bare word (13 sites reported, 277 actual); a scope written as three directory names, missing
four more populations that only `git ls-files` could enumerate; and every grep case-sensitive, so
six capitalised headings were invisible to all of them. Each miss was found by somebody else. **A
search cannot report what its own pattern excludes, which is why the durable form of this rule is
a property rather than a better grep.**

**Clause (a): the citation resolves.** Matched on *basename*, not full path, because this
codebase abbreviates — `runner.py:167` and `packages/weft-kernel/src/weft_kernel/runner.py:167`
are the same claim and both are written. Basename matching is therefore deliberately generous:
it accepts a citation this project could plausibly mean, and refuses only one that names a file
nothing here has. That is the whole of what it can honestly check, and the docstring says so
rather than implying the line number was verified too.

**Clause (b): a self-citation is refused.** A comment citing `foo.py:26` *inside* `foo.py` is
either redundant — it is pointing at code the reader is already looking at, and should name the
constant — or it is wrong, because it is quoting somebody else's file that happens to share the
name. The second is not hypothetical: three were found in this tree, including
`unicode_normalizer.py`'s **"Verified at source: `unicode_normalizer.py:12-37`'s `process`
calls…"**, describing a `process` method this file has never had (`docs/lessons.md` L8.9). It
read for three phases as an ordinary self-reference, and **it is the one form clause (a) is
structurally blind to** — the path resolves, precisely because the basename collides. Clause (b)
exists because clause (a) would have waved all three through.

**What this cannot check.** Whether the cited *line* says what the citing comment claims. That is
a judgement no walk can make; what it can do is refuse a pointer that goes nowhere and a pointer
that goes in a circle, which together are every mechanically detectable form the defect took here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import cache
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

#: A `path:line` citation: a filename with a known text extension, a colon, a line number.
#: Ranges (`:12-37`) match on their first number, which is all this check needs.
_CITATION: Final[re.Pattern[str]] = re.compile(r"([A-Za-z0-9_./-]+\.(?:py|md|toml|yaml|yml)):(\d+)")

#: Directories excluded from the search for a cited basename: reading material kept on disk and
#: out of version control. A citation that resolves only inside one of these is exactly the
#: defect this check exists for, so they must not count as a hit.
_NOT_THIS_REPO: Final[tuple[str, ...]] = (".venv", "_external-src", "_external-reading", ".git")

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
        path.name
        for path in REPO_ROOT.rglob("*")
        if path.is_file() and not any(part in _NOT_THIS_REPO for part in path.parts)
    )


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
            elif not _basename_exists(basename):
                dangling.append(
                    f"{relative}: cites '{match.group(0)}', which is nowhere in this repo"
                )
    return dangling, self_citing


def test_the_waiver_is_empty() -> None:
    assert frozenset() == CITATIONS_WAIVED, (
        "CITATIONS_WAIVED is no longer empty. A citation that goes nowhere, or that goes in a "
        "circle, is a pointer a reader cannot follow — fix the citation rather than recording "
        "it here. If an entry is genuinely right, it needs the fact that makes it right, in "
        "this constant's own docstring and in docs/README.md's decision log."
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


def test_no_citation_names_the_file_it_appears_in() -> None:
    """Clause (b) — the form clause (a) is blind to, because the path resolves."""
    _, self_citing = _violations()
    assert not self_citing, (
        "these comments cite the file they are written in:\n  "
        + "\n  ".join(self_citing)
        + "\n\nThat is either redundant — name the constant or function instead of a line "
        "number the reader is already looking at — or it is quoting a different file that "
        "happens to share the name, which is how 'verified at source' ended up attached to a "
        "method this tree never had (docs/lessons.md L8.9)."
    )


def test_a_dangling_citation_would_be_caught(tmp_path: Path) -> None:
    """Prove clause (a) can fail, on a planted file rather than the real tree."""
    # Arrange
    planted = tmp_path / "note.md"
    planted.write_text("see `no_such_module_anywhere.py:42` for the argument", encoding="utf-8")

    # Act
    match = _CITATION.search(planted.read_text(encoding="utf-8"))

    # Assert
    assert match is not None
    assert not _basename_exists(Path(match.group(1)).name)


def test_a_self_citation_would_be_caught() -> None:
    """Prove clause (b) can fail — and that clause (a) alone would *not* have caught it,
    which is the whole reason there are two clauses."""
    # Arrange — a citation naming a file that really does exist here: this one.
    text = "the guard at `test_ff17_citations_resolve.py:12` explains it"

    # Act
    match = _CITATION.search(text)

    # Assert
    assert match is not None
    basename = Path(match.group(1)).name
    assert basename == Path(__file__).name, "clause (b) sees it"
    assert _basename_exists(basename), "clause (a) does not — the path resolves"
