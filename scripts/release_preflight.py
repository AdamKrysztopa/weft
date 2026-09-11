"""The preconditions for a `v*` tag that a machine can hold. `docs/09-release.md` §1.1 is the rest.

A version number on PyPI is not reusable, so a wheel uploaded against a stale README can only be
superseded, never replaced. `v2.1.0` shipped with a five-phase-old changelog, no assets and a front
page reading "Status: Phase 0, not yet built"; nothing checked any of it.

Not in `ci-checks`: it asks the index what it holds, and that answer changes the moment a release
succeeds. `http.client` rather than `urllib.request` because an `HTTPSConnection` to a named host
cannot be talked into opening a `file://` URL.
"""

from __future__ import annotations

import http.client
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Final, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish_set import REPO_ROOT, publishing_members  # noqa: E402

_INDEX_HOST: Final[str] = "pypi.org"
_INDEX_PATH: Final[str] = "/pypi/{name}/json"

#: `## [2.4.0] - 2026-09-11` — the heading shape `CHANGELOG.md` declares it follows.
_RELEASED_HEADING: Final[re.Pattern[str]] = re.compile(
    r"^## \[(?P<version>\d+\.\d+\.\d+)\] - (?P<date>\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE
)

_UNRELEASED_HEADING: Final[str] = "## [Unreleased]"

#: `09` §1: the documentation, the baseline and the support window are stated against the release
#: set, so a `v*` tag names its version and not the kernel's.
_RELEASE_SET: Final[str] = "weft-rag"


class PreflightError(Exception):
    """One precondition that does not hold. Collected, never raised — every one is reported."""


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _project_table(directory: Path) -> dict[str, Any]:
    project = _load_toml(directory / "pyproject.toml").get("project")
    if not isinstance(project, dict):
        message = f"{directory}/pyproject.toml declares no [project] table"
        raise PreflightError(message)
    return cast(dict[str, Any], project)


def _versions_on_the_index(name: str) -> frozenset[str] | None:
    """Versions the index holds for `name`; `None` if no such project — not the same thing."""
    connection = http.client.HTTPSConnection(_INDEX_HOST, timeout=30)
    try:
        connection.request("GET", _INDEX_PATH.format(name=name), headers={"Accept": "*/*"})
        response = connection.getresponse()
        body = response.read()
        status = response.status
    except OSError as error:
        message = f"the index was unreachable for {name} ({error}); preflight is not a pass"
        raise PreflightError(message) from error
    finally:
        connection.close()
    if status == 404:
        return None
    if status != 200:
        message = f"the index answered {status} for {name}; preflight cannot tell what it holds"
        raise PreflightError(message)
    releases = cast(dict[str, Any], json.loads(body)).get("releases")
    if not isinstance(releases, dict):
        message = f"the index's JSON for {name} carries no 'releases' map"
        raise PreflightError(message)
    return frozenset(str(version) for version in cast(dict[str, Any], releases))


def _version_failures() -> list[str]:
    """No version about to be uploaded may already exist on the index."""
    failures: list[str] = []
    for member in publishing_members():
        version = _project_table(member.directory).get("version")
        if not isinstance(version, str):
            failures.append(f"{member.name} declares no version")
            continue
        try:
            published = _versions_on_the_index(member.name)
        except PreflightError as error:
            failures.append(str(error))
            continue
        if published is None:
            print(f"  {member.name} {version} — the index holds no such project yet")
            continue
        if version in published:
            failures.append(
                f"{member.name} {version} is ALREADY on the index and a version is not reusable; "
                f"bump it or the release job will refuse the file"
            )
            continue
        print(f"  {member.name} {version} — free ({len(published)} version(s) already published)")
    return failures


def _readme_failures() -> list[str]:
    """Every published distribution's README is its project page. `weft-kernel` declared none."""
    failures: list[str] = []
    for member in publishing_members():
        declared = _project_table(member.directory).get("readme")
        if not isinstance(declared, str):
            failures.append(f"{member.name} declares no [project] readme; its page will be bare")
            continue
        readme = member.directory / declared
        if not readme.is_file():
            failures.append(f"{member.name} declares readme {declared!r}, which does not exist")
            continue
        if not readme.read_text(encoding="utf-8").strip():
            failures.append(f"{member.name}'s readme {declared!r} is empty")
    return failures


def _changelog_failures(version: str) -> list[str]:
    """The tag has a dated section, and `[Unreleased]` has been emptied into it."""
    failures: list[str] = []
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = {match["version"]: match["date"] for match in _RELEASED_HEADING.finditer(text)}
    if version not in headings:
        failures.append(
            f"CHANGELOG.md has no '## [{version}] - <date>' section; "
            f"it carries {sorted(headings) or 'no released sections at all'}"
        )
    start = text.find(_UNRELEASED_HEADING)
    if start < 0:
        failures.append(f"CHANGELOG.md has no {_UNRELEASED_HEADING} heading for the next release")
        return failures
    body = text[start + len(_UNRELEASED_HEADING) :]
    next_heading = body.find("\n## ")
    remainder = (body if next_heading < 0 else body[:next_heading]).strip()
    if remainder:
        failures.append(
            f"{_UNRELEASED_HEADING} still holds {len(remainder.splitlines())} line(s); "
            f"a cut release leaves it empty"
        )
    return failures


def _tag_failures(version: str) -> list[str]:
    """The tag names the release set's version."""
    members = {member.name: member for member in publishing_members()}
    release_set = members.get(_RELEASE_SET)
    if release_set is None:
        return [f"{_RELEASE_SET} is not in the publishing set; this file's premise is stale"]
    declared = _project_table(release_set.directory).get("version")
    if declared == version:
        return []
    return [
        f"tag v{version} does not name {_RELEASE_SET}'s version ({declared!r}); "
        f"a tag names the release set"
    ]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} vX.Y.Z", file=sys.stderr)
        return 2
    tag = argv[1]
    if not tag.startswith("v"):
        print(f"a release tag is 'vX.Y.Z'; got {tag!r}", file=sys.stderr)
        return 2
    version = tag[1:]

    checks: list[tuple[str, list[str]]] = []
    print("versions against the index:")
    checks.append(("versions", _version_failures()))
    print("the tag:")
    checks.append(("tag", _tag_failures(version)))
    print("the changelog:")
    checks.append(("changelog", _changelog_failures(version)))
    print("project pages:")
    checks.append(("readmes", _readme_failures()))

    failures = [(name, failure) for name, group in checks for failure in group]
    if failures:
        print(f"\n{len(failures)} precondition(s) do not hold for {tag}:", file=sys.stderr)
        for name, failure in failures:
            print(f"  [{name}] {failure}", file=sys.stderr)
        return 1
    print(f"\npreflight clear for {tag}. The four this file cannot hold are `09` §1.1's:")
    print("  the gate is green in the environment the release runs in, container up;")
    print("  the working tree is committed and the lockfile is the committed one;")
    print("  the binary has been run from outside this repository, failure path included;")
    print("  PyPI's cooling window is clear — release.yml refuses the run if it is not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
