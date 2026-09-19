"""Phase 40's power, frozen before any reordering arm runs — ledger 40.6.

Reads `scripts/pool_ceilings.py`'s output and a slice membership, and gives each slice its sd
bounds, the effect each could detect at two-sided 5% and 80% power, and the questions it would
need to detect `eval/pool-promotion/protocol.toml`'s worthwhile effect. Nothing here reads an arm's
outcome.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence, Set
from typing import Final

from pool_ceilings import QuestionCeiling
from pydantic import BaseModel, ConfigDict

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
