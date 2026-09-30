"""Task 44.22 — a `Route` carries its reasons, the claims they cite and a fallback."""

from weft_retrieve.payload import Query, Route, RouteView, RuleOutcome, Scorecard


def _card() -> Scorecard:
    return Scorecard(query=Query(text="q"), scores={})


def test_a_route_written_before_44_22_still_validates_with_nothing_recorded() -> None:
    # Arrange — the exact keys a 1.3.0 producer wrote.
    old = {
        "pipeline": "retrieve-then-generate",
        "outcome": "fell-through",
        "rule": "",
        "scorecard": _card().model_dump(),
    }

    # Act
    route = Route.model_validate(old)

    # Assert
    assert route.reasons == ()
    assert route.claims == ()
    assert route.fallback is None


def test_a_route_carries_reasons_claims_and_the_rung_it_would_fall_back_to() -> None:
    # Act
    route = Route(
        pipeline="whole-corpus-then-generate",
        outcome=RuleOutcome.MATCHED,
        rule="small-corpus",
        scorecard=_card(),
        reasons=("rule 'small-corpus' held: corpus.fits_context eq True",),
        claims=("whole-corpus.small-corpus.answer-correctness",),
        fallback="retrieve-then-generate",
    )

    # Assert
    assert route.reasons == ("rule 'small-corpus' held: corpus.fits_context eq True",)
    assert route.claims == ("whole-corpus.small-corpus.answer-correctness",)
    assert route.fallback == "retrieve-then-generate"


def test_the_view_of_a_route_keeps_the_decision_and_drops_the_scorecard() -> None:
    # Arrange
    route = Route(
        pipeline="whole-corpus-then-generate",
        outcome=RuleOutcome.MATCHED,
        rule="small-corpus",
        scorecard=_card(),
        reasons=("held",),
        claims=("c.one",),
        fallback="retrieve-then-generate",
    )

    # Act
    view = route.view()

    # Assert
    assert view == RouteView(
        pipeline="whole-corpus-then-generate",
        outcome=RuleOutcome.MATCHED,
        rule="small-corpus",
        reasons=("held",),
        claims=("c.one",),
        fallback="retrieve-then-generate",
    )
    assert "scorecard" not in view.model_dump()


def test_a_route_view_recorded_before_44_22_still_loads() -> None:
    # Act — an eval record's `question_routes` entry from 1.3.0.
    view = RouteView.model_validate({"pipeline": "p", "outcome": "matched", "rule": "always"})

    # Assert
    assert (view.reasons, view.claims, view.fallback) == ((), (), None)
