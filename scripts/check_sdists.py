"""Nothing load-bearing is in the checkout and absent from the artefact — ledger task **6.7**.

`docs/09-release.md` §5.2, *Install path*: "The sdist builds and its tests pass from the sdist.
*Fails if a data file, locale catalogue or entry-point declaration is present in the checkout and
absent from the artefact.*"

Two readers, one comparison. `files_that_must_ship` reads the checkout; `sdist_contents` reads an
archive; `main` builds every published distribution's sdist with `uv build`, diffs the two sets per
distribution, and — only when `--run-tests` is passed — installs every built sdist together into one
clean environment and runs this repository's test suite against the artefacts rather than the
editable workspace. Modelled on `scripts/check_isolated_installs.py`: fixed argv, no shell, nothing
user-controlled, `check=False`, `capture_output=True`.
"""

import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from publish_set import Member, PublishSetUnreadableError, publishing_members

#: Directory entries and build droppings never belong in the required set — a required set that
#: swept those in would fail on any machine that had ever run the tests (`test_sdist_completeness`).
_EXCLUDED_DIR: str = "__pycache__"
_EXCLUDED_SUFFIX: str = ".pyc"

#: Ledger task 6.11, `docs/09-release.md` §5.2: the licence travels with the artefact rather than
#: with the repository, so every distribution's `pyproject.toml` now declares `license-files`
#: naming its own `LICENSE`/`NOTICE` copies. This is the check that proves those two files are
#: actually *in* the tarball, not merely sitting in the distribution's directory.
_LICENCE_FILES: frozenset[str] = frozenset({"LICENSE", "NOTICE"})


def files_that_must_ship(member: Member) -> frozenset[str]:
    """Every path that must appear in `member`'s sdist, relative to the distribution directory.

    `pyproject.toml` always, because it carries the entry-point declarations `09` §5.2 names,
    plus `LICENSE` and `NOTICE` (task 6.11), plus every file under `<member.directory>/src/`,
    recursively, excluding `__pycache__` and `.pyc` build droppings. A member with no `src/`
    directory (the code-free release set `weft`) still ships its licence and notice, so it
    yields exactly `{"pyproject.toml", "LICENSE", "NOTICE"}`.
    """
    required = {"pyproject.toml", *_LICENCE_FILES}

    src_dir = member.directory / "src"
    if not src_dir.is_dir():
        return frozenset(required)

    for path in src_dir.rglob("*"):
        if not path.is_file():
            continue
        if _EXCLUDED_DIR in path.relative_to(src_dir).parts:
            continue
        if path.suffix == _EXCLUDED_SUFFIX:
            continue
        relative = path.relative_to(member.directory).as_posix()
        required.add(relative)

    return frozenset(required)


def sdist_contents(archive: Path) -> frozenset[str]:
    """Every file in `archive`, with the single leading `<name>-<version>/` component stripped."""
    contents: set[str] = set()

    with tarfile.open(archive, "r:gz") as tar:
        for info in tar.getmembers():
            if not info.isfile():
                continue
            posix_name = Path(info.name).as_posix()
            _root, _sep, rest = posix_name.partition("/")
            if rest:
                contents.add(rest)

    return frozenset(contents)


def _build_sdist(name: str, out_dir: Path) -> subprocess.CompletedProcess[str]:
    command = ["uv", "build", "--sdist", "--package", name, "--out-dir", str(out_dir)]
    # Fixed argv, no shell, nothing user-controlled.
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


def _find_archive(out_dir: Path, name: str) -> Path | None:
    normalised = name.replace("-", "_")
    candidates = sorted(out_dir.glob(f"{normalised}-*.tar.gz"))
    return candidates[0] if candidates else None


#: The suites that are claims about **the code**, and therefore about the artefacts once the
#: artefacts are what is installed. `tests/architecture` and `tests/docs` are deliberately not
#: here: they are claims about *the checkout* — they read `packages/*/pyproject.toml`, walk the
#: repository and assert about the workspace — so running them in an artefact environment asks
#: them a question they were not written to answer, and two of them cannot answer it even in
#: principle (`tests/architecture/test_ff8_trust_model.py` needs `weft-canary` installed, and
#: `weft-canary` is deliberately never published — task 6.2's opt-out marker). See
#: `docs/lessons.md` L6.25: a suite that asserts over the repository does not become a stronger
#: claim by being run against an install, it becomes a wrong one.
_SUITES_ABOUT_THE_CODE: tuple[str, ...] = ("tests/unit", "tests/integration")


def _run_tests_against_sdists(archives: list[Path], repo_root: Path) -> int:
    command = [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        *[part for archive in archives for part in ("--with", str(archive))],
        "--with",
        "pytest",
        "--with",
        "pytest-asyncio",
        "--with",
        "pytest-timeout",
        # `weft-cli[reference]`'s own extra, installed here for the same reason `pytest` is: the
        # tests exercise the contract-reference generator, which shells out to it. Task 6.7
        # declared it; before that it was reachable only through the workspace's dev group
        # (`docs/lessons.md` L6.24).
        "--with",
        "ruff>=0.16.0",
        "pytest",
        *_SUITES_ABOUT_THE_CODE,
        "-q",
    ]
    # Fixed argv, no shell, nothing user-controlled.
    result = subprocess.run(  # noqa: S603
        command, capture_output=True, text=True, check=False, cwd=repo_root
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    run_tests = "--run-tests" in sys.argv[1:]

    try:
        members = publishing_members(repo_root)
    except PublishSetUnreadableError as error:
        sys.stderr.write(f"could not enumerate the published set: {error}\n")
        return 1

    failures: list[str] = []
    built_archives: list[Path] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = Path(tmp_dir)

        for member in members:
            built = _build_sdist(member.name, out_dir)
            sys.stdout.write(built.stdout)
            sys.stderr.write(built.stderr)

            if built.returncode != 0:
                sys.stderr.write(f"\n{member.name} could not be built as an sdist.\n")
                failures.append(member.name)
                continue

            archive = _find_archive(out_dir, member.name)
            if archive is None:
                sys.stderr.write(
                    f"\n{member.name} was built but no matching .tar.gz was found in {out_dir}.\n"
                )
                failures.append(member.name)
                continue

            try:
                shipped = sdist_contents(archive)
            except (tarfile.TarError, OSError) as error:
                sys.stderr.write(f"\n{member.name}'s sdist could not be read: {error}\n")
                failures.append(member.name)
                continue

            missing = files_that_must_ship(member) - shipped
            if missing:
                sys.stderr.write(
                    f"\n{member.name}: a data file, locale catalogue or entry-point declaration "
                    f"is present in the checkout and absent from the artefact — missing "
                    f"{sorted(missing)}\n"
                )
                failures.append(member.name)
                continue

            built_archives.append(archive)
            sys.stdout.write(f"{member.name}: the sdist carries everything the checkout has.\n")

        if failures:
            sys.stderr.write(f"\nfailed: {', '.join(sorted(failures))}\n")
            return 1

        if not run_tests:
            sys.stdout.write("\n(--run-tests not passed: the suite was not run from the sdists)\n")
            return 0

        sys.stdout.write("\nrunning the test suite against the built sdists...\n")
        test_returncode = _run_tests_against_sdists(built_archives, repo_root)
        if test_returncode != 0:
            sys.stderr.write("\nthe test suite failed when run against the built sdists.\n")
            return test_returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
