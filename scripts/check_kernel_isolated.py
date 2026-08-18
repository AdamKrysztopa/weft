"""Fitness function 1, primary half: install `weft-kernel` alone and import it.

The reference could not do this. `src/a_prior_project/` does not import standalone — it
resolves `adapters.*` only because `pyproject.toml` sets pytest
`pythonpath = ["system", ".", "scripts"]`, so its boundary was a test-runner
setting rather than a property of the package.

A kernel that is its own wheel is checked by installing it into a clean
environment and importing it. Anything reachable that should not be fails here,
with no AST walk and nothing to keep in sync.
"""

import subprocess
import sys
from pathlib import Path

KERNEL = Path(__file__).resolve().parents[1] / "packages" / "weft-kernel"


def main() -> int:
    command = [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        "--with",
        str(KERNEL),
        "python",
        "-c",
        "import weft_kernel; print('weft-kernel imports standalone')",
    ]

    # Fixed argv, no shell, nothing user-controlled.
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603

    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)

    if result.returncode != 0:
        sys.stderr.write(
            "\nweft-kernel does not import in a clean environment. Something it uses is not "
            "something it ships — see G1, The kernel boundary.\n"
        )

    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
