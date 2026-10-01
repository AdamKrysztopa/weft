"""Task 44.32 — the evidence page rung table is generated from claims; no claim reads never."""

from weft_eval.claims import Claim
from weft_eval.claims_check import ClaimCheck
from weft_eval.claims_render import HEADER, render_claims_table
from weft_eval.verdict import ClaimStatus, EffectVerdict


def _claim(
    claim_id: str,
    *,
    rung: str = "whole",
    basis: str = "records",
    status: str = "helps",
    language: str = "en",
    regime: bool = False,
) -> Claim:
    body: dict[str, object] = {
        "id": claim_id,
        "rung": rung,
        "baseline": "dense",
        "metric": "answer_correctness",
        "status": status,
        "basis": basis,
        "population": {"benchmark": "validation-en", "language": language, "question_sets": []},
    }
    if basis == "records":
        body["source"] = {"experiment": "eval/experiments/whole-corpus-en.toml", "invocation": "i"}
        body["margin"] = 0.05
    else:
        body["ledger"] = "Phase 39"
    if regime:
        body["regime"] = [{"feature": "corpus.fits_context", "op": "eq", "value": True}]
    return Claim.model_validate(body)


def _check(claim: Claim, *, mean: float | None = 0.075, derived: bool = True) -> ClaimCheck:
    return ClaimCheck(
        claim_id=claim.id,
        stated=claim.status,
        derived=claim.status if derived and mean is not None else None,
        verdict=EffectVerdict.WORTHWHILE if derived and mean is not None else None,
        mean=mean,
        low=None if mean is None else mean - 0.04,
        high=None if mean is None else mean + 0.04,
        n=210 if mean is not None else None,
        margin=0.05,
        reproducible=mean is not None,
        stale=None,
    )


def test_a_records_claim_renders_its_recomputed_numbers_and_its_source() -> None:
    # Arrange
    claim = _claim("c.one", regime=True)

    # Act
    table = render_claims_table([(claim, _check(claim))], shipped_rungs=["whole"])

    # Assert
    assert table.startswith(HEADER)
    assert (
        "| `whole` | **helps** against `dense` on `answer_correctness` (en, validation-en) when "
        "corpus.fits_context eq True: +0.075 (95% interval +0.035 to +0.115), n 210 "
        "| `eval/experiments/whole-corpus-en` |"
    ) in table


def test_a_shipped_rung_with_no_claim_is_never_and_a_claimed_one_is_not() -> None:
    # Arrange
    claim = _claim("c.one")

    # Act
    table = render_claims_table([(claim, _check(claim))], shipped_rungs=["whole", "b", "a"])

    # Assert
    assert table.splitlines()[-1] == "| `a`, `b` | never | none |"
    assert "`whole`, " not in table.splitlines()[-1]


def test_a_ledger_claim_says_it_cannot_be_reproduced_and_names_its_ledger_entry() -> None:
    # Arrange
    claim = _claim("h.one", rung="hybrid", basis="ledger", status="no-gain")

    # Act
    table = render_claims_table([(claim, _check(claim, mean=None))], shipped_rungs=["hybrid"])

    # Assert
    assert "not reproducible from committed records (Phase 39)" in table
    assert "| Phase 39 |" in table


def test_two_claims_of_one_rung_share_a_row_in_id_order() -> None:
    # Arrange
    pl = _claim("c.b-pl", language="pl", status="no-gain")
    en = _claim("c.a-en")

    # Act
    table = render_claims_table([(pl, _check(pl)), (en, _check(en))], shipped_rungs=["whole"])

    # Assert
    row = next(line for line in table.splitlines() if line.startswith("| `whole`"))
    assert row.index("(en, validation-en)") < row.index("(pl, validation-en)")
    assert row.count("`eval/experiments/whole-corpus-en`") == 1


def test_an_asserted_status_says_it_is_asserted() -> None:
    # Arrange
    claim = _claim("c.one", status="wrong-questions")

    # Act
    table = render_claims_table([(claim, _check(claim, derived=False))], shipped_rungs=["whole"])

    # Assert
    assert ClaimStatus.WRONG_QUESTIONS.value in table
    assert "asserted, not derivable from an interval" in table


def test_with_no_claims_every_shipped_rung_is_never() -> None:
    # Act
    table = render_claims_table([], shipped_rungs=["b", "a"])

    # Assert
    assert table == f"{HEADER}\n| `a`, `b` | never | none |"
