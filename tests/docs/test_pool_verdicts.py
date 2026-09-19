"""`eval/pool-promotion/*-verdict.json` regenerate byte-identical from the records beside them —
ledger **40.8**, and the first clause of Phase 40's exit.

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

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_POOL: Final[Path] = _ROOT / "eval" / "pool-promotion"


# ~28 s locally for TechQA; the bootstrap runs per slice and arm (L26.6: CI runs about 2x slower).
@pytest.mark.timeout(180)
@pytest.mark.parametrize("corpus", ["esci", "techqa"])
def test_each_verdict_table_regenerates_byte_identical_from_its_records(
    corpus: str, tmp_path: Path
) -> None:
    # Arrange
    committed = _POOL / f"{corpus}-verdict.json"
    sources = json.loads((_POOL / f"{corpus}-verdict-sources.json").read_text(encoding="utf-8"))
    questions = _ROOT / "corpus" / f"{corpus}-questions.toml"
    if not questions.exists():
        pytest.skip(f"corpus fixture missing: corpus/{corpus}-questions.toml (the ignored corpus/)")
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
