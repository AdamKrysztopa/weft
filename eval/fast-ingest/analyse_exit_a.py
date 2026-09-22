"""One Exit A run → the five clauses 43.5 names. Usage: analyse_exit_a.py RUN_DIR [RUN_DIR ...]"""

import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
FIRST_SOURCE = (HERE / "source_first.txt").read_text().strip()
LAST_SOURCE = (HERE / "source_last.txt").read_text().strip()
BATCH = re.compile(r"batch (\d+)/(\d+) · (\d+)/(\d+) documents queryable · ([\d.]+) s since start")


def clocks(run: Path) -> dict[str, object]:
    start = float((run / "start.txt").read_text().strip())
    lines = [BATCH.search(line) for line in (run / "index.err").read_text().splitlines()]
    batches = [
        {"k": int(m[1]), "of": int(m[2]), "queryable": int(m[3]), "at": float(m[5])}
        for m in lines
        if m
    ]
    asks = [json.loads(line) for line in (run / "asks.jsonl").read_text().splitlines() if line]

    # The loop runs first, last, sleep 5, first, ...: an ask ends where the next one starts, less
    # the sleep after a `last`. The final ask has no successor and is left out of the latencies.
    for a, following in zip(asks, asks[1:], strict=False):
        a["end"] = following["t"] - (5.0 if a["q"] == "last" else 0.0)

    def first_cited(which: str, source: str) -> float | None:
        for a in asks:
            if a["q"] == which and source in a["out"] and "[" in a["out"] and "end" in a:
                return round(a["end"] - start, 1)
        return None

    def answered_not_yet(which: str) -> bool:
        return any(a["q"] == which and "not yet indexed" in a["out"] for a in asks)

    ingest_end = start + (batches[-1]["at"] if batches else 0)
    during = sorted(
        a["end"] - a["t"]
        for a in asks
        if a["q"] == "first" and "end" in a and a["end"] <= ingest_end
    )
    after = [float(x) for x in (run / "after_latencies.txt").read_text().split()]
    return {
        "run": run.name,
        "1_first_active_s": batches[0]["at"] if batches else None,
        "2_first_cited_answer_s": first_cited("first", FIRST_SOURCE),
        "3_coverage_per_batch": [(b["at"], b["queryable"]) for b in batches],
        "4_all_base_ready_s": batches[-1]["at"] if batches else None,
        "5_ask_p50_after_s": round(statistics.median(after), 2) if after else None,
        "5_ask_p95_after_s": round(sorted(after)[int(len(after) * 0.95) - 1], 2) if after else None,
        "5_ask_p50_during_s": round(statistics.median(during), 2) if during else None,
        "5_ask_p95_during_s": round(during[max(0, int(len(during) * 0.95) - 1)], 2)
        if during
        else None,
        "asks_during": len(during),
        "last_batch_question_said_not_yet_indexed": answered_not_yet("last"),
        "last_question_cited_at_s": first_cited("last", LAST_SOURCE),
        "index_exit": (run / "index_exit.txt").read_text().strip(),
        "rows_after": (run / "rows_after.txt").read_text().split(),
    }


for arg in sys.argv[1:]:
    print(json.dumps(clocks(Path(arg))))
