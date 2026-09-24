"""Phase 40's verdict, per corpus, arm and slice — ledger 40.8.

Pairs each replayed arm against the identity replay of the same frozen pool, question by question,
over every slice `scripts/pool_power.py` froze, and reads each interval by
`eval/pool-promotion/protocol.toml`'s five outcomes, the rule and oracle arms jointly.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pool_ceilings import QuestionCeiling
from pool_power import WORTHWHILE, slices_from

from weft_eval.falsify import paired_differences
from weft_eval.question_set import read_question_set
from weft_eval.run_record import RunRecord, load_run_record

_METRICS = ("mrr@5", "recall@1", "ndcg@10")


def verdict(low: float, high: float, mean: float, *, underpowered: bool) -> str:
    """`protocol.toml`'s `[[verdict]]` table, first match wins."""
    if high < 0:
        return "harm"
    if high < WORTHWHILE:
        return "benefit ruled out"
    if low > 0 and mean >= WORTHWHILE:
        return "worthwhile"
    if low > 0:
        return "positive, below worthwhile"
    return "inconclusive (underpowered)" if underpowered else "inconclusive"


def joint_reading(rule: str, oracle: str) -> str:
    """`protocol.toml`'s `[joint_reading]`: a rule null beside an oracle gain condemns the
    extractor; only the oracle can rule promotion out.
    """
    if oracle in ("harm", "benefit ruled out"):
        return "promotion ruled out on this slice"
    if rule == "worthwhile":
        return "promotion helps with the rule's own anchors"
    if oracle in ("worthwhile", "positive, below worthwhile"):
        return "the extractor fails where promotion would succeed"
    return "no joint conclusion"


def _read(record: RunRecord, other: RunRecord, keys: frozenset[str]) -> dict[str, Any]:
    paired = paired_differences(record, other, question_keys=keys)
    return {name: paired[name].model_dump() for name in _METRICS if name in paired}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("--dense", "--rule", "--oracle", "--ceilings", "--power", "--questions"):
        parser.add_argument(flag, type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--identifier-exact", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    dense, rule, oracle = (load_run_record(p) for p in (args.dense, args.rule, args.oracle))
    ceilings = [
        QuestionCeiling.model_validate(row)
        for row in json.loads(args.ceilings.read_text(encoding="utf-8"))["questions"]
    ]
    power = json.loads(args.power.read_text(encoding="utf-8"))["slices"]
    axes = {q.id: dict(q.axes) for q in read_question_set(args.questions).questions}
    labelled = {r["question_id"] for r in _jsonl(args.labels) if r["anchors"]}
    exact = {
        r["question_id"] for r in _jsonl(args.identifier_exact) if r["identifier_decides"] == "yes"
    }
    slices = slices_from(ceilings, axes, labelled=labelled, identifier_exact=exact)

    out: dict[str, Any] = {"worthwhile": WORTHWHILE, "slices": {}}
    for name in sorted(power):
        keys = frozenset(slices[name])
        underpowered = bool(power[name]["underpowered"])
        entry: dict[str, Any] = {"n": len(keys), "underpowered": underpowered}
        verdicts: dict[str, str] = {}
        for arm, record in (("anchor-promote", rule), ("oracle-anchor-promote", oracle)):
            paired = _read(dense, record, keys)
            entry[arm] = paired
            primary = paired.get("mrr@5")
            if primary is None or primary["low"] is None:
                verdicts[arm] = "unreadable: no paired questions"
                continue
            verdicts[arm] = verdict(
                primary["low"], primary["high"], primary["mean"], underpowered=underpowered
            )
        entry["verdicts"] = verdicts
        entry["joint"] = joint_reading(
            verdicts["anchor-promote"], verdicts["oracle-anchor-promote"]
        )
        out["slices"][name] = entry
        print(
            f"{name}: n={len(keys)} rule={verdicts['anchor-promote']} "
            f"oracle={verdicts['oracle-anchor-promote']} -> {entry['joint']}",
            flush=True,
        )
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line]


if __name__ == "__main__":
    raise SystemExit(main())
