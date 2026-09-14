"""`tests/conftest.py`'s skip guard: every skip names a known cause; a claimed service never skips.

It replaced a pinned total, `WEFT_TEST_EXPECTED_SKIPS`, which moved seven times in five days
because it summed causes that change independently — untracked documents, a Qdrant and a BM25
server CI deliberately does not run — and could be measured only in CI, after the push.
"""

from __future__ import annotations

import pytest

from tests.conftest import SkipCause, skip_cause, skip_problems

_DSN = "postgresql://weft:weft@localhost:5433/weft"


@pytest.mark.parametrize(
    ("reason", "cause"),
    [
        (
            "docs/internal/build-ledger.md is untracked by design (owner's decision, 2026-09-11 — "
            "see .gitignore and tests.conftest.UNTRACKED_BY_DESIGN) and absent from this checkout",
            SkipCause.UNTRACKED_BY_DESIGN,
        ),
        (
            f"WEFT_DATABASE_URL ({_DSN}) is unreachable: refused. `docker compose up -d`.",
            SkipCause.POSTGRES_UNREACHABLE,
        ),
        (
            "WEFT_DATABASE_URL names no reachable Postgres; manual/user-manual.md §7 needs one",
            SkipCause.POSTGRES_UNREACHABLE,
        ),
        (
            "WEFT_QDRANT_URL (http://localhost:6333) is unreachable: [Errno 61]. "
            "`docker compose --profile conformance up -d qdrant`.",
            SkipCause.QDRANT_UNREACHABLE,
        ),
        (
            "no BM25 database at postgresql://weft:weft@localhost:5434/weft "
            "(docker compose --profile bm25 up -d): connection refused",
            SkipCause.BM25_UNREACHABLE,
        ),
        (
            "WEFT_LIVE_API_TESTS is unset: this reaches a live service, so it is opt-in "
            "separately from OPENAI_API_KEY",
            SkipCause.LIVE_API_NOT_OPTED_IN,
        ),
        (
            "OPENAI_API_KEY is unset: the live OpenAI completion checks cannot run",
            SkipCause.LIVE_API_NOT_OPTED_IN,
        ),
        (
            "reaches pl.wikipedia.org and arxiv.org; set WEFT_CORPUS_NETWORK=1 to run it",
            SkipCause.CORPUS_NETWORK_NOT_OPTED_IN,
        ),
        (
            "no corpus document is materialised on this machine, so no quote can be read back",
            SkipCause.CORPUS_NOT_MATERIALISED,
        ),
        (
            "corpus fixture missing: corpus/arxiv/2508.18901v1.pdf",
            SkipCause.CORPUS_NOT_MATERIALISED,
        ),
    ],
)
def test_every_reason_this_tree_writes_names_its_cause(reason: str, cause: SkipCause) -> None:
    # Act
    found = skip_cause(reason)

    # Assert
    assert found is cause


def test_a_reason_no_cause_recognises_names_none() -> None:
    # Act
    found = skip_cause("flaky on Tuesdays")

    # Assert
    assert found is None


def test_an_unrecognised_skip_fails_the_run_naming_the_test_and_its_reason() -> None:
    # Arrange
    skips = [("tests/unit/test_x.py::test_y", "flaky on Tuesdays")]

    # Act
    problems = skip_problems(skips, environ={})

    # Assert
    assert len(problems) == 1
    assert "tests/unit/test_x.py::test_y" in problems[0]
    assert "flaky on Tuesdays" in problems[0]
    assert "SkipCause" in problems[0]
    assert all(cause.name in problems[0] for cause in SkipCause)


def test_a_service_the_environment_claims_fails_the_run_when_it_skips() -> None:
    # Arrange
    skips = [
        ("tests/integration/test_a.py::test_pg", f"WEFT_DATABASE_URL ({_DSN}) is unreachable: x"),
        ("tests/unit/weft_qdrant/test_store.py::test_q", "WEFT_QDRANT_URL (u) is unreachable: y"),
    ]

    # Act
    problems = skip_problems(skips, environ={"WEFT_DATABASE_URL": _DSN})

    # Assert
    assert len(problems) == 1
    assert "tests/integration/test_a.py::test_pg" in problems[0]
    assert "WEFT_DATABASE_URL" in problems[0]


def test_skips_for_known_unclaimed_causes_pass_whatever_their_number() -> None:
    # Arrange — the shape that broke CI: more skips of a cause the environment does not provide.
    skips = [
        (f"tests/unit/weft_qdrant/test_store.py::test_{n}", "WEFT_QDRANT_URL (u) is unreachable")
        for n in range(60)
    ] + [
        (f"tests/docs/test_d.py::test_{n}", "docs/internal/README.md is untracked by design")
        for n in range(40)
    ]

    # Act
    problems = skip_problems(skips, environ={"WEFT_DATABASE_URL": _DSN})

    # Assert
    assert problems == []
