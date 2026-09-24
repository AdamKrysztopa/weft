"""The crossed lexical/fusion sweep on Weft's own corpus — ledger task **21.9**.

`12-roadmap.md`'s standing rule is that a shipped default moves on a measurement over Weft's own
corpus and not on a plausible argument. Phase 21b made two things selectable that were not:
`[packs.store] text_mode` chooses between Postgres full-text search and real BM25 (`21.6`, `21.7`),
and `normalized-score-fusion` sits beside `reciprocal-rank-fusion` (`21.5`). **Neither default has
moved.** This is the measurement that would earn a change to either.

**It is crossed, and that is the whole design.** The review this phase is built from states the
reason in one sentence: *"otherwise an improved lexical ranker can be hidden by a fuser, or an
improved fuser credited for a changed candidate pool."* Four arms — `fts`/`bm25` × `rrf`/`nsf` —
so each factor is read at both levels of the other. Two arms would answer a different question and
look like this one.

**`L19.8` is why the fusion factor is here at all.** Task `21.2` swept the text arm's rank
normalisation and returned `precision@5` and `recall@5` *identical to the digit* across three arms,
because `reciprocal-rank-fusion` consumes each arm as a rank and discards its scale — the value was
read on the path under test and its effect did not survive to the metric. A BM25 arm measured under
RRF alone would reproduce that null exactly, and the null would look like a finding about BM25.

**Both lexical arms run on the same server, and that is not incidental.** `text_mode` is a
*provisioning-time* property — the BM25 index is built when the schema is — so the two arms cannot
share a database. They can share a *server*, and they must: the floor container is PostgreSQL 16
and the BM25 one is 17, so running `fts` on the floor and `bm25` on the other would vary the
Postgres version alongside the ranking and call the difference BM25's. Both databases are created
on the BM25 server, which can serve either mode.

**Within one lexical arm the index is built once** and the second fuser queries what the first one
wrote — `L11.46`: repetitions are repetitions only if the thing measured stayed still between them.
Across lexical arms it cannot be, for the provisioning reason above, so each arm indexes the same
corpus from the same manifest into its own database.

**It drives `weft_engine.api.Weft`, and starts no loop**, the way `sweep_text_normalization`
settled it at `21.2` and `examples/weft-example-app/app.py` at `24.3` — fitness function 7(a)
permits exactly one `asyncio.run` in this tree and it belongs to the CLI. `uv run poe
sweep-lexical-fusion` supplies the bridge.

Generation runs under the `scripted` provider: the metric being read is *retrieval*, generated text
is not scored, and a scripted provider makes the run free, offline and deterministic.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
from uuid import uuid4

import psycopg
from psycopg import sql

from weft_engine.api import Weft
from weft_eval import paired_differences

if TYPE_CHECKING:  # pragma: no cover - typing only
    from weft_eval.run_record import RunRecord


class Arm(NamedTuple):
    """One cell of the cross: a lexical mode and a fuser, named as an operator would write them."""

    text_mode: str
    fuser: str
    query_rung: str


#: The two fusers, by the pipeline document that selects each. `hybrid-then-generate` is the
#: shipped default and fuses by reciprocal rank; `hybrid-normalized-scores` derives from it and
#: replaces one stage, which is why the pair differs in the fuser and in nothing else.
FUSERS: tuple[tuple[str, str], ...] = (
    ("reciprocal-rank-fusion", "hybrid-then-generate"),
    ("normalized-score-fusion", "hybrid-normalized-scores"),
)

#: The two lexical modes. `fts` is what every corpus indexed before `21.6` was ranked with.
TEXT_MODES: tuple[str, ...] = ("fts", "bm25")

ARMS: tuple[Arm, ...] = tuple(
    Arm(text_mode=mode, fuser=fuser, query_rung=rung)
    for mode in TEXT_MODES
    for fuser, rung in FUSERS
)

#: The **ingest** rung. `eval run` resolves the corpus through it even under `reuse_index`, so it
#: must be a pipeline with an `Extractor` stage — `L8.29`'s shape, met head-on at `21.2`.
INGEST_RUNG = "index-pdf-text"

CORPUS = Path("corpus")
#: Corpus-relative labels, JSON, re-derivable — the property Phase 10's exit did not have.
QUESTIONS = Path("eval/raptor-baseline/questions.json")

#: Where both databases are created. **Not** `WEFT_DATABASE_URL`: that is the floor container,
#: PostgreSQL 16, which has no `pg_textsearch` and could serve only one of the two arms.
_BM25_SERVER_ENV = "WEFT_BM25_DATABASE_URL"


def _config_for(arm: Arm, dsn: str, workspace: Path) -> Path:
    """One arm's `weft.toml`.

    Two arms of a fuser pair differ in **no** field of this file — the fuser is chosen by
    `query_pipeline`, not by configuration, which is what keeps the two lexical arms' indexes shared
    between them.
    """
    path = workspace / f"weft-{arm.text_mode}-{arm.fuser}.toml"
    path.write_text(
        f'[packs.store]\ndsn = "{dsn}"\ntext_mode = "{arm.text_mode}"\n'
        f'\n[llm.roles]\ngenerate = {{ provider = "scripted" }}\n',
        encoding="utf-8",
    )
    return path


async def _database_for(mode: str, server: str) -> str:
    """A fresh database on the BM25 server, named for its mode so a reader of `\\l` can tell.

    Created rather than reused: a `text_mode` is decided when the schema is built, so an arm that
    inherited another's database would be measuring the other's index under its own name.
    """
    name = f"weft_sweep_{mode}_{uuid4().hex[:8]}"
    admin = await psycopg.AsyncConnection.connect(server, autocommit=True)
    try:
        async with admin.cursor() as cur:
            await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    finally:
        await admin.close()
    return f"{server.rsplit('/', 1)[0]}/{name}"


async def main() -> None:
    """Index once per lexical mode, query once per cell, and print every paired difference."""
    server = os.environ.get(_BM25_SERVER_ENV)
    if not server:
        message = (
            f"{_BM25_SERVER_ENV} is unset. This sweep needs a PostgreSQL 17/18 carrying "
            f"timescale/pg_textsearch, because one of its two lexical arms is real BM25 and the "
            f"other has to run on the same server or the comparison varies the Postgres version "
            f"too. `docker compose --profile bm25 up -d` starts one on port 5434."
        )
        raise RuntimeError(message)

    workspace = Path(tempfile.mkdtemp()).resolve()
    records: dict[Arm, RunRecord] = {}

    for mode in TEXT_MODES:
        dsn = await _database_for(mode, server)
        print(f"\n=== text_mode={mode} — {dsn.rsplit('/', 1)[-1]} ===")
        for position, arm in enumerate(a for a in ARMS if a.text_mode == mode):
            config = _config_for(arm, dsn, workspace)
            async with Weft.open(config) as weft:
                result = await weft.run(
                    "eval run",
                    {
                        "path": str(CORPUS),
                        "pipeline": INGEST_RUNG,
                        "query_pipeline": arm.query_rung,
                        "questions": str(QUESTIONS),
                        # Only the first fuser of a lexical arm builds the index; the second
                        # queries what it wrote, so the two are repetitions of one another.
                        "reuse_index": position > 0,
                    },
                    yes=True,
                )
            record = getattr(result, "record", None)
            if record is None:  # pragma: no cover - a result shape change, not a measurement
                message = f"'eval run' returned {type(result).__name__} with no record"
                raise RuntimeError(message)
            records[arm] = record
            print(f"  {arm.fuser}: run {getattr(result, 'run_id', '?')}")

    baseline = ARMS[0]
    print(f"\n### every arm against the shipped pair ({baseline.text_mode}, {baseline.fuser})")
    for arm in ARMS[1:]:
        print(f"\n--- {arm.text_mode} + {arm.fuser} ---")
        differences = paired_differences(records[baseline], records[arm])
        if not differences:
            print("  nothing paired — neither record carries per-question scores")
            continue
        for metric in sorted(differences):
            difference = differences[metric]
            print(
                f"  {metric}: mean {difference.mean:+.4f} "
                f"[{difference.low}, {difference.high}] over n={difference.n}"
            )
