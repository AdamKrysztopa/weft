"""A newcomer installs, indexes and asks from the README alone — ledger task **6.12**.

`docs/09-release.md` §5.2, *Security, licensing, documentation*: "A newcomer can install, index and
ask from the README alone, without opening `docs/`."

**Measured before it was fixed: they could not.** `README.md`'s *Start here* pointed at
`docs/README.md` as "the single source of truth", its layout table listed five design documents,
and every runnable block in it was a maintainer's command — `poe ci-checks`, `next_task.py`. There
was no install, no index and no query anywhere on the page. Somebody arriving at the repository saw
a plan, not a product, and the first thing the checklist promises them is the one thing the page
did not do.

**This is `08` §3 clause (a)'s harness aimed one page over.** `tests/docs/test_quickstart.py`
executes `manual/quickstart.md`, which is the right check for that document and says nothing about
this one: the quickstart is reached *from* the README, and a newcomer who has to be told where to
go has already opened something else. So the blocks are extracted from `README.md` itself, run in a
throwaway directory, and the answer is asserted on structure rather than on words a model chose.

**Both suppression markers below are this harness's, copied in intent from
`tests/docs/test_quickstart.py`**: `pytest.skip` is the container discipline
(`docs/06-phase-0-build.md` — skipped with a clear reason, never silently passed), and the
security-lint suppression is on the one `subprocess.run` that needs a shell, because the README's
own blocks use heredocs. The body being run is this repository's own documentation.

**What is waived, and why it is one entry rather than a policy.** `install` cannot run: nothing is
published to an index yet — ledger task **6.13** is what makes that possible — so the one line
demonstrating the future state would need a network call this gate refuses to make. Exactly the
waiver `test_quickstart.py` carries, for exactly the same reason, and it empties at the same task.

**The check that the README needs nothing from `docs/` is separate and mechanical**: the executed
blocks are asserted not to reference `docs/` at all. A runnable path that says "see
`docs/03-cli.md` for the flag you need" satisfies "the commands ran" and fails the actual promise.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final

import psycopg
import pytest
from pydantic import SecretStr

from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
README: Final[Path] = REPO_ROOT / "README.md"

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

#: `08` §3's ratchet, one entry, for the reason `test_quickstart.py`'s own carries one: nothing is
#: on an index until ledger task 6.13, so the install line demonstrates a state that does not
#: exist yet and cannot be executed without a network call this gate refuses.
BLOCKS_WAIVED_FROM_EXECUTION: Final[frozenset[str]] = frozenset({"install"})

#: The newcomer path's blocks, in the order a reader meets them. Named rather than discovered:
#: a page that stopped carrying one of these would otherwise pass by having fewer blocks to run,
#: which is the vacuous shape this file's own floor test refuses.
REQUIRED_BLOCKS: Final[tuple[str, ...]] = ("install", "env", "files", "index", "ask")

_FENCE: Final[re.Pattern[str]] = re.compile(
    r"^```bash(?:\s+id=(?P<id>\S+))?\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL
)


def _bash_blocks(markdown: str) -> list[tuple[str, str]]:
    return [
        (match.group("id") or f"block-{index}", match.group("body"))
        for index, match in enumerate(_FENCE.finditer(markdown), start=1)
    ]


def newcomer_blocks() -> list[tuple[str, str]]:
    """Every tagged block on the newcomer path, in document order."""
    tagged = dict(_bash_blocks(README.read_text(encoding="utf-8")))
    return [(name, tagged[name]) for name in REQUIRED_BLOCKS if name in tagged]


async def _database_reachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await conn.close()
    return None


@pytest.fixture
async def clean_database() -> AsyncIterator[None]:
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    schema_forcer = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await schema_forcer.count()
    await schema_forcer.aclose()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield


def test_the_readme_carries_the_whole_newcomer_path() -> None:
    """The floor, and the real subject: the page has the blocks at all.

    This is the assertion that was false. A page with no `index` block passes any harness that
    runs "every block it finds", because it finds none.
    """
    # Act
    present = {name for name, _ in _bash_blocks(README.read_text(encoding="utf-8"))}

    # Assert
    missing = [name for name in REQUIRED_BLOCKS if name not in present]
    assert not missing, (
        f"`README.md` has no {missing} block. `09` §5.2: a newcomer installs, indexes and asks "
        f"from the README alone — a page that sends them to `docs/` or to another document for "
        f"any of those steps has not done it."
    )


def test_the_newcomer_path_needs_nothing_from_docs() -> None:
    """ "Without opening `docs/`" is the half a passing harness says nothing about."""
    # Act
    reaching = [
        f"{name}: {line.strip()}"
        for name, body in newcomer_blocks()
        for line in body.splitlines()
        if "docs/" in line
    ]

    # Assert
    assert not reaching, (
        "the newcomer path reaches into `docs/`:\n  " + "\n  ".join(reaching) + "\n\n"
        "`09` §5.2's clause is 'from the README alone, **without opening `docs/`**'. A runnable "
        "path that tells the reader to go and look something up has answered a different "
        "question."
    )


async def test_the_readme_path_runs_and_answers(clean_database: None, tmp_path: Path) -> None:
    """Executed, in a throwaway directory, exactly as `08` §3 clause (a) executes the quickstart.

    Each block is its own subprocess sharing one working directory — what a stranger typing them
    into one terminal would experience — with `WEFT_DATABASE_URL` supplied directly rather than
    relied on to survive an `export` from a sibling subprocess.
    """
    # Arrange
    del clean_database
    executed = [
        (name, body) for name, body in newcomer_blocks() if name not in BLOCKS_WAIVED_FROM_EXECUTION
    ]
    assert executed, "every block was waived — nothing was actually checked"
    env = {**os.environ, "WEFT_DATABASE_URL": _DSN, "PATH": os.environ.get("PATH", "")}

    # Act
    outputs: dict[str, str] = {}
    for name, body in executed:
        result = subprocess.run(  # noqa: S602 - a heredoc needs a shell; body is this repo's own doc
            body,
            shell=True,
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, (
            f"README.md block {name!r} exited {result.returncode}:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        outputs[name] = result.stdout

    # Assert — structure, never the words a retriever happened to return (`08` §3).
    assert re.search(
        r"^produced \d+, nothing to produce \d+, failed 0\. nodes now stored: \d+\.$",
        outputs["index"],
        re.MULTILINE,
    ), f"`weft index` did not print the structure the README shows:\n{outputs['index']}"
    assert re.search(r"^1\. \S", outputs["ask"], re.MULTILINE), (
        f"`weft ask` returned no ranked result:\n{outputs['ask']}"
    )
    assert "no matching passages found" not in outputs["ask"]
