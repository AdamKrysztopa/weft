"""`eval/pool-promotion/*-verdict.json` and `*-ce-verdict.json` regenerate byte-identical from the
records beside them — ledgers **40.8** and **41.3**, the first clause of each phase's exit.

The verdict is computed from committed replay records, the frozen power table and the committed
labels, all under `eval/pool-promotion/`; only the question file comes from the ignored `corpus/`,
so this skips, naming it, where that file is absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest
from pool_verdict import main
from rerank_verdict import main as rerank_main

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_POOL: Final[Path] = _ROOT / "eval" / "pool-promotion"


def _questions(corpus: str) -> Path:
    """The ignored `corpus/` question file both verdicts read, or a skip naming it."""
    questions = _ROOT / "corpus" / f"{corpus}-questions.toml"
    if not questions.exists():
        pytest.skip(f"corpus fixture missing: corpus/{corpus}-questions.toml (the ignored corpus/)")
    return questions


# ~28 s locally for TechQA; the bootstrap runs per slice and arm (L26.6: CI runs about 2x slower).
@pytest.mark.timeout(180)
@pytest.mark.parametrize("corpus", ["esci", "techqa"])
def test_each_verdict_table_regenerates_byte_identical_from_its_records(
    corpus: str, tmp_path: Path
) -> None:
    # Arrange
    committed = _POOL / f"{corpus}-verdict.json"
    sources = json.loads((_POOL / f"{corpus}-verdict-sources.json").read_text(encoding="utf-8"))
    questions = _questions(corpus)
    out = tmp_path / "verdict.json"

    # Act
    main(
        [
            *("--dense", str(_POOL / "runs" / f"{sources['dense']}.json")),
            *("--rule", str(_POOL / "runs" / f"{sources['anchor-promote']}.json")),
            *("--oracle", str(_POOL / "runs" / f"{sources['oracle-anchor-promote']}.json")),
            *("--ceilings", str(_POOL / f"{corpus}-ceilings.json")),
            *("--power", str(_POOL / f"{corpus}-power.json")),
            *("--questions", str(questions)),
            *("--labels", str(_POOL / f"{corpus}-oracle-anchors.jsonl")),
            *("--identifier-exact", str(_POOL / f"{corpus}-identifier-exact.jsonl")),
            *("--out", str(out)),
        ]
    )

    # Assert
    assert out.read_bytes() == committed.read_bytes()


def _run(run_id: str) -> str:
    return str(_POOL / "runs" / f"{run_id}.json")


# Ledger 41.3: Phase 41's cross-encoder verdicts, the first clause of its exit. The bootstrap runs
# per slice, arm and repetition: ~140 s here per corpus, so twice that on CI plus margin (L26.6).
@pytest.mark.timeout(600)
@pytest.mark.parametrize("corpus", ["esci", "techqa"])
def test_each_cross_encoder_verdict_regenerates_byte_identical(corpus: str, tmp_path: Path) -> None:
    # Arrange
    committed = _POOL / f"{corpus}-ce-verdict.json"
    sources: dict[str, str | list[str]] = json.loads(
        (_POOL / f"{corpus}-ce-verdict-sources.json").read_text(encoding="utf-8")
    )
    questions = _questions(corpus)
    arms = [
        f"--arm={arm}=" + ",".join(_run(run) for run in runs)
        for arm, runs in sorted(sources.items())
        if isinstance(runs, list)
    ]
    out = tmp_path / "verdict.json"

    # Act
    rerank_main(
        [
            *("--dense", _run(str(sources["dense"]))),
            *("--anchor-promote", _run(str(sources["anchor-promote"]))),
            *arms,
            *("--ceilings", str(_POOL / f"{corpus}-ceilings.json")),
            *("--power", str(_POOL / f"{corpus}-ce-power.json")),
            *("--questions", str(questions)),
            *("--labels", str(_POOL / f"{corpus}-oracle-anchors.jsonl")),
            *("--identifier-exact", str(_POOL / f"{corpus}-identifier-exact.jsonl")),
            *("--out", str(out)),
        ]
    )

    # Assert
    assert out.read_bytes() == committed.read_bytes()
