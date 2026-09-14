"""Every `tests/integration` file passes when it is the only file in its process — repair `R22.10`.

The gate runs the integration files together, so a file can pass only because another one
registered something first. Three did, on `weft_store.rehydrate`'s process-wide `ExtModel`
registry, and the full gate stayed green on the order it happened to run in
(`docs/internal/lessons.md` `L22.16`). Each file runs here in a freshly spawned interpreter, one
after another: the files share one database and truncate its tables.
"""

import multiprocessing
import sys
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
INTEGRATION: Final[Path] = REPO_ROOT / "tests" / "integration"


def _run_alone(path: str) -> None:
    raise SystemExit(int(pytest.main([path, "-q", "-p", "no:cacheprovider"])))


def main() -> int:
    files = sorted(INTEGRATION.glob("test_*.py"))
    if not files:
        print(f"no integration test files under {INTEGRATION}", file=sys.stderr)
        return 1
    spawn = multiprocessing.get_context("spawn")
    failed: list[str] = []
    for path in files:
        process = spawn.Process(target=_run_alone, args=(str(path),))
        process.start()
        process.join()
        if process.exitcode != 0:
            failed.append(f"{path.relative_to(REPO_ROOT)} (exit {process.exitcode})")
    if failed:
        print(
            f"{len(failed)} of {len(files)} integration file(s) fail when each is the only file in "
            f"its process: {'; '.join(failed)}. A file that passes in the full run leans on "
            "something an earlier file set up — register what it reads in its own fixture.",
            file=sys.stderr,
        )
        return 1
    print(f"all {len(files)} integration files pass when each is the only file in its process")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
