"""`docs/08-manuals.md` §3, clause (a) — the quickstart executes.

"Its fenced shell blocks are extracted and run against a fresh throwaway
project in CI, and the run must exit `0` and produce a structure the prose
asserts — never a text match on generated prose, so a model swap cannot
break the check." This is that harness, run against `manual/quickstart.md`.

**Against the real container**, skipped with a clear reason when it is
absent — the same discipline `tests/integration/test_cli_end_to_end.py`
already uses, repeated here rather than shared so this reads as one
self-contained scenario, exactly as that module's own docstring argues for
itself.

**Each fenced block runs as its own subprocess**, sharing one throwaway
directory (`tmp_path`) as its working directory across every block, exactly
as a stranger typing them into one terminal would experience files landing
in the same place. `WEFT_DATABASE_URL` is supplied directly in every
subprocess's environment rather than relied on to survive from the `export`
block to the next one — `export` in one subprocess cannot reach a sibling
subprocess, only a shared shell session could, and chaining every block into
one script would make one failing block hide every block after it instead of
naming which one broke.
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
QUICKSTART: Final[Path] = REPO_ROOT / "manual" / "quickstart.md"

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

#: `08` §3's ratchet for clause (a): "a fenced block skipped from the CI run... must be named
#: here explicitly." One entry, and it is a documented, visible choice rather than a silent
#: omission: `weft-cli` is not published to any index yet — Phase 0 predates the release Phase 6
#: ships — so the one line demonstrating that future state cannot run against a real package
#: index without a network call this gate refuses to make. Every other block in the page is real
#: and executed below.
BLOCKS_WAIVED_FROM_EXECUTION: Final[frozenset[str]] = frozenset({"install"})

_FENCE = re.compile(
    r"^```bash(?:\s+id=(?P<id>\S+))?\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL
)


def _bash_blocks(markdown: str) -> list[tuple[str, str]]:
    """Every fenced ```bash block in `markdown`, as `(id, body)` pairs, in document order."""
    return [
        (match.group("id") or f"block-{index}", match.group("body"))
        for index, match in enumerate(_FENCE.finditer(markdown), start=1)
    ]


async def _database_reachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await conn.close()
    return None


@pytest.fixture
async def clean_database() -> AsyncIterator[None]:
    """Truncate `weft_nodes`/`weft_sources` first, so the quickstart's own claims about what it
    stores are checked against a database only this run touched — same fixture shape as
    `tests/integration/test_cli_end_to_end.py`'s `clean_database`, repeated rather than shared
    for the reason that module states: this should read as one self-contained scenario.
    """
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    schema_forcer = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await schema_forcer.count()  # forces schema creation through the public API
    await schema_forcer.aclose()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield


def test_at_least_one_fenced_block_is_extracted() -> None:
    # Floor — `08` §3: "at least one fenced shell block is extracted before any is run. A
    # quickstart with nothing to execute cannot pass by having nothing to fail."
    blocks = _bash_blocks(QUICKSTART.read_text(encoding="utf-8"))
    assert blocks, "manual/quickstart.md has no fenced ```bash blocks to check"


async def test_quickstart_executes_against_a_throwaway_project(
    clean_database: None, tmp_path: Path
) -> None:
    # Arrange
    del clean_database
    blocks = _bash_blocks(QUICKSTART.read_text(encoding="utf-8"))
    executed = [
        (block_id, body)
        for block_id, body in blocks
        if block_id not in BLOCKS_WAIVED_FROM_EXECUTION
    ]
    assert executed, "every fenced block was waived — nothing was actually checked"
    env = {**os.environ, "WEFT_DATABASE_URL": _DSN}

    # Act
    outputs: dict[str, str] = {}
    for block_id, body in executed:
        result = subprocess.run(  # noqa: S602 — a heredoc needs a shell; body is this repo's own doc
            body,
            shell=True,
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, (
            f"manual/quickstart.md block {block_id!r} exited {result.returncode}:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        outputs[block_id] = result.stdout

    # Assert — structure, never a text match on generated prose (`08` §3): Phase 0's `ask` output
    # is deterministic retrieval rather than model prose, but these still key on shape, not on
    # the exact words this fixture's corpus happens to contain.
    assert re.search(
        r"^produced \d+, nothing to produce \d+, failed 0\. nodes now stored: \d+\.$",
        outputs["index"],
        re.MULTILINE,
    ), f"weft index did not print the structure the quickstart asserts:\n{outputs['index']}"

    ask_output = outputs["ask"]
    assert re.search(r"^1\. \S", ask_output, re.MULTILINE), (
        f"weft ask did not return a ranked result:\n{ask_output}"
    )
    assert "no matching passages found" not in ask_output
    # `docs/03-cli.md` -> Output, *Score display*: human output never prints the raw score.
    assert "score=" not in ask_output

    # The fact is "weft-store is reported active", never the literal line
    # (`docs/lessons.md` L5.13). Task 6.4 put the installed version between the name and the
    # status — `weft-store 2.0.0: active` — and a pattern anchored on the old spelling
    # asserted the formatting rather than the state it exists to check.
    assert re.search(r"^weft-store\b[^:]*: active", outputs["doctor"], re.MULTILINE), (
        f"weft plugins doctor did not report weft-store active:\n{outputs['doctor']}"
    )
