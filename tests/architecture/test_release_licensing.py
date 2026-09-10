"""`LICENSE` and `NOTICE` are in every built artefact — ledger task **6.11**.

`docs/09-release.md` §5.2, *Security, licensing, documentation*, and `CLAUDE.md`'s originality
rule: every file in the release is accounted for as original work, and the licence travels with the
artefact rather than with the repository.

**Measured before it was fixed: not one built artefact carried either file.** No distribution
declared a `license` at all, and `LICENSE`/`NOTICE` sit at the repository root, which nothing in a
per-distribution build can see. Twenty wheels were one `uv publish` away from an index with no
licence in them — the state where a company's own tooling refuses the dependency and there is no
answer in the artefact to point at.

**Why each distribution carries its own copy rather than reaching for the root one.** Measured, not
assumed: `[tool.hatch.build.targets.wheel.force-include]` with `"../../LICENSE"` fails the build
outright, and PEP 639's `license-files` resolves relative to the distribution's own directory. So
the copies are real files, and this check is what makes twenty copies safe — each is asserted
**byte-identical** to the root original, so a licence edited in one place and not the others fails
the gate rather than shipping twenty different licences.

**A carried licence must be a *regular file*, and that clause was bought by measurement.** The nine
copies are maintained by hand, so the obvious economy is to symlink them at the root and let the
filesystem make them one file. Measured 2026-09-09 in a throwaway hatchling package rather than
argued: with `LICENSE`/`NOTICE` as symlinks and both declared in `license-files`, the sdist carries
them at **size 0** and the wheel built from that sdist carries **no licence entry at all** — the
state the paragraph above records this tree being found in. Both checks below passed on it:
`is_file()` follows a symlink and `read_bytes()` reads through one, so neither could see it. The
`is_symlink()` refusal is therefore not tidiness; it is the only thing standing between a plausible
simplification and twenty wheels with no licence. `docs/lessons.md` `L11.8`. The nine copies stay
nine files, and `poe licence-sync` is what keeps a one-sentence edit from being a nine-file one —
the check stays the enforcement rather than becoming the workflow.

**The artefact half lives in `scripts/check_sdists.py`**, not here: `files_that_must_ship` requires
both files of every distribution, so task 6.7's comparison against the real archive is what proves
they are actually *in* the tarball. This file checks the declarations and the copies; that one
checks the bytes that ship. Two sources, and they can disagree — a `license-files` entry naming a
file that is not there, or a file present and never declared.

**Task 11.0 added a second subject to this file, and it is a different population.** The checks
above walk *distributions* and read metadata; the block at the foot walks *source files* and reads
their lines, because `NOTICE` case 2's promise — that a reader can tell the owner's own prior work
from Weft's own without asking — is a claim about lines and nothing here read a line of source until
then. They share this module because they share the document: `NOTICE` is the artefact both halves
are about, and splitting them would put two checks on one file in two places.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final, NamedTuple, cast

from publish_set import publishing_members

from .conftest import REPO_ROOT, tracked_files

ROOT_LICENSE: Final[Path] = REPO_ROOT / "LICENSE"
ROOT_NOTICE: Final[Path] = REPO_ROOT / "NOTICE"

#: The files every published distribution carries, and the SPDX expression they are under.
LICENCE_FILES: Final[tuple[str, ...]] = ("LICENSE", "NOTICE")
SPDX: Final[str] = "MIT"


def _project(manifest: Path) -> dict[str, object]:
    with manifest.open("rb") as handle:
        document: dict[str, Any] = tomllib.load(handle)
    project = document.get("project", {})
    return cast("dict[str, object]", project) if isinstance(project, dict) else {}


def test_every_published_distribution_carries_the_licence_files() -> None:
    """The copies exist. A `license-files` entry naming a file that is not there builds a wheel
    with no licence in it and says nothing about it.
    """
    # Arrange
    members = publishing_members()

    # Act
    missing = [
        f"{member.name}/{name}"
        for member in members
        for name in LICENCE_FILES
        if not (member.directory / name).is_file()
    ]
    not_regular = [
        f"{member.name}/{name}"
        for member in members
        for name in LICENCE_FILES
        if (member.directory / name).is_symlink()
    ]

    # Assert
    assert members, "no publishing member was found — the reader is wrong, not the workspace"
    assert not not_regular, (
        f"{not_regular} are links rather than real files. Measured: hatchling writes a symlinked "
        f"`license-files` entry into the sdist at size 0, and the wheel built from that sdist "
        f"carries no licence at all — while `is_file()` and the byte comparison below both pass, "
        f"because each follows the link. Nine real copies, kept in step by `poe licence-sync`."
    )
    assert not missing, (
        f"{missing} are absent. Every published distribution carries its own copy: hatchling "
        f"cannot force-include a path outside the distribution directory, and PEP 639's "
        f"`license-files` resolves relative to it, so the root files are unreachable from a "
        f"per-distribution build."
    )


def test_every_carried_licence_is_byte_identical_to_the_root_original() -> None:
    """Twenty copies are safe only because this check makes them one file.

    Without it, the licence is the classic two-lists bug aimed at the one document a lawyer
    reads: edited in one place, stale in nineteen, and every one of them shipped.
    """
    # Arrange
    originals = {"LICENSE": ROOT_LICENSE.read_bytes(), "NOTICE": ROOT_NOTICE.read_bytes()}

    # Act
    drifted = [
        f"{member.name}/{name}"
        for member in publishing_members()
        for name in LICENCE_FILES
        if (member.directory / name).is_file()
        and (member.directory / name).read_bytes() != originals[name]
    ]

    # Assert
    assert originals["LICENSE"] and originals["NOTICE"], (
        f"{ROOT_LICENSE} or {ROOT_NOTICE} is empty — the comparison below would pass by having "
        f"nothing to compare."
    )
    assert not drifted, (
        f"{drifted} differ from the repository's own copy. There is one licence and one notice; "
        f"a distribution shipping a different one is shipping a different promise."
    )


def test_every_published_distribution_declares_its_licence() -> None:
    """The declaration is what puts the files in the artefact. A copy sitting in the directory
    with nothing naming it is a file the build ignores.
    """
    # Arrange
    members = publishing_members()

    # Act
    undeclared: list[str] = []
    for member in members:
        project = _project(member.directory / "pyproject.toml")
        declared = project.get("license-files")
        names: set[str] = set(cast("list[str]", declared)) if isinstance(declared, list) else set()
        if project.get("license") != SPDX or not set(LICENCE_FILES) <= names:
            undeclared.append(member.name)

    # Assert
    assert not undeclared, (
        f'{undeclared} do not declare `license = "{SPDX}"` and '
        f"`license-files = {list(LICENCE_FILES)}`. Without the declaration the files are in the "
        f"directory and not in the wheel, which is the state this task found the whole tree in."
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Planted, because the real tree agrees once this task lands and the comparison is then
    never seen disagreeing (`docs/lessons.md` L5.19). Both halves: a drifted copy and a
    declaration that names a file nobody wrote.
    """
    # Arrange
    original = b"MIT License\n\nCopyright (c) 2026\n"
    drifted_dir = tmp_path / "weft-drifted"
    drifted_dir.mkdir()
    (drifted_dir / "LICENSE").write_bytes(b"Apache License\n")
    (drifted_dir / "pyproject.toml").write_text(
        '[project]\nname = "weft-drifted"\nversion = "0.0.0"\nlicense = "Apache-2.0"\n',
        encoding="utf-8",
    )

    # Act
    drifted = (drifted_dir / "LICENSE").read_bytes() != original
    project = _project(drifted_dir / "pyproject.toml")
    declared = project.get("license-files")
    names: set[str] = set(cast("list[str]", declared)) if isinstance(declared, list) else set()

    linked_dir = tmp_path / "weft-linked"
    linked_dir.mkdir()
    (linked_dir / "LICENSE").symlink_to(drifted_dir / "LICENSE")

    # Assert
    assert drifted, "a different licence text must read as drifted"
    assert not (drifted_dir / "NOTICE").is_file()
    assert project.get("license") != SPDX
    assert not set(LICENCE_FILES) <= names
    # The symlink half, planted because the real tree carries nine regular files and the clause
    # would otherwise never be seen firing. Both of the other predicates agree with the link,
    # which is the whole reason a third one had to be written.
    assert (linked_dir / "LICENSE").is_symlink()
    assert (linked_dir / "LICENSE").is_file(), (
        "a symlink to an existing file reads as a file — this is what the existence check above "
        "could not see, and why it is not sufficient on its own"
    )
    assert (linked_dir / "LICENSE").read_bytes() == (drifted_dir / "LICENSE").read_bytes(), (
        "and reading through the link reports no drift, so the byte comparison could not see it "
        "either"
    )


# ---------------------------------------------------------------------------
# Ledger task **11.0** — the owner's own prior work is marked where it lands.
# ---------------------------------------------------------------------------
#
# `NOTICE` case 2 permits material the project owner wrote before this project began, and requires
# that "the file carrying it says so, naming the source work — so a reader can always tell the two
# origins apart without asking". Until this task that requirement was a sentence: there was no
# spelling for the marker and nothing read a source file looking for one. The obligation is dated
# and it is *before* the first copy, not after — `docs/product-direction.md:83-84 'must be amende'`:
# `NOTICE` "must
# be amended to distinguish the third-party source from the owner's own prior work, **in the same
# commit as the first copied line — not after**". A check that only exists after the first copy is
# the prose-check shape `docs/lessons.md` L6.12 forbids, so it is built here, before task 11.7
# carries the first line across.
#
# **Three sources, and they can genuinely disagree** (`docs/lessons.md` L5.6 — a check whose two
# sides come from one source cannot fail):
#
#   1. `NOTICE` case 2 owns the **convention**: the two spellings, in backticks, and nothing else
#      in this repository decides them. The sweep below does not hardcode them — it *reads* them
#      out of `NOTICE` and greps with what it found, so a `NOTICE` edit that changes the convention
#      changes what the check looks for rather than silently leaving it looking for the old thing.
#   2. The repository `README.md` owns the **enumeration**: which source works are carried, in a
#      list under a stable anchor, where a reader of the public front page finds it.
#   3. The carrying files own the **spans**: which lines are that work, delimited in place.
#
# **What this asserts about the tree today, stated plainly, because it is not much.** No file in
# this repository carries the owner's prior work yet, so the set comparison is empty against empty
# and cannot fail on this commit. That is `docs/lessons.md` L11.5's shape and it is not hidden
# here: the two assertions that *are* live today are that `NOTICE` still declares the convention
# and that `README.md` still carries a parseable enumeration, and the comparison is **armed** for
# the commit that adds the first marker — which is exactly the commit the obligation names. The
# floor for the vacuous half is `test_the_prior_work_marking_check_can_actually_fail`, which plants
# a fixture tree and watches every direction fire.
#
# **This module never writes the marker literally, and that is deliberate rather than clever.** A
# check that greps the tree for a token it also contains finds itself, and the usual repair is an
# exclusion list naming the checker — which then has to be maintained by whoever moves the file.
# Instead every token used below, in the sweep *and* in the plant, is derived from the `NOTICE`
# text at `_convention()`. The population is restricted to source extensions, which keeps `NOTICE`
# (no extension) and every `.md` document out without naming any of them.

#: Where `README.md` enumerates the source works carried. An HTML comment, so it renders as
#: nothing and still gives the parser below a stable point to start from — a heading would be a
#: second thing the check depends on a human not rewording.
README_ANCHOR: Final[str] = "<!-- weft-prior-work-sources -->"

#: The extensions the sweep reads. Source and configuration, never prose: `NOTICE` and the `docs/`
#: tree *describe* the convention and would otherwise read as violations of it, and an allowlist
#: excludes them by what they are rather than by a list of paths that goes stale.
MARKABLE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".py", ".pyi", ".toml", ".yaml", ".yml", ".sql", ".cfg", ".sh"}
)

#: `NOTICE` case 2's two spellings, read out of `NOTICE` rather than restated here. The `<source
#: work>` placeholder is part of the match because it is what makes the opening spelling a
#: *template* — a reader who copies the line gets the shape and the obligation together.
_CONVENTION: Final[re.Pattern[str]] = re.compile(
    r"`(?P<begin>[a-z][a-z-]* begin): <source work>`.*?`(?P<end>[a-z][a-z-]* end)`",
    re.DOTALL,
)


class PriorWorkSpan(NamedTuple):
    """One run of lines a file declares as the owner's own prior work.

    `path` is repository-relative for a message a reader can act on; the two line numbers are
    1-indexed and inclusive of their own marker lines, because *"which lines are that work"* is the
    fact the task asks for and a half-open interval invites an off-by-one in the answer.
    """

    path: str
    source_work: str
    begin_line: int
    end_line: int


def _convention(notice: str) -> tuple[str, str]:
    """The begin and end marks, as `NOTICE` case 2 spells them.

    Returns them stripped of the trailing colon and placeholder, so the caller has exactly the two
    literals a marked file contains.
    """
    match = _CONVENTION.search(notice)
    assert match is not None, (
        f"{ROOT_NOTICE} does not spell the prior-work marker. `NOTICE` case 2 owns this "
        f"convention: it must name the opening line as `<token> begin: <source work>` and the "
        f"closing line as `<token> end`, both in backticks, or nothing in this repository knows "
        f"what a marked file looks like."
    )
    begin, end = match.group("begin"), match.group("end")
    assert begin.rsplit(" ", 1)[0] == end.rsplit(" ", 1)[0], (
        f"the two spellings in {ROOT_NOTICE} use different tokens ({begin!r} against {end!r}), so "
        f"a marked file would open with one vocabulary and close with another"
    )
    return f"{begin}:", end


def _declared_source_works(readme: str) -> tuple[str, ...]:
    """The source works `README.md` says are carried, in the order it lists them.

    A bullet declares a source work when its text opens with a backticked name; a bullet that does
    not — today's single *(none)* line — declares nothing. That is what lets the enumeration be
    honestly empty rather than absent, and an absent anchor is a failure rather than an empty list.
    """
    _, _, after = readme.partition(README_ANCHOR)
    assert after, (
        f"the repository README.md carries no {README_ANCHOR} anchor, so nothing on the front "
        f"page says which source works this repository carries under `NOTICE` case 2"
    )
    names: list[str] = []
    for line in after.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("- "):
            break
        if declared := re.match(r"- `([^`]+)`", stripped):
            names.append(declared.group(1))
    return tuple(names)


class PriorWorkSweep(NamedTuple):
    """What one pass over a file set found — including `files_read`, which is the load-bearing part.

    `spans` and `malformed` are both empty on this tree today, and they are *also* both empty when
    the sweep reads nothing at all: a wrong suffix allowlist, a `tracked_files()` that came back
    empty, a root pointing somewhere else. Those two states are indistinguishable from their
    outputs, which is `docs/lessons.md` L5.19's shape exactly — so the count of files actually
    opened is returned alongside them and asserted, rather than left as something a reader assumes.
    """

    spans: tuple[PriorWorkSpan, ...]
    malformed: tuple[str, ...]
    files_read: int


def _prior_work_spans(root: Path, relative_paths: Iterable[str]) -> PriorWorkSweep:
    """Every well-formed span, and every malformed marker, over the files named.

    Malformations are returned rather than raised because the caller wants all of them in one
    message: an unbalanced marker is usually one of several in a commit that got the convention
    half right, and a check that stops at the first found makes that a sequence of gate runs.

    Nesting is a malformation, not a structure. A span inside a span makes *"which lines are that
    work"* answerable two ways, which is the one thing this convention exists to prevent.
    """
    notice = (root / "NOTICE").read_text(encoding="utf-8")
    begin_mark, end_mark = _convention(notice)
    spans: list[PriorWorkSpan] = []
    malformed: list[str] = []
    files_read = 0
    for relative in sorted(relative_paths):
        path = root / relative
        if path.suffix not in MARKABLE_SUFFIXES or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        files_read += 1
        if begin_mark not in text and end_mark not in text:
            continue
        open_at: int | None = None
        open_name = ""
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if begin_mark in stripped:
                if open_at is not None:
                    inner = stripped.split(begin_mark)[-1].strip()
                    malformed.append(
                        f"{relative}:{number} opens a span for {inner!r} while the one opened at "
                        f"line {open_at} is still open — a nested span makes which lines are prior "
                        f"work answerable two ways"
                    )
                    continue
                open_at = number
                open_name = stripped.split(begin_mark, 1)[1].strip()
                if not open_name:
                    malformed.append(
                        f"{relative}:{number} opens a span and names no source work, which is the "
                        f"one thing `NOTICE` case 2 requires of it"
                    )
            elif end_mark in stripped:
                if open_at is None:
                    malformed.append(
                        f"{relative}:{number} closes a prior-work span that was never opened"
                    )
                    continue
                if open_name:
                    spans.append(PriorWorkSpan(relative, open_name, open_at, number))
                open_at, open_name = None, ""
        if open_at is not None:
            malformed.append(
                f"{relative}:{open_at} opens a prior-work span for {open_name!r} and the file ends "
                f"without closing it, so its last line is undecided"
            )
    return PriorWorkSweep(tuple(spans), tuple(malformed), files_read)


def _case_two(notice: str) -> str:
    """`NOTICE`'s case 2 alone — the numbered paragraph that permits the material.

    Sliced rather than searched, because *"`NOTICE` mentions the marker somewhere"* is satisfied by
    a sentence in case 1 or case 3 and would then be a check that the string exists rather than
    that the right case owes it.
    """
    _, _, after = notice.partition("2. **The copyright holder's own prior work")
    assert after, (
        f"{ROOT_NOTICE} has no case 2 opening with `2. **The copyright holder's own prior work`, "
        f"so the case that permits this material cannot be located and nothing can own the marker"
    )
    body, terminator, _ = after.partition("3. **Short attributed quotation")
    # Watched failing 2026-09-09, and it did not: with the terminator reworded, `partition` returns
    # the whole remainder as the first element, so this slice silently grew to end-of-file and
    # "declared inside case 2" became "declared anywhere below case 2's heading". A `partition`
    # whose separator is absent does not fail — it succeeds with everything on one side, which is
    # the failure mode `CLAUDE.md` calls a plausible answer against the wrong data.
    assert terminator, (
        f"{ROOT_NOTICE} has no case 3 opening with `3. **Short attributed quotation`, so case 2's "
        f"extent cannot be bounded and every assertion about what is inside it would be made "
        f"against the rest of the file"
    )
    return body


def test_notice_case_two_names_the_prior_work_marker_convention() -> None:
    """`NOTICE` owns the spelling, and this is the assertion that keeps it there.

    Live on this commit, unlike the set comparison below: it fails the moment `NOTICE` loses the
    convention, which is the state in which every other test in this block silently stops looking
    for anything.
    """
    # Arrange
    notice = ROOT_NOTICE.read_text(encoding="utf-8")

    # Act
    begin_mark, end_mark = _convention(notice)
    case_two = _case_two(notice)

    # Assert
    assert begin_mark.endswith(":"), (
        f"the opening mark {begin_mark!r} must end in a colon — the source work is what follows it"
    )
    assert end_mark and not end_mark.endswith(":"), (
        f"the closing mark {end_mark!r} takes no argument: a span closes, it does not re-declare"
    )
    assert _CONVENTION.search(case_two) is not None, (
        f"{ROOT_NOTICE} spells the prior-work marker outside case 2. Case 2 is the case that "
        f"permits the material, so it is the case that owes the convention — a spelling declared "
        f"anywhere else leaves the permitting paragraph still saying only that a file 'says so'."
    )
    assert "README" in case_two, (
        f"case 2 does not send a reader to the enumeration. The convention marks *which lines*; "
        f"only {REPO_ROOT / 'README.md'} says which source works are carried at all, and a reader "
        f"who finds a marker needs to be told where the list is."
    )


def test_the_readme_enumerates_the_source_works_carried() -> None:
    """The front page says which prior work is in here, and the enumeration is parseable.

    Also live today. An empty enumeration is the correct answer on this commit and an *absent* one
    is not, which is the distinction `_declared_source_works` refuses to blur.
    """
    # Arrange
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    # Act
    declared = _declared_source_works(readme)
    shown_here = _convention(readme)
    declared_in_notice = _convention(ROOT_NOTICE.read_text(encoding="utf-8"))

    # Assert
    assert README_ANCHOR in readme
    assert len(set(declared)) == len(declared), (
        f"README.md lists a source work twice ({declared}), so the enumeration disagrees with "
        f"itself before anything else gets to disagree with it"
    )
    # The one clause that closes a hole found by watching this check fail. The sweep reads its
    # marks out of `NOTICE`, which is the right authority and means a *rename* of the token there
    # silently redirects the sweep at something no file uses — it then finds nothing and reads
    # exactly like a tree with nothing marked. Nothing else catches that while the enumeration is
    # empty. Two independently edited documents showing the same convention does catch it, today.
    assert shown_here == declared_in_notice, (
        f"README.md shows the prior-work marker as {shown_here} and {ROOT_NOTICE} declares it as "
        f"{declared_in_notice}. A reader follows whichever page they landed on, and the sweep "
        f"follows `NOTICE` — so a rename in one of the two aims the check at a token no file "
        f"carries, which looks identical to a tree with nothing to find."
    )


def test_every_marked_span_is_well_formed_and_names_an_enumerated_source_work() -> None:
    """The tree agrees with the front page about which lines are the owner's prior work.

    **Empty against empty on the commit that adds this**, and armed for the one that adds the
    first marker — which is the commit `docs/product-direction.md:84 's own prior's own prior work,
    in"` says owes it. The direction
    that bites first is a file marked and never enumerated: that is what a hurried copy looks like.
    """
    # Arrange
    declared = set(_declared_source_works((REPO_ROOT / "README.md").read_text(encoding="utf-8")))

    # Act
    sweep = _prior_work_spans(REPO_ROOT, tracked_files())
    unenumerated = sorted(
        f"{span.path}:{span.begin_line}-{span.end_line} names {span.source_work!r}"
        for span in sweep.spans
        if span.source_work not in declared
    )

    # Assert
    assert sweep.files_read > 500, (
        f"the sweep opened only {sweep.files_read} markable files in this repository, which is far "
        f"too few for it to be reading the tree — an empty result below would then mean 'nothing "
        f"was looked at' and read exactly like 'nothing is wrong'"
    )
    assert not sweep.malformed, (
        "prior-work markers in this tree are not well formed, so which lines are the owner's own "
        f"work is not a fact anyone can read: {sweep.malformed}"
    )
    assert not unenumerated, (
        f"{unenumerated} carry the owner's prior work under a source work README.md does not "
        f"enumerate. `NOTICE` case 2's promise is that a reader can tell the two origins apart "
        f"without asking, and the front page is where they look first — the enumeration is owed "
        f"in the same commit as the marker, not after it."
    )


def test_every_enumerated_source_work_is_actually_carried() -> None:
    """The other direction, and the one that goes stale silently.

    A source work left in the enumeration after its last marked line is deleted makes the front
    page claim a provenance the tree no longer has — and unlike the direction above, nothing about
    it ever fails to build. This is the clause that would notice.
    """
    # Arrange
    declared = _declared_source_works((REPO_ROOT / "README.md").read_text(encoding="utf-8"))

    # Act
    sweep = _prior_work_spans(REPO_ROOT, tracked_files())
    carried = {span.source_work for span in sweep.spans}

    # Assert
    assert sweep.files_read > 500, (
        f"the sweep opened only {sweep.files_read} markable files, so `carried` below is empty "
        f"because nothing was read rather than because nothing is marked"
    )

    # Assert
    assert not (set(declared) - carried), (
        f"README.md enumerates {sorted(set(declared) - carried)} and no file in this repository "
        f"marks a line as coming from it. Either the marker was removed and the enumeration was "
        f"not, or the enumeration was written ahead of the copy — and a provenance claim with "
        f"nothing behind it is the one a reader cannot check."
    )


def test_the_prior_work_marking_check_can_actually_fail(tmp_path: Path) -> None:
    """Planted, because the real tree carries no marked span and the sweep above therefore
    compares an empty set with an empty one (`docs/lessons.md` L5.19, L11.5).

    Every direction, on a fixture tree: a well-formed span **found** — the liveness half, without
    which the four assertions above are satisfied by a sweep that reads nothing — an unclosed span,
    a nested one, a span naming no source work, a stray close, a marked source work the
    enumeration omits, and an enumerated source work nothing carries. The marks come from
    `_convention` reading a real `NOTICE`, so the plant exercises the convention this repository
    actually declares rather than one restated here.
    """
    # Arrange
    begin_mark, end_mark = _convention(ROOT_NOTICE.read_text(encoding="utf-8"))
    (tmp_path / "NOTICE").write_text(ROOT_NOTICE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "good.py").write_text(
        f"# {begin_mark} some-earlier-project\nVALUE = 1\n# {end_mark}\nOWN = 2\n", encoding="utf-8"
    )
    (tmp_path / "unclosed.py").write_text(
        f"# {begin_mark} some-earlier-project\nVALUE = 1\n", encoding="utf-8"
    )
    (tmp_path / "nested.py").write_text(
        f"# {begin_mark} a\n# {begin_mark} b\nX = 1\n# {end_mark}\n", encoding="utf-8"
    )
    (tmp_path / "anonymous.py").write_text(
        f"# {begin_mark}\nX = 1\n# {end_mark}\n", encoding="utf-8"
    )
    (tmp_path / "stray.py").write_text(f"X = 1\n# {end_mark}\n", encoding="utf-8")
    (tmp_path / "prose.md").write_text(f"# {begin_mark} not-scanned\n", encoding="utf-8")
    planted = [
        "good.py",
        "unclosed.py",
        "nested.py",
        "anonymous.py",
        "stray.py",
        "prose.md",
    ]

    # Act
    spans, malformed, files_read = _prior_work_spans(tmp_path, planted)
    omitting = _declared_source_works(f"body\n\n{README_ANCHOR}\n\n- *(none)*\n")
    claiming = _declared_source_works(f"body\n\n{README_ANCHOR}\n\n- `never-carried` — a claim\n")

    # Assert
    assert spans, (
        "the sweep found no span in a fixture tree that plants a well-formed one, so every "
        "assertion above is being satisfied by a check that reads nothing"
    )
    assert PriorWorkSpan("good.py", "some-earlier-project", 1, 3) in spans
    assert not any(span.path == "prose.md" for span in spans), (
        "the sweep read a Markdown file, which is how `NOTICE` and the `docs/` tree end up "
        "reported as violations of the convention they describe"
    )
    assert [failure.split(":")[0] for failure in malformed] == sorted(
        ["anonymous.py", "nested.py", "stray.py", "unclosed.py"]
    ), f"a malformation went undetected: {malformed}"
    assert omitting == () and {span.source_work for span in spans} - set(omitting), (
        "a marked source work the enumeration omits must be detectable"
    )
    assert files_read == 5, (
        f"the sweep opened {files_read} of the 6 planted files; it must read the five markable "
        f"ones and skip prose.md, and a count that drifts means the allowlist changed under it"
    )
    assert set(claiming) - {span.source_work for span in spans} == {"never-carried"}, (
        "an enumerated source work nothing carries must be detectable"
    )
