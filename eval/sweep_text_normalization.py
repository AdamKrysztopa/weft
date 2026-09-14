"""The text-ranking normalisation sweep on Weft's own corpus — ledger task **21.2**.

`12-roadmap.md`'s standing rule is that a shipped default moves on a measurement over Weft's own
corpus and not on a plausible argument. Ledger task `21.0` made `[packs.store]
text_rank_normalization` selectable and deliberately left the default where Postgres had always
had it — `0`, no length normalisation at all. This is the measurement that would earn a change.

**It drives `weft_engine.api.Weft`, and that is the point of the file as much as the numbers.**
`fix-plans/06` argued for taking Phase 24a before this one on exactly one claim: that 21a's sweeps
stop being a subprocess and a parsed stdout and become ordinary Python. The deleted
`eval/run_baseline.py` was what that claim was made against — it ran the binary and read its
output back, *for fitness function 7(a)'s reason*, because the tree may hold exactly one
`asyncio.run` and it is the CLI's; repair R22.4c's `weft_cli.eval_baseline` carries the identical
claim further, taking the published baseline itself in process. Here there is no subprocess:
`Weft.run("eval run", …)` reaches the same `Command` the terminal reaches, through the same
registry, and what comes back is a typed `EvalRunCommandResult` carrying its own `RunRecord`.
Nothing is parsed.

**So this module exposes `async def main()` and starts no loop.** The bridge is the caller's, the
way `examples/weft-example-app/app.py` settled it at task 24.3 — which keeps 7(a) true without
anybody waiving anything. `uv run poe sweep-normalization` supplies it.

**Two arms differing in one field.** `L10.5`/`L10.6` are the reason that is stated rather than
assumed: a comparison whose instrument cannot see the thing being varied produces a plausible
number rather than an obviously broken one. Here the varied field is a pack setting, so each arm
gets its own `weft.toml` and its own `Weft`, and the corpus underneath them does not move —
`L11.46`: repetitions are repetitions only if the thing measured stayed still between them, so the
index is built **once** and every later arm queries it with `reuse_index`.

**Why `hybrid-then-generate`.** It is the only shipped rung that reaches `search_text` at all —
`hybrid` is the one retriever that fans out to the store's text arm, which is the arm `21.0`'s
setting governs. Generation runs under the `scripted` provider: the metric being read is
*retrieval*, the generated text is not scored here, and a scripted provider makes the run free,
offline and deterministic. An arm whose generation differed would be measuring something else.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from weft_engine.api import Weft
from weft_eval import paired_differences

if TYPE_CHECKING:  # pragma: no cover - typing only
    from weft_eval.run_record import RunRecord

#: The arms. `0` is what every corpus indexed before `21.0` was ranked with — Postgres's own
#: default, *"ignores the document length"* — and `2` is *"divides the rank by the document
#: length"*, the one a reader expects a search engine to be doing. `1` is the gentler
#: `1 + log(length)` divisor, included because two points cannot tell a trend from a coin flip
#: (`L11.3`: probe a derivation where its answer changes, not at one point of a step function).
ARMS: tuple[int, ...] = (0, 2, 1)

#: The **query** rung. See the module docstring — `hybrid` is the only shipped retriever that
#: reaches the store's text arm, which is the arm the setting under test governs. This is the half
#: that makes the instrument able to see the thing being varied (`L10.5`, `L10.6`): with a
#: vector-only rung here the sweep would run, produce three plausible numbers, and have measured
#: nothing at all, because `text_rank_normalization` would never have been read.
QUERY_RUNG = "hybrid-then-generate"

#: The **ingest** rung, which is a different argument and a different question. `eval run` resolves
#: the corpus through it even under `reuse_index`, so it must be a pipeline with an `Extractor`
#: stage — `L8.29`'s shape, met head-on: naming the query rung here refuses with *"has no stage
#: registered under the Extractor contract"*.
INGEST_RUNG = "index-pdf-text"

CORPUS = Path("corpus")
#: The reproducible set  made derivable — corpus-relative labels, JSON, and
#: re-derivable by  rather than built by hand
#: in a scratch directory, which is the defect that made Phase 10s exit unreconstructable.
QUESTIONS = Path("eval/raptor-baseline/questions.json")


def _config_for(normalization: int, workspace: Path) -> Path:
    """One arm's `weft.toml`, differing from the others in exactly one field."""
    dsn = os.environ["WEFT_DATABASE_URL"]
    path = workspace / f"weft-{normalization}.toml"
    path.write_text(
        f'[packs.store]\ndsn = "{dsn}"\ntext_rank_normalization = {normalization}\n'
        f'\n[llm.roles]\ngenerate = {{ provider = "scripted" }}\n',
        encoding="utf-8",
    )
    return path


async def main() -> None:
    """Index once, query per arm, and print the paired differences between the arms."""
    workspace = Path(tempfile.mkdtemp()).resolve()
    records: dict[int, RunRecord] = {}

    for index, normalization in enumerate(ARMS):
        config = _config_for(normalization, workspace)
        async with Weft.open(config) as weft:
            result = await weft.run(
                "eval run",
                {
                    "path": str(CORPUS),
                    "pipeline": INGEST_RUNG,
                    "query_pipeline": QUERY_RUNG,
                    "questions": str(QUESTIONS),
                    # Only the first arm builds the index. Every later arm queries what the
                    # first one wrote, which is what makes these repetitions of one another
                    # rather than three measurements of three different corpora (`L11.46`).
                    "reuse_index": index > 0,
                },
                yes=True,
            )
        run_id = getattr(result, "run_id", "?")
        record = getattr(result, "record", None)
        if record is None:  # pragma: no cover - a result shape change, not a measurement
            message = f"'eval run' returned {type(result).__name__} with no record to compare"
            raise RuntimeError(message)
        records[normalization] = record
        print(f"arm normalization={normalization}: run {run_id}")

    baseline = records[ARMS[0]]
    for normalization in ARMS[1:]:
        print(f"\n--- normalization {normalization} against the shipped default {ARMS[0]} ---")
        differences = paired_differences(baseline, records[normalization])
        if not differences:
            print("  nothing paired — neither record carries per-question scores")
            continue
        for metric in sorted(differences):
            difference = differences[metric]
            print(
                f"  {metric}: mean {difference.mean:+.4f} "
                f"[{difference.low}, {difference.high}] over n={difference.n}"
            )
