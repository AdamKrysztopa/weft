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
import socket
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

import psycopg
import pytest
from pydantic import SecretStr

from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
QUICKSTART: Final[Path] = REPO_ROOT / "manual" / "quickstart.md"

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

#: `08` §3's ratchet for clause (a): "a fenced block skipped from the CI run... must be named
#: here explicitly." One entry, and it is a documented, visible choice rather than a silent
#: omission: **installing resolves against a package index, and this gate makes no network
#: call.** Every other block in the page is real and executed below.
#:
#: *(Until 2026-09-12 this comment gave a different reason — that nothing was published yet.
#: That stopped being true at ledger task `26.2` on 2026-09-11, when `weft-kernel 0.1.0` and
#: `weft-rag 2.4.0` went to PyPI, and no test went red, because a ratchet counts a waiver's
#: entries and nothing reads its reason. `R17.14`, `docs/internal/lessons.md` `L17.10`.)*
#: *(A second entry from 2026-09-13, ledger `28.6`: `local-install` is `uv add
#: 'weft-rag[openai]'`, the extra the semantic section needs, and it resolves against an index for
#: exactly the reason above. It was written **because the binary refused** — the harness runs in a
#: workspace where `openai` is already installed and could never have seen it; a clean venv with
#: `weft-rag` alone exits `4` naming `hash` as the only registered Embedder.)*
BLOCKS_WAIVED_FROM_EXECUTION: Final[frozenset[str]] = frozenset({"install", "local-install"})

#: The environment variable that names a local OpenAI-compatible embeddings server — ledger task
#: **28.6**, **G21** position 1. Named `WEFT_LIVE_*` on `WEFT_LIVE_API_TESTS`'s own footing: it is
#: a statement about *this run*, not a configuration key Weft itself reads, and nothing in the
#: product would recognise it.
LOCAL_EMBEDDINGS_URL_VAR: Final[str] = "WEFT_LIVE_EMBEDDINGS_URL"

#: The quickstart's semantic section, in document order. Executed **only** when the variable above
#: names a server — and when it does, a server that does not answer is a **failure**, never a skip,
#: which is the discipline `ci-checks` already applies to `WEFT_DATABASE_URL`: an operator who set
#: the variable has claimed a server is there, and a run that then skips proves nothing while
#: reporting green (`docs/internal/lessons-archive.md` `L7.8`).
#:
#: Named rather than discovered, for `REQUIRED_BLOCKS`'s reason one file over: a section deleted
#: from the page would otherwise stop being checked by having stopped existing.
BLOCKS_NEEDING_A_LOCAL_EMBEDDINGS_SERVER: Final[frozenset[str]] = frozenset(
    {"local-config", "local-index", "local-ask"}
)

_FENCE = re.compile(
    r"^```bash(?:\s+id=(?P<id>\S+))?\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL
)


def _bash_blocks(markdown: str) -> list[tuple[str, str]]:
    """Every fenced ```bash block in `markdown`, as `(id, body)` pairs, in document order."""
    return [
        (match.group("id") or f"block-{index}", match.group("body"))
        for index, match in enumerate(_FENCE.finditer(markdown), start=1)
    ]


def _local_embeddings_server() -> str | None:
    """The server this run was told to use, or `None` if the operator named none."""
    named = os.environ.get(LOCAL_EMBEDDINGS_URL_VAR, "").strip()
    return named or None


def _server_answers(url: str) -> str | None:
    """`None` when the endpoint accepts a connection, else why it did not.

    A TCP connect rather than an HTTP request: what the blocks below need to know is whether
    something is listening where the operator said, and an HTTP probe would additionally assert a
    route and a status this file has no opinion about — the server's own answer to `weft index` is
    the real check, and it runs seconds later.
    """
    parsed = urlparse(url)
    if parsed.hostname is None:
        return f"{LOCAL_EMBEDDINGS_URL_VAR}={url!r} is not a URL with a host"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=2):
            return None
    except OSError as exc:
        return f"{LOCAL_EMBEDDINGS_URL_VAR}={url!r} named a server that did not answer: {exc}"


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
        await cur.execute("TRUNCATE weft_nodes, weft_sources, weft_node_productions")
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
    server = _local_embeddings_server()
    if server is not None:
        unreachable = _server_answers(server)
        if unreachable is not None:
            pytest.fail(unreachable)
    executed = [
        (block_id, body)
        for block_id, body in blocks
        if block_id not in BLOCKS_WAIVED_FROM_EXECUTION
        and (server is not None or block_id not in BLOCKS_NEEDING_A_LOCAL_EMBEDDINGS_SERVER)
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
        r"^\d+ documents: \d+ indexed, \d+ unchanged\. nodes now stored: \d+\.$",
        outputs["index"],
        re.MULTILINE,
    ), f"weft index did not print the structure the quickstart asserts:\n{outputs['index']}"

    ask_output = outputs["ask"]
    assert re.search(r"^1\. \S", ask_output, re.MULTILINE), (
        f"weft ask did not return a ranked result:\n{ask_output}"
    )
    assert "no matching passages found" not in ask_output

    # The lexical step's claim is not prose a model chose — it is that asking for a literal token
    # returns the passage carrying it, which is the whole difference between the text arm and the
    # `hash` ranking above it (`R21.5`, and `28.6`'s first half).
    assert "microkernel" in outputs["lexical"], (
        f"the lexical step did not return the passage containing the word it was asked "
        f"for:\n{outputs['lexical']}"
    )
    # `docs/03-cli.md` -> Output, *Score display*: human output never prints the raw score.
    assert "score=" not in ask_output

    # The fact is "the store is reported active", never the literal line (`docs/internal/lessons.md`
    # L5.13). Task 6.4 put the installed version between the name and the status —
    # `weft-store 2.0.0: active` — and a pattern anchored on the old spelling asserted the
    # formatting rather than the state it exists to check. The 2026-09-05 consolidation did it a
    # second time, one field further left: a row now leads with the **pack** and names its
    # distribution after it (`store (weft-rag) 2.1.0: active`), so a pattern anchored on
    # `weft-store` matched nothing. Anchored on the pack name, which is the identity this assertion
    # is actually about — everything between it and the colon is provenance this test has no opinion
    # on.
    assert re.search(r"^store\b[^:]*: active", outputs["doctor"], re.MULTILINE), (
        f"weft plugins doctor did not report the store pack active:\n{outputs['doctor']}"
    )


def test_the_page_still_carries_the_lexical_step() -> None:
    """`28.6`'s first half: the honest first-hour retrieval step needs no account at all.

    `R21.5` made a store's text arm reachable with no model call, and this is the block that
    puts it in front of a reader. Named here so deleting it from the page fails, rather than
    quietly leaving the quickstart's only demonstration of retrieval the one whose ranking is a
    hash's (`L17.4`'s shape: what a page stops saying is what nothing notices).
    """
    # Act
    present = {block_id for block_id, _ in _bash_blocks(QUICKSTART.read_text(encoding="utf-8"))}

    # Assert
    assert "lexical" in present, (
        "`manual/quickstart.md` has no `lexical` block. Until a reader configures a model, the "
        "text arm is the only retrieval on the page whose order means anything"
    )


def test_the_semantic_section_exists_and_runs_when_a_server_is_named() -> None:
    """`28.6`'s second half, and the half a green run can hide.

    The section is executed by the test above **only** when `WEFT_LIVE_EMBEDDINGS_URL` names a
    server, which on a laptop with none means those blocks never run. So this asserts they are
    still *there*: a deleted section and an absent server are indistinguishable to a harness that
    only skips, and G21 settled the account-free semantic path on this page existing.
    """
    # Act
    present = {block_id for block_id, _ in _bash_blocks(QUICKSTART.read_text(encoding="utf-8"))}

    # Assert
    missing = sorted(BLOCKS_NEEDING_A_LOCAL_EMBEDDINGS_SERVER - present)
    assert not missing, (
        f"`manual/quickstart.md` is missing {missing}. These are the blocks G21 position 1 owes a "
        f"first-hour reader — a local server they run, rather than a model Weft downloads"
    )
