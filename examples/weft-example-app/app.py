"""Weft, embedded — the whole of it, and not one line of it is a pack.

Every other directory under `examples/` registers a plugin and proves a capability can be
*added* from outside. This proves Weft can be *consumed* from outside: no entry point, no
`register()`, no `src/` tree, and the registry never hears of this file.

**There is no `asyncio.run` here, and that is the honest shape rather than a dodge.** The
realistic embedding is inside a program that already has a loop — a FastAPI route, a worker,
a notebook — which is `docs/03-cli.md`:9's own claim about what the CLI is. A standalone script
adds the bridge itself, in its own process, where it can see it:

    import asyncio
    from app import main

    asyncio.run(main())

`manual/user-manual.md` §7 shows that form executable. Fitness function 7(a) asserts there is
exactly one `asyncio.run` in this tree, at the CLI's entry point; the one a reader writes is
theirs and is not in this tree.

`WEFT_DATABASE_URL` names a Postgres with pgvector. Without one this exits `2` rather than `1`,
which is what `scripts/check_isolated_installs.py` reads to tell *the wheel does not work* from
*this machine has no database*.
"""

import os
import sys
import tempfile
from pathlib import Path

from weft_engine.api import Weft


async def main() -> None:
    if not os.environ.get("WEFT_DATABASE_URL"):
        sys.stderr.write(
            "WEFT_DATABASE_URL is unset — the wheel imported, an answer needs a store\n"
        )
        raise SystemExit(2)

    workspace = Path(tempfile.mkdtemp()).resolve()
    (workspace / "corpus").mkdir()
    (workspace / "corpus" / "note.txt").write_text("Weft is a microkernel RAG engine.")
    (workspace / "weft.toml").write_text('[llm.roles]\ngenerate = { provider = "scripted" }\n')

    async with Weft.open(workspace / "weft.toml") as weft:
        await weft.index(workspace / "corpus")
        answer = await weft.ask("what is Weft?", pipeline="retrieve-then-generate")
        print(f"{type(answer).__name__} with {len(answer.citations)} citation(s)")
        await weft.delete(workspace / "corpus" / "note.txt", yes=True)
