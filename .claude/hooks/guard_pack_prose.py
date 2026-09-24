"""PostToolUse guard: a write that names the graph pack outside it hears so now, not at the gate.

`docs/internal/lessons.md` `L28.31` and `L28.39`. Fitness function 28(c) sweeps the kernel and every
other top-level package of the `weft-rag` wheel for the *text* of the graph pack's names, prose
included. An implementer naming `weft_kg.store.GraphStore` in a `weft_store` docstring, and another
following a brief that mandated a local `weft_kg` import, each found out a full architecture run
later. The writer reads the module in front of it, never the fitness function.

The names are read from `GRAPH_PACK_NAMES` in that fitness function's own file, so the two cannot
drift; if the literal cannot be read, the hook says so rather than going quiet.

Exit 2 feeds stderr back to the writer; the edit has already landed. Bare `python3` (3.9).
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_FF28 = Path("tests", "architecture", "test_ff28_graph_is_an_ordinary_pack.py")
_NAMES_LITERAL = re.compile(r"^GRAPH_PACK_NAMES\b[^=]*=\s*\((.*?)\)", re.MULTILINE | re.DOTALL)
_SWEPT = re.compile(r"^packages/(weft-kernel/|weft-rag/src/(?!weft_kg/)[^/]+/)")
_SUFFIXES = (".py", ".toml", ".md", ".yaml")


def _root_of(path):
    git = shutil.which("git")
    if git is None:
        return None
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [git, "-C", str(path.parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(done.stdout.strip()) if done.returncode == 0 else None


def _graph_pack_names(root):
    try:
        found = _NAMES_LITERAL.search((root / _FF28).read_text(encoding="utf-8"))
    except OSError:
        return None
    return tuple(re.findall(r"\"([^\"]+)\"", found.group(1))) if found else None


def main():
    """Warn the writer of a swept file that names the graph pack, before FF28(c) does.

    Returns:
        2 when the written file names the graph pack or its names cannot be read, with the
        lines on stderr; 0 otherwise.
    """
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    written = (payload.get("tool_input") or {}).get("file_path")
    if not isinstance(written, str) or not written.endswith(_SUFFIXES):
        return 0
    path = Path(payload.get("cwd") or ".") / written
    root = _root_of(path)
    if root is None:
        return 0
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return 0
    if not _SWEPT.match(relative):
        return 0
    names = _graph_pack_names(root)
    if not names:
        sys.stderr.write(
            "guard_pack_prose.py could not read GRAPH_PACK_NAMES from {}; fitness function\n"
            "28(c) still sweeps {} for the graph pack's names (L28.31).\n".format(_FF28, relative)
        )
        return 2
    try:
        lines = path.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError):
        return 0
    hits = [
        "  {}:{}: {!r}".format(relative, number, name)
        for number, line in enumerate(lines, 1)
        for name in names
        if name in line
    ]
    if not hits:
        return 0
    sys.stderr.write(
        "Fitness function 28(c) will fail on this file: nothing outside the graph pack may name\n"
        "it, and the sweep is text, so a docstring or comment counts (L28.31, L28.39):\n"
        + "\n".join(hits[:10])
        + '\nIn prose write "the graph pack"; in code, reach it through discovery.\n'
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
