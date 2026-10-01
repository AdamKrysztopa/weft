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
    pin_claim,
)
from weft_eval.fingerprint import ClaimFingerprint
from weft_eval.verdict import ClaimStatus, EffectVerdict
from weft_kernel.errors import UnresolvedNameError

_RECORDS = """\
[claim]
schema = 2
id = "whole-corpus.small-corpus.answer-correctness"
rung = "whole-corpus-wide-then-generate"
baseline = "retrieve-then-generate"
metric = "answer_correctness"
status = "helps"
verdict = "worthwhile"
basis = "records"
margin = 0.05

[claim.regime]
when = [
  { feature = "corpus.base_complete", op = "eq", value = true },
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
        "corpus.base_complete",
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
    assert claim.regime[1].feature == "corpus.layer.enrich-with-raptor.ready"


_BASE_COMPLETE = '  { feature = "corpus.base_complete", op = "eq", value = true },\n'


@pytest.mark.parametrize(
    "feature", ["corpus.leaf_tokens", "corpus.fits_context.small", "corpus.layer.raptor.ready"]
)
def test_a_regime_about_the_corpus_must_say_the_base_is_complete(
    tmp_path: Path, feature: str
) -> None:
    # Arrange — measured on a complete corpus, so it must not apply to a still-indexing one.
    text = _RECORDS.replace(_BASE_COMPLETE, "")
    text = text.replace('{ feature = "corpus.fits_context", op = "eq", value = true },\n  ', "")
    text = text.replace("corpus.leaf_tokens", feature)

    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="corpus.base_complete"):
        load_claim(_write(tmp_path, text))


def test_a_regime_may_pin_the_base_incomplete_to_claim_a_partial_corpus(tmp_path: Path) -> None:
    # Arrange
    text = _RECORDS.replace(
        'feature = "corpus.base_complete", op = "eq", value = true',
        'feature = "corpus.base_complete", op = "eq", value = false',
    )

    # Act
    claim = load_claim(_write(tmp_path, text))

    # Assert
    assert claim.regime[0].value is False


def test_a_regime_with_only_query_features_needs_no_corpus_state(tmp_path: Path) -> None:
    # Arrange
    text = _RECORDS.replace(_BASE_COMPLETE, "")
    text = text.replace('  { feature = "corpus.fits_context", op = "eq", value = true },\n', "")
    text = text.replace(
        'feature = "corpus.leaf_tokens", op = "lte", value = 260000',
        'feature = "query.word_count", op = "lte", value = 12',
    )

    # Act
    claim = load_claim(_write(tmp_path, text))

    # Assert
    assert [condition.feature for condition in claim.regime] == ["query.word_count"]


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
schema = 2
id = "hybrid.phase-39"
rung = "hybrid-then-generate"
baseline = "retrieve-then-generate"
metric = "answer_correctness"
status = "no-gain"
verdict = "benefit-ruled-out"
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
        load_claim(_write(tmp_path, _RECORDS.replace("schema = 2\n", "")))
    with pytest.raises(ClaimDocumentError, match="upgrade"):
        load_claim(_write(tmp_path, _RECORDS.replace("schema = 2", "schema = 9")))


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


def test_a_claim_states_the_verdict_beneath_its_status(tmp_path: Path) -> None:
    # Act
    claim = load_claim(_write(tmp_path, _RECORDS))

    # Assert
    assert claim.status is ClaimStatus.HELPS
    assert claim.verdict is EffectVerdict.WORTHWHILE


def test_a_status_that_hides_which_verdict_it_stands_for_is_refused(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="verdict.*positive-below-margin.*worthwhile"):
        load_claim(_write(tmp_path, _RECORDS.replace('verdict = "worthwhile"\n', "")))


def test_a_verdict_that_reads_as_another_status_is_refused(tmp_path: Path) -> None:
    # Arrange — 'benefit-ruled-out' is a `no-gain`, never a `helps`.
    text = _RECORDS.replace('verdict = "worthwhile"', 'verdict = "benefit-ruled-out"')

    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="benefit-ruled-out.*no-gain.*helps"):
        load_claim(_write(tmp_path, text))


def test_a_status_no_interval_gives_carries_no_verdict(tmp_path: Path) -> None:
    # Arrange
    text = _RECORDS.replace('status = "helps"', 'status = "never"')

    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="verdict"):
        load_claim(_write(tmp_path, text))
    assert (
        load_claim(_write(tmp_path, text.replace('verdict = "worthwhile"\n', ""))).verdict is None
    )


def test_a_claim_written_before_verdicts_is_refused_naming_what_to_add(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="schema 1.*verdict"):
        load_claim(_write(tmp_path, _RECORDS.replace("schema = 2", "schema = 1")))


@pytest.mark.parametrize("verdict", list(EffectVerdict))
def test_only_a_worthwhile_verdict_on_records_is_adoptable_for_routing(
    tmp_path: Path, verdict: EffectVerdict
) -> None:
    # Arrange
    status = verdict.status.value
    text = _RECORDS.replace('status = "helps"', f'status = "{status}"')
    text = text.replace('verdict = "worthwhile"', f'verdict = "{verdict.value}"')

    # Act
    claim = load_claim(_write(tmp_path, text))

    # Assert
    assert claim.adoptable_for_routing is (verdict is EffectVerdict.WORTHWHILE)


def test_a_worthwhile_ledger_claim_is_not_adoptable_since_nothing_can_recompute_it(
    tmp_path: Path,
) -> None:
    # Arrange
    text = _RECORDS.split("[claim.source]")[0].replace(
        'basis = "records"', 'basis = "ledger"\nledger = "Phase 39"'
    )
    text += "[claim.untested]\nregimes = []\n"

    # Act
    claim = load_claim(_write(tmp_path, text))

    # Assert
    assert claim.verdict is EffectVerdict.WORTHWHILE
    assert claim.adoptable_for_routing is False


_PIN = """
[claim.fingerprint]
rung = "r"
baseline = "b"
index = "i"
baseline_index = "i"
judge = "j"
"""


def test_a_pinned_fingerprint_loads_with_the_claim(tmp_path: Path) -> None:
    # Act
    claim = load_claim(_write(tmp_path, _RECORDS + _PIN))

    # Assert
    assert claim.fingerprint is not None
    assert (claim.fingerprint.rung, claim.fingerprint.judge) == ("r", "j")
    assert claim.fingerprint.profiler is None
    assert load_claim(_write(tmp_path, _RECORDS)).fingerprint is None


def test_an_unknown_fingerprint_component_is_refused(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="fingerprint.*vibes"):
        load_claim(_write(tmp_path, _RECORDS + _PIN + 'vibes = "good"\n'))


def test_pinning_writes_a_table_that_loads_back_and_keeps_the_rest_of_the_file(
    tmp_path: Path,
) -> None:
    # Arrange
    path = _write(tmp_path, "# a comment a person wrote\n" + _RECORDS)
    fingerprint = ClaimFingerprint(
        rung="r", baseline="b", index="i", baseline_index="i", judge=None, profiler="1"
    )

    # Act
    pin_claim(path, fingerprint)

    # Assert
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# a comment a person wrote\n")
    assert text.count("[claim.fingerprint]") == 1
    assert 'regimes = ["corpus.leaf_tokens > 260000"]' in text
    assert load_claim(path).fingerprint == fingerprint


def test_pinning_again_replaces_the_pin_in_place(tmp_path: Path) -> None:
    # Arrange
    path = _write(tmp_path, _RECORDS + _PIN + "\n[claim.untested]\n")
    path.write_text(
        _RECORDS.replace("[claim.untested]", _PIN + "\n[claim.untested]"), encoding="utf-8"
    )
    newer = ClaimFingerprint(rung="r2", baseline="b", index="i", baseline_index="i")

    # Act
    pin_claim(path, newer)

    # Assert
    text = path.read_text(encoding="utf-8")
    assert text.count("[claim.fingerprint]") == 1
    assert load_claim(path).fingerprint == newer
    assert "[claim.untested]" in text
