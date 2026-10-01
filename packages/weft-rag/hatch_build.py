"""Stamps a wheel with the commit it was built from — carried repair **R44.7**.

A wheel built for distribution has no `.git`, so `weft_cli.provenance.source_revision` has
nothing to ask once installed. This hook writes `git rev-parse HEAD` and whether the tree was
dirty into `weft_eval/_build_revision.json` at build time — for the sdist and, when a checkout
is directly available, the wheel too — so an installed wheel still names the commit it came from.

It also carries the evidence claim documents (`eval/claims/*.toml`) into
`weft_eval/shipped_claims/`, so an installed wheel can hold a router a project derives to the claims
it cites (`weft_cli.evidence_guard`). They are authored once, in the repository, and copied at build
time rather than kept twice.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_STAMP_NAME = "_build_revision.json"
_CLAIMS_RELATIVE = Path("eval") / "claims"


class BuildRevisionStampHook(BuildHookInterface[Any]):
    """Writes `weft_eval/_build_revision.json` from `git`, when a checkout is available.

    Silent when it is not: a wheel built from an unpacked sdist has no `.git` above it, and by
    then the sdist already carries the stamp as an ordinary package file, which the wheel's own
    `packages` selection picks up unchanged.
    """

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Add the stamp to `build_data["force_include"]`, unless this build has no checkout."""
        if version == "editable":
            return

        self._include_claims(build_data)
        commit = self._run_git("rev-parse", "HEAD")
        if commit is None:
            return
        status = self._run_git("status", "--porcelain", "--untracked-files=no")
        dirty = bool(status.strip()) if status is not None else None

        stamp_dir = Path(mkdtemp(prefix="weft-build-revision-"))
        stamp_path = stamp_dir / _STAMP_NAME
        stamp_path.write_text(
            json.dumps({"commit": commit.strip(), "dirty": dirty}), encoding="utf-8"
        )

        prefix = "src/" if self.target_name == "sdist" else ""
        build_data["force_include"][str(stamp_path)] = f"{prefix}weft_eval/{_STAMP_NAME}"

    def _include_claims(self, build_data: dict[str, Any]) -> None:
        """Add every `eval/claims/*.toml` of the checkout, or nothing when this build has none.

        An unpacked sdist has no `eval/` above it, and by then it already carries the claims as
        package files, which the wheel's own `packages` selection picks up unchanged.
        """
        source = Path(self.root).resolve().parents[1] / _CLAIMS_RELATIVE
        if not source.is_dir():
            return
        prefix = "src/" if self.target_name == "sdist" else ""
        for claim in sorted(source.glob("*.toml")):
            build_data["force_include"][str(claim)] = (
                f"{prefix}weft_eval/shipped_claims/{claim.name}"
            )

    def _run_git(self, *args: str) -> str | None:
        """`git -C self.root <args>`'s stdout, or `None` when git is missing or fails."""
        git = shutil.which("git")
        if git is None:
            return None
        try:
            result = subprocess.run(  # noqa: S603 — a literal argv, no shell, nothing interpolated
                [git, "-C", self.root, *args],
                capture_output=True,
                text=True,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None
        return result.stdout
