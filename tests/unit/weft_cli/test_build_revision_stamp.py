"""A built `weft-rag` wheel names the commit it was built from — carried repair **R44.7**.

A paid run executes an installed wheel, and a wheel has no checkout for `source_revision` to ask,
so every such record said `commit=None` (E2's did). The build stamps the revision into the wheel
as `weft_eval/_build_revision.json`. Built here the way `uv build` builds by default — the sdist,
then the wheel from the unpacked sdist, which has no `.git` — so the stamp must travel through
the sdist, and nothing may be written into the checkout.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
_STAMP = "weft_eval/_build_revision.json"


def _head() -> str:
    git = shutil.which("git")
    assert git is not None
    return subprocess.run(  # noqa: S603 — a literal argv, no shell, nothing interpolated
        [git, "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.mark.timeout(300)
def test_a_wheel_built_through_its_sdist_carries_the_head_commit(tmp_path: Path) -> None:
    # Arrange
    uv = shutil.which("uv")
    assert uv is not None
    head = _head()

    # Act
    result = subprocess.run(  # noqa: S603 — a literal argv, no shell
        [uv, "build", "--package", "weft-rag", "--out-dir", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=280,
        check=False,
    )

    # Assert
    assert result.returncode == 0, result.stderr
    [wheel] = sorted(tmp_path.glob("weft_rag-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        stamp = json.loads(archive.read(_STAMP))
    assert stamp["commit"] == head
    assert isinstance(stamp["dirty"], bool)
    assert not (REPO_ROOT / "packages" / "weft-rag" / "src" / _STAMP).exists()
