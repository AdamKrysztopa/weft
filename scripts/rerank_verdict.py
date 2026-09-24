"""Phase 41's verdict, per corpus, cross-encoder arm and slice — ledger 41.3.

Pairs each repetition of each cross-encoder arm against 40.8's dense replay of the same frozen pool,
question by question, over every slice `scripts/pool_power.py` froze, and reads the first
repetition by `eval/pool-promotion/protocol.toml`'s five outcomes; the second is read the same way
and a disagreement makes the slice *unstable*. Against 40.8's `anchor-promote` record the contrast
is descriptive: its interval is published beside the MDE its bound allows, and no verdict is read.
Every record must have replayed one manifest over one question set (`40.2`; `L28.4`).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pool_ceilings import QuestionCeiling
from pool_power import WORTHWHILE, slices_from
from pool_verdict import verdict
from pydantic import BaseModel, ConfigDict

from weft_eval.falsify import paired_differences
from weft_eval.question_set import read_question_set
from weft_eval.run_record import RunRecord, load_run_record
from weft_kernel.payload import Produced

_METRICS = ("mrr@5", "recall@1", "ndcg@10")


class PoolIdentity(BaseModel):
    """What two records must share to be paired: the manifest they replayed, the questions."""

    model_config = ConfigDict(frozen=True)

    pool_manifest: str | None
    question_set_digest: str | None


def require_one_pool(identities: Mapping[str, PoolIdentity]) -> None:
    """Refuse, naming the record, any record that did not replay the first one's pool."""
    (first_name, first), *rest = identities.items()
    if first.pool_manifest is None:
        raise ValueError(f"record '{first_name}' replayed no pool manifest")
    for name, identity in rest:
        if identity != first:
            raise ValueError(
                f"record '{name}' replayed {identity.pool_manifest} over questions "
                f"{identity.question_set_digest}, not '{first_name}''s {first.pool_manifest} "
                f"over {first.question_set_digest}; records of different pools do not pair"
            )


def stable(first: str, second: str) -> str:
    """`[phase_41.repeats]`: a slice is read on its first repetition unless the second disagrees."""
    return first if first == second else f"unstable: {first} / {second}"


def _identity(record: RunRecord) -> PoolIdentity:
    experiment = record.experiment
    return PoolIdentity(
        pool_manifest=experiment.pool_manifest if experiment is not None else None,
        question_set_digest=record.question_set_digest,
    )


def _paired(base: RunRecord, other: RunRecord, keys: frozenset[str]) -> dict[str, Any]:
    paired = paired_differences(base, other, question_keys=keys)
    return {name: paired[name].model_dump() for name in _METRICS if name in paired}


def _read(paired: Mapping[str, Any], *, underpowered: bool) -> str:
    primary = paired.get("mrr@5")
    if primary is None or primary["low"] is None:
        return "unreadable: no paired questions"
    return verdict(primary["low"], primary["high"], primary["mean"], underpowered=underpowered)


def _excluded(record: RunRecord) -> int:
    outcome = record.metrics["mrr@5"]
    if not isinstance(outcome, Produced):
        raise ValueError(f"record {record.experiment} aggregated no mrr@5: {outcome}")
    return outcome.value.excluded


def _arm(text: str) -> tuple[str, tuple[Path, ...]]:
    name, _, paths = text.partition("=")
    return name, tuple(Path(path) for path in paths.split(","))


def _power_and_slices(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, set[str]]]:
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
    return power, slices


def _arm_entry(
    dense: RunRecord,
    promote: RunRecord,
    records: tuple[RunRecord, ...],
    keys: frozenset[str],
    *,
    underpowered: bool,
) -> dict[str, Any]:
    against_dense = [_paired(dense, record, keys) for record in records]
    readings = [_read(paired, underpowered=underpowered) for paired in against_dense]
    return {
        "against dense": against_dense[0],
        "repetitions": [
            {"verdict": reading, "mrr@5": paired.get("mrr@5")}
            for reading, paired in zip(readings, against_dense, strict=True)
        ],
        "repetitions differ on": _paired(records[0], records[-1], keys)
        .get("mrr@5", {})
        .get("differing", 0),
        "against anchor-promote (descriptive)": _paired(promote, records[0], keys),
        "verdict": stable(readings[0], readings[-1]),
    }


def _slice_entry(
    frozen: Mapping[str, Any],
    keys: frozenset[str],
    dense: RunRecord,
    promote: RunRecord,
    arms: Mapping[str, tuple[RunRecord, ...]],
) -> dict[str, Any]:
    underpowered = bool(frozen["underpowered"])
    entry: dict[str, Any] = {
        "n": len(keys),
        "underpowered": underpowered,
        "mde_against_dense": frozen["mde_against_dense"],
        "mde_between_reorderers": frozen["mde_between_reorderers"],
        "breakeven_fraction": frozen["breakeven_fraction"],
        "anchor-promote against dense": _paired(dense, promote, keys),
    }
    for arm, records in arms.items():
        entry[arm] = _arm_entry(dense, promote, records, keys, underpowered=underpowered)
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    """Write one corpus's table.

    The flags are `--dense` and `--anchor-promote` (40.8's records), `--arm
    name=rep1.json,rep2.json` per cross-encoder, `--ceilings`, `--power` (41.0's
    `{corpus}-ce-power.json`), `--questions`, `--labels`, `--identifier-exact`, `--out`.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("--dense", "--anchor-promote", "--ceilings", "--power", "--questions"):
        parser.add_argument(flag, type=Path, required=True)
    parser.add_argument("--arm", type=_arm, action="append", required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--identifier-exact", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    dense = load_run_record(args.dense)
    promote = load_run_record(args.anchor_promote)
    arms = {name: tuple(load_run_record(p) for p in paths) for name, paths in args.arm}
    require_one_pool(
        {
            "dense": _identity(dense),
            "anchor-promote": _identity(promote),
            **{
                f"{name} r{index}": _identity(record)
                for name, records in arms.items()
                for index, record in enumerate(records, start=1)
            },
        }
    )

    power, slices = _power_and_slices(args)

    out: dict[str, Any] = {
        "worthwhile": WORTHWHILE,
        "excluded": {
            name: [_excluded(record) for record in records] for name, records in arms.items()
        },
        "slices": {},
    }
    for name in sorted(power):
        keys = frozenset(slices[name])
        entry = _slice_entry(power[name], keys, dense, promote, arms)
        out["slices"][name] = entry
        print(
            f"{name}: n={len(keys)} " + " ".join(f"{arm}={entry[arm]['verdict']}" for arm in arms),
            flush=True,
        )
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line]


if __name__ == "__main__":
    raise SystemExit(main())
