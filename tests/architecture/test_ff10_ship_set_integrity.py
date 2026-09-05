"""Fitness function 10 — ship-set integrity. Ledger task **6.2** builds clause (a).

`docs/01-high-level-plan.md` → *Fitness functions* 10(a), quoted because this file exists to be
held to it rather than to paraphrase it:

    **The publish set and the workspace agree.** Two sets are computed from **different sources**
    and compared: on one side, the distributions the release job actually passes to the index; on
    the other, the workspace members (`[tool.uv.workspace] members`) that do not carry an opt-out
    marker in their own `pyproject.toml`. The check fails if either side holds a distribution the
    other does not. [...] `testing/weft-canary` — whose entire purpose is to be *refused* by
    discovery (fitness function 8) — is the standing test case: it must always be on the opt-out
    side and never in the publish job's arguments.

**Why the two sides are read from two files that can genuinely disagree.** `01` states the reason
in the clause itself: a check that asked the derivation function what it derives would compare a
function to itself and could never fail. So the publish side is parsed out of
`.github/workflows/release.yml` — the artefact CI actually runs, hand-maintained on purpose — and
the workspace side is expanded from the root `pyproject.toml`'s member globs. Adding a package and
forgetting the workflow fails here; publishing something that opted out fails here.

**Neither side may answer emptily.** An empty collection means *"I did not find it"*, never *"it is
not there"* (`docs/lessons.md` L5.9, L6.14) — and a comparison between two empty sets passes while
checking nothing, which is exactly the vacuous pass L5.19 requires a floor against. Both readers
therefore raise rather than return `frozenset()`, and the equality test asserts each side is
non-empty before comparing them.

**Clause (b) — no distribution depends on a sibling without a version bound — is ledger task 6.3**,
below. `01` states it as *"a property over the workspace rather than as a lint of one file"*, and it
exists because the tree once declared `dependencies = ["weft-kernel"]` in every pack, which permits
any pack against any kernel and leaves **any** compatibility policy unenforceable.

**Its subject is already satisfied, which is exactly when a check is most likely to be worthless.**
G9's enforcement rule landed in Phase 5, so every intra-repository requirement in the workspace
already carries a bound — `09` §1 records G10's own *Bring* prediction of zero being falsified on
the day, the answer being all of them. A check written against a set that already agrees passes
whether or not it can read anything, so the floor here is `docs/lessons.md` L5.19's: the comparison
is proved non-vacuous (the edge population is non-empty and the kernel is visible in it) and a
planted bare requirement is watched going red.

**What a bound means is not this clause's to choose.** `01`: *"a floor, a compatible range, or an
exact pin — is G9's and this clause does not choose: a floor is the weakest of the three and is
implied by all of them"*. So this check asks only for a lower bound, and the release set's exact
pins (`weft-kernel==0.1.0`) satisfy it as readily as a pack's `>=0.1.0,<1.0.0`. **Do not tighten
this into G9's rule** — G9 settled that ranges are `>=X,<MAJOR+1` *and never exact pins*, which is
true of a pack depending on a contract publisher and deliberately false of the release set, whose
entire purpose is to pin what was tested together (`09` §1). Those are two rules with two subjects;
collapsing them here would fail the release set for being what G10 settled it should be.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Final, cast

import pytest
import yaml
from packaging.requirements import Requirement
from publish_set import PublishSetUnreadableError, publishing_members

from .conftest import REPO_ROOT

RELEASE_WORKFLOW: Final[Path] = REPO_ROOT / ".github" / "workflows" / "release.yml"

#: The matrix key whose values are the distributions a job passes to the index. Every job in the
#: workflow is read, not one named job: the release set is published by a second job that `needs`
#: the first, because `weft` pins exact versions that must reach the index before it does. A reader
#: keyed to one job name would have gone blind to that second job's arguments the moment it was
#: added, which is `docs/lessons.md` L6.4 — read the population, not a declaration.
PUBLISH_MATRIX_KEY: Final[str] = "distribution"

#: `[tool.weft] publish = false` in a distribution's own `pyproject.toml`. `01` requires "an
#: opt-out marker" and does not spell one, so this file spells it: a marker in the distribution
#: that opts out, never a list held somewhere central, because a central list is a second
#: description of the same fact and drifts from it.
OPT_OUT_TABLE: Final[str] = "weft"
OPT_OUT_KEY: Final[str] = "publish"

#: The standing test case `01` names. Its entire purpose is to be refused by discovery, so it must
#: be on the opt-out side and never in the publish job's arguments.
CANARY: Final[str] = "weft-canary"


class ShipSetUnreadableError(Exception):
    """A side of the comparison could not be read, which is not the same as it being empty."""


def _toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _table(value: object, key: str) -> dict[str, object]:
    """The sub-table at `key`, or an empty one. YAML is `object` until it proves otherwise."""
    if isinstance(value, dict):
        inner = cast("dict[str, object]", value).get(key)
        if isinstance(inner, dict):
            return cast("dict[str, object]", inner)
    return {}


def published_distributions(workflow: Path = RELEASE_WORKFLOW) -> frozenset[str]:
    """What the release job actually passes to the index, read off the workflow it runs."""
    if not workflow.is_file():
        raise ShipSetUnreadableError(
            f"{workflow} does not exist. Fitness function 10(a) compares the distributions the "
            f"release job passes to the index against the workspace; with no release job there is "
            f"no publish side, and an absent file is not an empty publish set."
        )

    document: object = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    jobs = _table(document, "jobs")
    names: set[str] = set()

    for job in jobs.values():
        values = _table(_table(job, "strategy"), "matrix").get(PUBLISH_MATRIX_KEY)
        if isinstance(values, list):
            names.update(str(value) for value in cast("list[object]", values))

    if not names:
        raise ShipSetUnreadableError(
            f"no job in {workflow} declares a non-empty strategy.matrix.{PUBLISH_MATRIX_KEY} "
            f"list. Its jobs are {sorted(jobs)}; those lists are the publish set, and a reader "
            f"that finds none is wrong rather than looking at a release that publishes nothing."
        )

    return frozenset(names)


def workspace_distributions(repo_root: Path = REPO_ROOT) -> frozenset[str]:
    """Every workspace member that does not opt out — read through the one reader that owns it.

    `scripts/publish_set.publishing_members` is that reader, built at ledger task **6.6**, and
    it is called here rather than copied because "which members publish" is one fact: the
    opt-out marker, the member globs and the skip rules would otherwise be spelled twice and
    could disagree, which is the two-lists shape `docs/README.md`'s own opening rule is written
    about. It changes nothing about clause (a)'s independence — the *other* side is parsed out
    of `.github/workflows/release.yml`, which this reader never opens.
    """
    try:
        return frozenset(member.name for member in publishing_members(repo_root))
    except PublishSetUnreadableError as error:
        raise ShipSetUnreadableError(str(error)) from error


def test_the_publish_set_and_the_workspace_agree() -> None:
    """Clause (a) itself: two sets, two sources, symmetric difference empty."""
    # Arrange
    published = published_distributions()
    workspace = workspace_distributions()

    # Act
    published_only = published - workspace
    workspace_only = workspace - published

    # Assert
    assert published, "the publish side read as empty — see `published_distributions`"
    assert workspace, "the workspace side read as empty — see `workspace_distributions`"
    assert not published_only, (
        f"{sorted(published_only)} would be published and are not workspace members that publish. "
        f"Either the release job names something that does not exist, or the distribution opted "
        f"out of publishing and the workflow was not told (`01` → *Fitness functions* 10(a))."
    )
    assert not workspace_only, (
        f"{sorted(workspace_only)} are workspace members with no opt-out marker and the release "
        f"job never passes them to the index. Add them to a "
        f"`{RELEASE_WORKFLOW.name}` job's '{PUBLISH_MATRIX_KEY}' matrix, or declare "
        f"`[tool.{OPT_OUT_TABLE}] {OPT_OUT_KEY} = false` in the distribution's own pyproject.toml "
        f"and say why."
    )


def test_the_canary_opts_out_and_is_never_passed_to_an_index() -> None:
    """`01` 10(a)'s standing test case, and the edge the whole clause was written around."""
    # Arrange
    canary_manifest = REPO_ROOT / "testing" / "weft-canary" / "pyproject.toml"

    # Act
    marker = _toml(canary_manifest).get("tool", {}).get(OPT_OUT_TABLE, {}).get(OPT_OUT_KEY)

    # Assert
    assert marker is False, (
        f"{canary_manifest} must declare `[tool.{OPT_OUT_TABLE}] {OPT_OUT_KEY} = false`. Its "
        f"whole purpose is to be refused by discovery (fitness function 8); a distribution that "
        f"exists to be refused must never reach an index."
    )
    assert CANARY not in published_distributions()
    assert CANARY not in workspace_distributions()


def test_an_unreadable_publish_side_is_refused_rather_than_read_as_empty(tmp_path: Path) -> None:
    """`docs/lessons.md` L5.9: an empty answer is "I did not find it", never "it is not there"."""
    # Arrange
    workflow = tmp_path / "release.yml"
    workflow.write_text("jobs:\n  gate:\n    runs-on: ubuntu-latest\n", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ShipSetUnreadableError, match=PUBLISH_MATRIX_KEY):
        published_distributions(workflow)

    with pytest.raises(ShipSetUnreadableError, match="does not exist"):
        published_distributions(tmp_path / "absent.yml")


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Clause (b) of fitness function 16: plant a disagreement and watch the comparison go red.

    Planted through the **real readers** rather than against literal sets, so what is proven is
    that the parse and the comparison together can disagree — a self-test over hand-written sets
    would prove only that `frozenset.__sub__` works.
    """
    # Arrange — a workspace whose one publishing member the release job never names, and a
    # release job naming one the workspace does not have.
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n', encoding="utf-8"
    )
    for name, opts_out in (("weft-planted", False), ("weft-planted-optout", True)):
        member = tmp_path / "packages" / name
        member.mkdir(parents=True)
        marker = f"\n[tool.{OPT_OUT_TABLE}]\n{OPT_OUT_KEY} = false\n" if opts_out else ""
        (member / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.0.0"\n{marker}', encoding="utf-8"
        )
    workflow = tmp_path / "release.yml"
    workflow.write_text(
        f"jobs:\n  publish:\n    strategy:\n      matrix:\n"
        f"        {PUBLISH_MATRIX_KEY}: [weft-planted-optout]\n"
        f"  publish-release-set:\n    needs: publish\n    strategy:\n      matrix:\n"
        f"        {PUBLISH_MATRIX_KEY}: [weft-never-existed]\n",
        encoding="utf-8",
    )

    # Act
    published = published_distributions(workflow)
    workspace = workspace_distributions(tmp_path)

    # Assert — both directions of the failure `01` describes, and the opt-out marker respected.
    assert workspace == frozenset({"weft-planted"})
    assert published - workspace == frozenset({"weft-planted-optout", "weft-never-existed"})
    assert workspace - published == frozenset({"weft-planted"})


# ---------------------------------------------------------------------------
# Clause (b) — no distribution depends on a sibling without a version bound.
# ---------------------------------------------------------------------------

#: The specifier operators that place a **lower** bound on a sibling. `01` names the three shapes a
#: bound may take — "a floor, a compatible range, or an exact pin" — and every one of them pins the
#: bottom. A lone `<1.0.0` or `!=1.2` is a specifier and not a bound: it still permits any older
#: release, which is the unenforceable state the clause exists to end.
LOWER_BOUND_OPERATORS: Final[frozenset[str]] = frozenset({">=", ">", "==", "===", "~="})


def intra_repository_requirements(
    repo_root: Path = REPO_ROOT,
) -> list[tuple[str, str, Requirement]]:
    """Every `(distribution, field, requirement)` in the workspace that names a sibling.

    Both published dependency tables are swept — `project.dependencies` and
    `project.optional-dependencies` — because an extra is shipped metadata and an unbounded sibling
    in one is the same hole as in the other. `[dependency-groups]` deliberately is not: a dev group
    is never installed by anyone depending on the distribution, so it is not something "a
    distribution depends on" in the sense `01` states.
    """
    manifests: dict[str, dict[str, Any]] = {}
    members = cast(
        "list[str]",
        _toml(repo_root / "pyproject.toml")["tool"]["uv"]["workspace"]["members"],
    )

    for pattern in members:
        for member in sorted(repo_root.glob(pattern)):
            manifest = member / "pyproject.toml"
            if manifest.is_file():
                project = cast("dict[str, Any]", _toml(manifest)["project"])
                manifests[cast("str", project["name"])] = project

    if not manifests:
        raise ShipSetUnreadableError(
            f"no workspace member under {repo_root} yielded a [project] table. Fitness function "
            f"10(b) is a property over the workspace; a workspace that reads as empty means the "
            f"reader is wrong, not that there are no intra-repository dependencies to bound."
        )

    siblings = frozenset(manifests)
    found: list[tuple[str, str, Requirement]] = []

    for name, project in sorted(manifests.items()):
        fields: list[tuple[str, list[str]]] = [
            ("dependencies", cast("list[str]", project.get("dependencies", [])))
        ]
        extras = cast("dict[str, list[str]]", project.get("optional-dependencies", {}))
        fields.extend(
            (f"optional-dependencies.{extra}", values) for extra, values in extras.items()
        )

        for field, requirements in fields:
            for text in requirements:
                requirement = Requirement(text)
                if requirement.name in siblings:
                    found.append((name, field, requirement))

    return found


def test_no_distribution_depends_on_a_sibling_without_a_version_bound() -> None:
    """Clause (b). `01` → *Fitness functions* 10(b)."""
    # Arrange
    edges = intra_repository_requirements()

    # Act
    unbounded = [
        f"{name} → {requirement} (in {field})"
        for name, field, requirement in edges
        if not any(
            specifier.operator in LOWER_BOUND_OPERATORS for specifier in requirement.specifier
        )
    ]
    depended_upon = {requirement.name for _, _, requirement in edges}

    # Assert — non-vacuity first (`docs/lessons.md` L5.19): a check over a set that already agrees
    # passes identically when the reader is broken, so the population is proved real before it is
    # judged.
    assert edges, "no intra-repository dependency was found at all — the reader is wrong"
    assert "weft-kernel" in depended_upon, (
        "no distribution was seen depending on `weft-kernel`. Every pack depends on the kernel by "
        "construction (G1), so a sweep that cannot see those edges is not reading the workspace."
    )
    assert not unbounded, (
        f"{unbounded} depend on a sibling with no lower bound. `01` → *Fitness functions* 10(b): "
        f"an unbounded requirement permits any pack against any kernel, and **any** compatibility "
        f"policy is unenforceable on top of one. Declare a bound — G9 settled the shape as "
        f"`>=X,<MAJOR+1` for a pack; the release set pins exactly (`09` §1)."
    )


def test_the_bound_check_can_actually_fail(tmp_path: Path) -> None:
    """Fitness function 16 clause (b), for clause (b) — planted through the real reader.

    The real workspace agrees today and has since Phase 5, so this is the only place the
    comparison is watched disagreeing.
    """
    # Arrange — two members, one declaring a bare sibling and one a ceiling with no floor.
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n', encoding="utf-8"
    )
    for name, requirement in (
        ("weft-kernel", None),
        ("weft-planted-bare", '"weft-kernel"'),
        ("weft-planted-ceiling", '"weft-kernel<1.0.0"'),
        ("weft-planted-bounded", '"weft-kernel>=0.1.0,<1.0.0"'),
    ):
        member = tmp_path / "packages" / name
        member.mkdir(parents=True)
        declares = f"dependencies = [{requirement}]\n" if requirement else ""
        (member / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.0.0"\n{declares}', encoding="utf-8"
        )

    # Act
    edges = intra_repository_requirements(tmp_path)
    unbounded = {
        name
        for name, _, requirement in edges
        if not any(
            specifier.operator in LOWER_BOUND_OPERATORS for specifier in requirement.specifier
        )
    }

    # Assert
    assert len(edges) == 3, "the reader missed a sibling edge it was handed"
    assert unbounded == {"weft-planted-bare", "weft-planted-ceiling"}
