"""`oracle-anchor-promote` — `anchor-promote` with the anchors a person wrote, ledger **40.7**.

Phase 40 reads the rule extractor's arm (`weft_retrieve.anchor_promote.AnchorPromote`) beside
this one, question by question, so a null result from extraction — `find_anchors`'s shape-only
rule finding nothing — can be told apart from a null result from promotion itself. This stage
calls the same public `promote` function `anchor-promote` calls, over anchors `40.5` had a person
write rather than a rule infer, and never a copy of that function: the two arms differ only in
where their anchors came from.

**Why this is its own unpublished distribution rather than a module in `weft-rag`.** G19 closed
the published name space at two — `weft-kernel` and `weft-rag` — and this control is neither: it
exists to be installed only where Phase 40 measures with it, and shipping it inside `weft-rag`
would register its `Reranker` into the default install, reachable from no shipped pipeline
document and so failing fitness function 16's ladder-reachability check the moment it landed. The
root `pyproject.toml`'s `[tool.uv.workspace] exclude` keeps it out of the dev `.venv` entirely, on
`testing/weft-canary`'s own precedent for a distribution whose whole point is to stay off a path
another check would otherwise walk.

It reaches Weft the same way any third-party pack does: one `weft.packs` entry point resolving to
`register`, `oracle-anchors = "weft_oracle_anchors:register"`, discovered and activated by the
identical seam a first-party pack goes through.

Its question comes from the pool-question ext entry `weft_eval.pool` replay attaches to each
`Ranking` — a bare `Query` carries no id, and TechQA asks some texts twice — and it refuses that
question by name, rather than guessing, the moment the entry is missing, its text hash disagrees
with the label's, or the label itself does not exist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_eval.pool import PoolQuestionEntry, text_sha256
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, Outcome, Produced
from weft_oracle_anchors.gold_first import GOLD_FIRST, OracleGoldFirst
from weft_retrieve.anchor_promote import promote
from weft_retrieve.contract import Reranker
from weft_retrieve.payload import Ranking

#: The name this reranker is registered and selectable under.
NAME = "oracle-anchor-promote"


class Settings(BaseModel):
    """This pack takes no pack-level settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class OracleLabelsError(WeftError):
    """Stops an oracle run on a bad labels file rather than scoring against partial truth.

    A `40.5` labels file could not be read as written — a duplicate question id or a
    malformed line, always naming the file and, for a malformed line, its line number.
    """


class OracleLabel(BaseModel):
    """The truth the oracle reorders by, tied to the exact text it was labelled on by digest.

    One person-written row from a `40.5` labels file: a question, the text it was asked
    against, and the anchors a person found in it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    text_sha256: str
    anchors: tuple[str, ...]


def load_oracle_labels(path: Path) -> dict[str, OracleLabel]:
    """Read `path` as JSONL, one `OracleLabel` per non-blank line, keyed by `question_id`.

    Raises `OracleLabelsError` naming `path` and the offending line number for a line that does
    not parse, and naming `path` and the question id for one that repeats — a labels file
    speaks for exactly one anchor set per question, and a silent overwrite would let the later
    of two disagreeing rows win with no record that the first ever existed.
    """
    labels: dict[str, OracleLabel] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            label = OracleLabel.model_validate_json(line)
        except (json.JSONDecodeError, ValueError) as exc:
            raise OracleLabelsError(
                f"{path}: line {line_number} is not a valid oracle label: {exc}"
            ) from exc
        if label.question_id in labels:
            raise OracleLabelsError(
                f"{path}: question id {label.question_id!r} is labelled more than once"
            )
        labels[label.question_id] = label
    return labels


class OracleAnchorPromoteConfig(BaseModel):
    """`OracleAnchorPromote`'s `with:` config — the one path to the `40.5` labels file it reads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    labels: Path


class OracleAnchorPromote:
    """`anchor-promote` over a person's own anchors rather than `find_anchors`'s inferred ones.

    Satisfies `weft_retrieve.contract.Reranker` structurally. `cost_bound = (0, 0)`: the labels
    file is read once at construction and every `run` is a dict lookup plus the same
    zero-cost `promote` comparison `anchor-promote` itself performs.
    """

    score_semantics: ClassVar[str] = (
        "3 x the number of the question's labelled anchors this passage holds, plus its "
        "incoming score — identical semantics to anchor-promote's, over anchors a person wrote "
        "rather than a rule inferred, and not comparable to a score from a different stage"
    )
    config_model: ClassVar[type[OracleAnchorPromoteConfig]] = OracleAnchorPromoteConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: OracleAnchorPromoteConfig) -> None:
        self._config = config
        self._labels = load_oracle_labels(config.labels)

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Promote `payload.hits` by the anchors this question's own label carries.

        Refuses by name — never guesses — the moment the ranking carries no pool entry, the
        entry names a question with no label, or either recorded text hash disagrees with the
        text actually being asked.
        """
        del ctx

        entry = payload.ext.get(PoolQuestionEntry.__namespace__)
        if not isinstance(entry, PoolQuestionEntry):
            return Failed(
                reason=(
                    "oracle-anchor-promote requires a pool question entry on the ranking "
                    "it is reranking — this stage only ever runs under a pool replay"
                )
            )

        label = self._labels.get(entry.question_id)
        if label is None:
            return Failed(reason=f"no oracle label for question id {entry.question_id!r}")

        origin_sha256 = text_sha256(payload.origin.text)
        if label.text_sha256 != entry.text_sha256 or origin_sha256 != label.text_sha256:
            return Failed(
                reason=(
                    f"question id {entry.question_id!r}: text hash disagrees between the pool "
                    f"entry, the oracle label and the text actually asked"
                )
            )

        promoted, held = promote(payload.hits, label.anchors)
        if held == 0:
            return Produced(value=payload)
        return Produced(value=payload.model_copy(update={"hits": promoted}))


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `oracle-anchor-promote` and `oracle-gold-first` for `Reranker`.

    The entry point `weft.packs` resolves to — `oracle-anchor-promote` and, for Phase 41's
    instrument check, `oracle-gold-first`.
    """
    del settings
    registrar.add(Reranker, NAME, OracleAnchorPromote)
    registrar.add(Reranker, GOLD_FIRST, OracleGoldFirst)


__all__ = [
    "NAME",
    "OracleAnchorPromote",
    "OracleAnchorPromoteConfig",
    "OracleLabel",
    "OracleLabelsError",
    "Settings",
    "load_oracle_labels",
    "register",
]
