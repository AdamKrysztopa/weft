"""`manual/evidence.md` cites every committed result under `eval/` — ledger **41.5**.

The page tells a user what Weft measured and what it therefore recommends. It is only worth reading
if it cannot quietly fall behind the evidence, so the population is derived from the tree: every
directory holding a committed `.json` or `.md` result under `eval/` (a `runs/` folder counts as its
parent), each of which the page must cite as a backticked `eval/…` path. A cited directory covers
the directories beneath it, and a `*` in a citation matches one path segment's worth of text.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Final

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_PAGE: Final[Path] = _ROOT / "manual" / "evidence.md"
_CITATION: Final[re.Pattern[str]] = re.compile(r"`(eval/[^`\s]+)`")
#: Inputs and instruments, not results: question sets.
_NOT_RESULTS: Final[tuple[str, ...]] = ("eval/questions",)


def _tracked(pattern: str) -> list[str]:
    """The tracked paths matching `pattern` — `tests/architecture/conftest.py`'s own resolution of
    `git`, so a `PATH` without it fails by name rather than as a partial-path lint."""
    git = shutil.which("git")
    assert git is not None, "git is not on PATH, so nothing here can enumerate tracked files"
    return subprocess.run(  # noqa: S603 — literal argv, no shell; nothing interpolated
        [git, "ls-files", pattern], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()


def _result_directories() -> set[str]:
    listed = _tracked("eval")
    directories: set[str] = set()
    for path in listed:
        if not path.endswith((".json", ".md")) or path.startswith(_NOT_RESULTS):
            continue
        parent = PurePosixPath(path).parent
        if parent.name == "runs":
            parent = parent.parent
        directories.add(str(parent))
    return directories


def _cited_patterns(text: str) -> set[str]:
    patterns: set[str] = set()
    for citation in _CITATION.findall(text):
        path = citation.rstrip("/")
        if PurePosixPath(path).suffix in {".json", ".md", ".toml"}:
            path = str(PurePosixPath(path).parent)
        patterns.add(path)
    return patterns


def uncited(directories: set[str], text: str) -> list[str]:
    """The result directories no citation in `text` covers."""
    patterns = _cited_patterns(text)
    return sorted(
        directory
        for directory in directories
        if not any(
            fnmatch(directory, pattern) or directory.startswith(pattern + "/")
            for pattern in patterns
        )
    )


def test_every_committed_result_directory_is_cited_by_the_evidence_page() -> None:
    directories = _result_directories()

    missing = uncited(directories, _PAGE.read_text(encoding="utf-8"))

    assert directories, "found no committed result under eval/ — the walk itself broke"
    assert missing == [], f"manual/evidence.md cites no entry for: {missing}"


def test_the_check_can_actually_fail() -> None:
    directories = {"eval/experiments/planted-result", "eval/pool-promotion"}

    missing = uncited(directories, "see `eval/pool-promotion/esci-verdict.json`")

    assert missing == ["eval/experiments/planted-result"]


def test_the_readme_sends_a_reader_to_the_evidence_page() -> None:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")

    assert "manual/evidence.md" in readme


def _shipped_rungs() -> set[str]:
    return {PurePosixPath(path).stem for path in _tracked("packages/*/src/*/pipelines/*.yaml")}


def unlisted_rungs(rungs: set[str], text: str) -> list[str]:
    """The shipped rungs no backticked name or `*` pattern on the page covers."""
    names = set(re.findall(r"`([a-z0-9*][a-z0-9*-]*)`", text))
    return sorted(rung for rung in rungs if not any(fnmatch(rung, name) for name in names))


def test_every_shipped_rung_has_an_evidence_status_on_the_page() -> None:
    rungs = _shipped_rungs()

    missing = unlisted_rungs(rungs, _PAGE.read_text(encoding="utf-8"))

    assert rungs, "found no shipped pipeline document — the walk itself broke"
    assert missing == [], f"manual/evidence.md gives no evidence status for: {missing}"


def test_the_rung_check_can_actually_fail() -> None:
    assert unlisted_rungs({"planted-rung", "index-pdf-text"}, "`index-pdf*`") == ["planted-rung"]
