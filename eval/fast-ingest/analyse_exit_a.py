"""Reduce one Exit A run to the five clauses 43.5 names.

Usage: analyse_exit_a.py RUN_DIR [RUN_DIR ...]
"""

import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
FIRST_SOURCE = (HERE / "source_first.txt").read_text().strip()
LAST_SOURCE = (HERE / "source_last.txt").read_text().strip()
BATCH = re.compile(r"batch (\d+)/(\d+) · (\d+)/(\d+) documents queryable · ([\d.]+) s since start")


def _batches(run: Path) -> list[dict[str, float]]:
    lines = [BATCH.search(line) for line in (run / "index.err").read_text().splitlines()]
    return [
        {"k": int(m[1]), "of": int(m[2]), "queryable": int(m[3]), "at": float(m[5])}
        for m in lines
        if m
    ]


def _asks(run: Path) -> list[dict[str, Any]]:
    asks = [json.loads(line) for line in (run / "asks.jsonl").read_text().splitlines() if line]
    # The loop runs first, last, sleep 5, first, ...: an ask ends where the next one starts, less
    # the sleep after a `last`. The final ask has no successor and is left out of the latencies.
    for a, following in zip(asks, asks[1:], strict=False):
        a["end"] = following["t"] - (5.0 if a["q"] == "last" else 0.0)
    return asks


def _first_cited(asks: list[dict[str, Any]], start: float, which: str, source: str) -> float | None:
    for a in asks:
        if a["q"] == which and source in a["out"] and "[" in a["out"] and "end" in a:
            return round(a["end"] - start, 1)
    return None


def _answered_not_yet(asks: list[dict[str, Any]], which: str) -> bool:
    return any(a["q"] == which and "not yet indexed" in a["out"] for a in asks)


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def clocks(run: Path) -> dict[str, object]:
    """Measure one run directory's clocks and ask latencies.

    Args:
        run: The directory one Exit A run wrote its logs into.

    Returns:
        One JSON-ready row keyed by the clause each value answers.
    """
    start = float((run / "start.txt").read_text().strip())
    batches = _batches(run)
    asks = _asks(run)

    ingest_end = start + (batches[-1]["at"] if batches else 0)
    during = sorted(
        a["end"] - a["t"]
        for a in asks
        if a["q"] == "first" and "end" in a and a["end"] <= ingest_end
    )
    after = [float(x) for x in (run / "after_latencies.txt").read_text().split()]
    first_batch = batches[0]["at"] if batches else None
    last_batch = batches[-1]["at"] if batches else None
    after_p95 = round(sorted(after)[int(len(after) * 0.95) - 1], 2) if after else None
    during_p95 = round(during[max(0, int(len(during) * 0.95) - 1)], 2) if during else None
    return {
        "run": run.name,
        "1_first_active_s": first_batch,
        "2_first_cited_answer_s": _first_cited(asks, start, "first", FIRST_SOURCE),
        "3_coverage_per_batch": [(b["at"], b["queryable"]) for b in batches],
        "4_all_base_ready_s": last_batch,
        "5_ask_p50_after_s": _median(after),
        "5_ask_p95_after_s": after_p95,
        "5_ask_p50_during_s": _median(during),
        "5_ask_p95_during_s": during_p95,
        "asks_during": len(during),
        "last_batch_question_said_not_yet_indexed": _answered_not_yet(asks, "last"),
        "last_question_cited_at_s": _first_cited(asks, start, "last", LAST_SOURCE),
        "index_exit": (run / "index_exit.txt").read_text().strip(),
        "rows_after": (run / "rows_after.txt").read_text().split(),
    }


for arg in sys.argv[1:]:
    print(json.dumps(clocks(Path(arg))))
