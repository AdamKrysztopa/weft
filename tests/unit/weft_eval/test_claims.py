"""Tasks 44.30 and 44.34 — a claim is a TOML document, and an unknown name in it is refused by name.

A claim states a rung's measured standing against a baseline, in the runtime-observable regime it
holds in. The regime is what a routing rule may test; the population is what was measured on and
is never routed on, so the two are separate tables and a population key in the regime is refused.
"""

from pathlib import Path

import pytest

from weft_eval.claims import (
    Claim,
    ClaimBasis,
    ClaimDocumentError,
    UnknownClaimFeatureError,
    load_claim,
    load_claims,
)
from weft_eval.verdict import ClaimStatus
from weft_kernel.errors import UnresolvedNameError

_RECORDS = """\
[claim]
schema = 1
id = "whole-corpus.small-corpus.answer-correctness"
rung = "whole-corpus-wide-then-generate"
baseline = "retrieve-then-generate"
metric = "answer_correctness"
status = "helps"
basis = "records"
margin = 0.05

[claim.regime]
when = [
  { feature = "corpus.fits_context", op = "eq", value = true },
  { feature = "corpus.leaf_tokens", op = "lte", value = 260000 },
]

[claim.population]
benchmark = "validation-en"
language = "en"
question_sets = ["eval/questions/fetch.toml"]

[claim.source]
experiment = "eval/experiments/whole-corpus-en.toml"
invocation = "77a0ab088ccd43688bc0403932c95e6b"

[claim.untested]
regimes = ["corpus.leaf_tokens > 260000"]
"""


def _write(
    directory: Path, text: str, name: str = "whole-corpus.small-corpus.answer-correctness"
) -> Path:
    path = directory / f"{name}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_records_claim_loads_with_its_regime_population_and_source(tmp_path: Path) -> None:
    # Act
    claim = load_claim(_write(tmp_path, _RECORDS))

    # Assert
    assert isinstance(claim, Claim)
    assert claim.id == "whole-corpus.small-corpus.answer-correctness"
    assert claim.status is ClaimStatus.HELPS
    assert claim.basis is ClaimBasis.RECORDS
    assert claim.margin == 0.05
    assert [condition.feature for condition in claim.regime] == [
        "corpus.fits_context",
        "corpus.leaf_tokens",
    ]
    assert claim.population.language == "en"
    assert claim.source is not None
    assert claim.source.invocation == "77a0ab088ccd43688bc0403932c95e6b"
    assert claim.untested == ("corpus.leaf_tokens > 260000",)


def test_an_unknown_status_is_refused_naming_the_valid_ones(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ClaimDocumentError) as raised:
        load_claim(_write(tmp_path, _RECORDS.replace('status = "helps"', 'status = "great"')))

    # Assert
    assert "status" in str(raised.value)
    assert "no-gain" in str(raised.value)


def test_an_unknown_regime_feature_is_refused_naming_the_valid_ones(tmp_path: Path) -> None:
    # Arrange
    text = _RECORDS.replace("corpus.leaf_tokens", "corpus.leaf_tokns")

    # Act / Assert
    with pytest.raises(UnknownClaimFeatureError) as raised:
        load_claim(_write(tmp_path, text))

    # Assert
    assert isinstance(raised.value, UnresolvedNameError)
    assert "corpus.leaf_tokns" in str(raised.value)
    assert "corpus.leaf_tokens" in raised.value.valid_options


def test_a_layer_readiness_feature_is_a_valid_regime_name(tmp_path: Path) -> None:
    # Arrange
    text = _RECORDS.replace("corpus.fits_context", "corpus.layer.enrich-with-raptor.ready")

    # Act
    claim = load_claim(_write(tmp_path, text))

    # Assert
    assert claim.regime[0].feature == "corpus.layer.enrich-with-raptor.ready"


def test_a_population_key_in_the_regime_is_refused(tmp_path: Path) -> None:
    # Arrange — `benchmark` is what was measured on, never something a router can observe.
    text = _RECORDS.replace("[claim.regime]\n", '[claim.regime]\nbenchmark = "validation-en"\n')

    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="benchmark"):
        load_claim(_write(tmp_path, text))


def test_an_unknown_key_is_refused_naming_it_and_the_valid_ones(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="confidence.*Valid keys"):
        load_claim(_write(tmp_path, _RECORDS.replace("margin = 0.05", "confidence = 0.95")))


def test_a_records_claim_without_a_source_is_refused(tmp_path: Path) -> None:
    # Arrange
    text = _RECORDS.split("[claim.source]")[0] + "[claim.untested]\nregimes = []\n"

    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="source"):
        load_claim(_write(tmp_path, text))


def test_a_ledger_claim_names_its_ledger_entry_and_carries_no_source(tmp_path: Path) -> None:
    # Arrange
    ledger = """\
[claim]
schema = 1
id = "hybrid.phase-39"
rung = "hybrid-then-generate"
baseline = "retrieve-then-generate"
metric = "answer_correctness"
status = "no-gain"
basis = "ledger"
ledger = "Phase 39"

[claim.population]
benchmark = "validation-en"
language = "en"
question_sets = []
"""

    # Act
    claim = load_claim(_write(tmp_path, ledger, name="hybrid.phase-39"))

    # Assert
    assert claim.basis is ClaimBasis.LEDGER
    assert claim.source is None
    assert claim.ledger == "Phase 39"
    with pytest.raises(ClaimDocumentError, match="ledger"):
        load_claim(
            _write(tmp_path, ledger.replace('ledger = "Phase 39"\n', ""), name="hybrid.phase-39")
        )


def test_a_file_whose_name_is_not_its_claim_id_is_refused(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="named"):
        load_claim(_write(tmp_path, _RECORDS, name="something-else"))


def test_a_missing_or_newer_schema_is_refused(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="schema"):
        load_claim(_write(tmp_path, _RECORDS.replace("schema = 1\n", "")))
    with pytest.raises(ClaimDocumentError, match="upgrade"):
        load_claim(_write(tmp_path, _RECORDS.replace("schema = 1", "schema = 9")))


def test_load_claims_reads_a_directory_in_id_order(tmp_path: Path) -> None:
    # Arrange
    _write(tmp_path, _RECORDS)
    other = _RECORDS.replace("whole-corpus.small-corpus.answer-correctness", "a.first")
    _write(tmp_path, other, name="a.first")

    # Act
    claims = load_claims(tmp_path)

    # Assert
    assert [claim.id for claim in claims] == [
        "a.first",
        "whole-corpus.small-corpus.answer-correctness",
    ]


def test_load_claims_of_a_directory_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="no claims directory"):
        load_claims(tmp_path / "missing")
