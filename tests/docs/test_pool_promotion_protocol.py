"""`eval/pool-promotion/protocol.toml` says what Phase 40 decided before any run — ledger **40.0**.

A protocol is only worth writing first if it cannot be edited quietly afterwards to fit what came
back. This holds the choices that need no data to the values the owner settled in `fix-plans/18`,
so moving one is a visible diff in a test rather than a line nobody reads.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Final, cast

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_PROTOCOL: Final[Path] = _REPO_ROOT / "eval" / "pool-promotion" / "protocol.toml"


def _protocol() -> dict[str, Any]:
    return tomllib.loads(_PROTOCOL.read_text(encoding="utf-8"))


def test_the_pool_is_fifty_chunks_of_dense_retrieval_for_every_arm() -> None:
    pool = cast(dict[str, Any], _protocol()["pool"])

    assert (pool["retriever"], pool["depth"], pool["unit"]) == ("vector-top-k", 50, "chunks")


def test_esci_is_the_one_primary_corpus_and_techqa_confirms() -> None:
    corpora = cast(list[dict[str, Any]], _protocol()["corpus"])

    roles = {corpus["name"]: corpus["role"] for corpus in corpora}

    assert roles == {"esci": "primary", "techqa": "confirmatory"}


def test_every_result_is_labelled_exploratory_and_nothing_is_tuned_on_an_outcome() -> None:
    scope = cast(dict[str, Any], _protocol()["scope"])

    assert scope["label"] == "exploratory on reused benchmarks"
    assert set(scope["tuning_forbidden"]) >= {"entities", "matcher", "pool_depth"}


def test_the_verdict_is_five_outcomes_read_first_match_wins_in_the_settled_order() -> None:
    verdicts = cast(list[dict[str, Any]], _protocol()["verdict"])

    names = [verdict["name"] for verdict in verdicts]

    assert names == [
        "harm",
        "benefit ruled out",
        "worthwhile",
        "positive, below worthwhile",
        "inconclusive",
    ]
    assert verdicts[-1]["when"] == "otherwise"


def test_the_worthwhile_effect_and_the_phase_41_gate_are_the_settled_numbers() -> None:
    protocol = _protocol()

    assert protocol["effect"]["worthwhile"] == 0.05
    assert protocol["metrics"]["primary"] == "mrr@5"
    assert protocol["ceilings"]["open_phase_41_when"] == "esci oracle ceiling >= 0.05"


def test_the_rule_extractor_runs_with_no_configured_entities() -> None:
    anchors = cast(dict[str, Any], _protocol()["anchors"])

    assert (anchors["extractor"], anchors["entities"]) == ("find_anchors", [])
