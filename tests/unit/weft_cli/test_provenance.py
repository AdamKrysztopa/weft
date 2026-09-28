"""The revision of the code a run executed — task 44.4.

`source_revision` reads git in the directory the installed `weft_eval` was loaded from, never the
working directory: an operator running an installed wheel from inside this repository must not
record this repository's commit as the code that ran. Outside any checkout it says so.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from weft_cli.provenance import source_revision

REPO_ROOT = Path(__file__).resolve().parents[3]


async def test_a_checkout_s_revision_is_its_head_commit() -> None:
    # Arrange — the other side comes from git itself, not from the code under test.
    git = shutil.which("git")
    assert git is not None
    head = subprocess.run(  # noqa: S603 — a literal argv, no shell, nothing interpolated
        [git, "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # Act
    revision = await source_revision(REPO_ROOT / "packages" / "weft-rag" / "src" / "weft_eval")

    # Assert
    assert revision.commit == head
    assert isinstance(revision.dirty, bool)


async def test_a_directory_outside_any_checkout_has_no_revision(tmp_path: Path) -> None:
    # Act
    revision = await source_revision(tmp_path)

    # Assert
    assert revision.commit is None
    assert revision.dirty is None


async def test_by_default_the_revision_is_the_installed_weft_eval_s_not_the_working_directory_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — standing outside any checkout must not change the answer.
    monkeypatch.chdir(tmp_path)
    expected = await source_revision(REPO_ROOT / "packages" / "weft-rag" / "src" / "weft_eval")

    # Act
    revision = await source_revision()

    # Assert
    assert revision == expected


async def test_outside_a_checkout_a_build_stamp_beside_the_package_is_the_revision(
    tmp_path: Path,
) -> None:
    # Arrange — R44.7: what an installed wheel carries, since it has no checkout to ask.
    (tmp_path / "_build_revision.json").write_text(
        '{"commit": "0123456789abcdef0123456789abcdef01234567", "dirty": false}', encoding="utf-8"
    )

    # Act
    revision = await source_revision(tmp_path)

    # Assert
    assert revision.commit == "0123456789abcdef0123456789abcdef01234567"
    assert revision.dirty is False
