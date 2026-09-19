"""Phase 40's power, frozen before any reordering arm runs — ledger 40.6.

Reads `scripts/pool_ceilings.py`'s output and a slice membership, and gives each slice its sd
bounds, the effect each could detect at two-sided 5% and 80% power, and the questions it would
need to detect `eval/pool-promotion/protocol.toml`'s worthwhile effect. Nothing here reads an arm's
outcome.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable, Mapping, Sequence, Set
from pathlib import Path
from typing import Any, Final

from pool_ceilings import QuestionCeiling
from pydantic import BaseModel, ConfigDict

from weft_eval.question_set import read_question_set

#: `protocol.toml` → `[effect]`: two-sided 5%, 80% power, as `n ≈ (2.8·sd/effect)²`.
_Z: Final[float] = 2.8
WORTHWHILE: Final[float] = 0.05


class SlicePower(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int
    sd_against_dense: float
    sd_between_reorderers: float
    mde_against_dense: float
    mde_between_reorderers: float
    n_required: int
    underpowered: bool


def power_for(
    ceilings: Sequence[QuestionCeiling], slices: Mapping[str, Set[str]]
) -> dict[str, SlicePower]:
    """Each named slice's power, over the questions `slices` assigns it."""
    by_id = {ceiling.question_id: ceiling for ceiling in ceilings}
    power: dict[str, SlicePower] = {}
    for name, members in slices.items():
        missing = sorted(members - by_id.keys())
        if missing:
            raise ValueError(f"slice '{name}' names questions with no ceiling: {missing}")
        held = [by_id[identifier] for identifier in sorted(members)]
        if not held:
            continue
        n = len(held)
        against_dense = math.sqrt(sum(max(c.rr5, c.oracle_gain) ** 2 for c in held) / n)
        between = math.sqrt(sum(1.0 for c in held if c.any_relevant_in_pool) / n)
        required = math.ceil((_Z * against_dense / WORTHWHILE) ** 2)
        power[name] = SlicePower(
            n=n,
            sd_against_dense=against_dense,
            sd_between_reorderers=between,
            mde_against_dense=_Z * against_dense / math.sqrt(n),
            mde_between_reorderers=_Z * between / math.sqrt(n),
            n_required=required,
            underpowered=n < required,
        )
    return power


def slices_from(
    ceilings: Sequence[QuestionCeiling],
    axes: Mapping[str, Mapping[str, str]],
    *,
    labelled: Set[str],
    identifier_exact: Set[str],
) -> dict[str, set[str]]:
    """Which questions each slice holds: every question, every axis value, whether the rule fires,
    the oracle's labelled population, and the identifier-exact questions."""
    ids = {ceiling.question_id for ceiling in ceilings}
    slices: dict[str, set[str]] = {"all": set(ids)}
    for ceiling in ceilings:
        key = f"rule-fires={'true' if ceiling.rule_fires else 'false'}"
        slices.setdefault(key, set()).add(ceiling.question_id)
        for axis, value in axes.get(ceiling.question_id, {}).items():
            slices.setdefault(f"{axis}={value}", set()).add(ceiling.question_id)
    slices["oracle-labelled"] = set(labelled) & ids
    slices["identifier-exact=yes"] = set(identifier_exact) & ids
    return slices


def main(argv: Sequence[str] | None = None) -> int:
    """Write one corpus's power table: `--ceilings` (40.4's file), `--questions`, `--labels` (40.5's
    oracle anchors; a question with a non-empty set is in the oracle's population),
    `--identifier-exact` (40.5's identifier-exact labels), `--out`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ceilings", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--identifier-exact", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    body = json.loads(args.ceilings.read_text(encoding="utf-8"))
    ceilings = [QuestionCeiling.model_validate(row) for row in body["questions"]]
    axes = {
        question.id: dict(question.axes) for question in read_question_set(args.questions).questions
    }
    labelled = {row["question_id"] for row in _jsonl(args.labels) if row["anchors"]}
    exact = {
        str(row["id"]).split(":", 1)[1]
        for row in _jsonl(args.identifier_exact)
        if row["identifier_decides"] == "yes"
    }
    slices = slices_from(ceilings, axes, labelled=labelled, identifier_exact=exact)
    power = power_for(ceilings, slices)
    by_id = {ceiling.question_id: ceiling for ceiling in ceilings}
    out = {
        "ceilings": args.ceilings.name,
        "worthwhile": WORTHWHILE,
        "slices": {
            name: {
                **slice_.model_dump(),
                "oracle_ceiling": _mean(by_id[i].oracle_gain for i in slices[name]),
                "promotion_ceiling": _mean(by_id[i].promotion_gain for i in slices[name]),
            }
            for name, slice_ in sorted(power.items())
        },
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, slice_ in sorted(power.items()):
        print(
            f"{name}: n={slice_.n} mde_vs_dense={slice_.mde_against_dense:.4f} "
            f"n_required={slice_.n_required} underpowered={slice_.underpowered}",
            flush=True,
        )
    return 0


def _mean(values: Iterable[float]) -> float:
    held = list(values)
    return sum(held) / len(held)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


if __name__ == "__main__":
    raise SystemExit(main())
