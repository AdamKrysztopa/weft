"""The git revision of the code that ran — task **44.4**.

`source_revision` reads git in the directory the installed `weft_eval` package was loaded from,
never `Path.cwd()`: an operator running an installed wheel from inside this repository must not
have this repository's own commit recorded as the code that ran. Outside any git checkout — a
wheel install with no `.git` above it — it says so with `commit=None, dirty=None` rather than
raising, because "not a checkout" is itself the fact worth recording, not a failure.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import weft_eval
from weft_eval.run_record import SourceRevision


async def source_revision(directory: Path | None = None) -> SourceRevision:
    """The git revision of `directory`, defaulting to the installed `weft_eval`'s own directory.

    `commit`/`dirty` are both `None` when `git` is not on `PATH`, `directory` is not inside a git
    checkout, or `git rev-parse HEAD` otherwise fails — `SourceRevision`'s own footing for that
    case.
    """
    target = directory if directory is not None else Path(weft_eval.__file__).resolve().parent
    git = shutil.which("git")
    if git is None:
        return SourceRevision(commit=None, dirty=None)

    commit = await _run_git(git, target, "rev-parse", "HEAD")
    if commit is None:
        return SourceRevision(commit=None, dirty=None)

    status = await _run_git(git, target, "status", "--porcelain", "--untracked-files=no")
    dirty = bool(status.strip()) if status is not None else None
    return SourceRevision(commit=commit.strip(), dirty=dirty)


async def _run_git(git: str, directory: Path, *args: str) -> str | None:
    """`git -C directory <args>`'s stdout, or `None` on a non-zero exit."""
    process = await asyncio.create_subprocess_exec(
        git,
        "-C",
        str(directory),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await process.communicate()
    if process.returncode != 0:
        return None
    return stdout.decode("utf-8")
