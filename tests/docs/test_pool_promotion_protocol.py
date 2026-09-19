"""`eval/pool-promotion/protocol.toml` says what was decided before any run — ledgers 40.0, 41.0.

A protocol is only worth writing first if it cannot be edited quietly afterwards to fit what came
back. This holds the choices that need no data to the values the owner settled in `fix-plans/18`,
so moving one is a visible diff in a test rather than a line nobody reads.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any, Final, cast

import pytest

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


def _phase_41() -> dict[str, Any]:
    return cast(dict[str, Any], _protocol()["phase_41"])


def test_phase_41_names_bge_as_the_adoption_model_and_minilm_as_exploratory_only() -> None:
    phase = _phase_41()

    assert phase["adoption_model"] == "BAAI/bge-reranker-v2-m3"
    assert phase["adoption_model"] not in phase["exploratory_models"]
    assert phase["label"] == "exploratory on reused benchmarks"


def test_only_contrasts_against_dense_carry_a_verdict() -> None:
    contrasts = cast(list[dict[str, Any]], _phase_41()["contrast"])

    readings = {tuple(contrast["arms"]): contrast["reading"] for contrast in contrasts}

    assert {arms for arms, reading in readings.items() if reading == "verdict"} == {
        ("cross-encoder-bge", "dense"),
        ("cross-encoder-minilm", "dense"),
    }
    assert readings[("cross-encoder-bge", "anchor-promote")] == "descriptive"


def test_the_power_bound_states_the_fraction_of_questions_it_assumes_move() -> None:
    power = cast(dict[str, Any], _phase_41()["power"])

    assert 0 < power["moved_fraction"] < 1


def test_each_model_arm_runs_twice_and_is_read_on_its_first_repetition() -> None:
    repeats = cast(dict[str, Any], _phase_41()["repeats"])

    assert (repeats["per_model_arm"], repeats["read_on"]) == (2, 1)


def test_41b_opens_on_bge_against_dense_on_esci_not_being_harm_or_benefit_ruled_out() -> None:
    rule = cast(str, _phase_41()["open_41b"]["when"])

    assert all(term in rule for term in ("cross-encoder-bge", "esci", "harm", "benefit ruled out"))


def test_the_llm_rerank_arm_is_esci_only_and_spent_last() -> None:
    spend = cast(dict[str, Any], _phase_41()["spend"])

    assert spend["llm_rerank_corpora"] == ["esci"]
    assert spend["cap_usd"] == 5.0
    assert spend["order"][0].startswith("41.3")


@pytest.mark.parametrize("corpus", ["esci", "techqa"])
def test_the_committed_cross_encoder_power_uses_the_protocols_moved_fraction(corpus: str) -> None:
    power = json.loads((_PROTOCOL.parent / f"{corpus}-ce-power.json").read_text(encoding="utf-8"))
    fraction = _phase_41()["power"]["moved_fraction"]

    slices = cast(dict[str, dict[str, Any]], power["slices"])

    assert {entry["moved_fraction"] for entry in slices.values()} == {fraction}
    assert all("breakeven_fraction" in entry for entry in slices.values())


def test_the_serving_dtype_is_fixed_before_any_score_and_matches_the_reference() -> None:
    serving = cast(dict[str, Any], _phase_41()["serving"])

    assert serving["dtype"] == "float32"
    assert serving["bge_max_input_length"] >= 784
