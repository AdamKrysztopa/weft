"""The governance demo exists, runs in CI, and reads what it must — tasks **46.1** and **46.2**.

`scripts/check_governance_demo.py` replays three committed cases from the built wheels. Exit 0 alone
proves nothing — a claims directory holding no claims still prints a table header — so each case is
read for the facts it must carry, and these tests watch each reading refuse the near miss. The
script builds wheels and a virtualenv, so it cannot sit in the `ci-checks` composite; a check
outside the composite is one that can ship and never run (fitness function 0), so this file, which
is in it, pins the poe task and the CI job that run it.
"""

from __future__ import annotations

import ast
import tomllib
from typing import Any, cast

import check_governance_demo
from check_governance_demo import BudgetRoute, CaseResult

from .conftest import REPO_ROOT

GRAPH = "graph-and-vector-rrf.global.answer-correctness"
RAPTOR = "raptor-and-leaves-rrf.global.answer-correctness"
FETCH = "whole-corpus.fetch-operator.answer-correctness"
WHOLE = "whole-corpus.global.answer-correctness"
STALE = "definitely-stale: rung changed since the claim was pinned"
FF38 = (
    "tests/architecture/test_ff38_policy_cites_evidence.py"
    "::test_every_shipped_evidence_rule_cites_evidence_that_holds"
)


def _table(notes: dict[str, str] | None = None, *, graph: str = "-0.080 (-0.111 to -0.049)") -> str:
    notes = notes or {}
    rows = (
        (GRAPH, "harms (harm)", "harm", graph, 80),
        (
            RAPTOR,
            "helps (positive-below-margin)",
            "positive-below-margin",
            "+0.025 (+0.000 to +0.051)",
            80,
        ),
        (FETCH, "helps (worthwhile)", "worthwhile", "+0.075 (+0.039 to +0.117)", 210),
        (WHOLE, "helps (worthwhile)", "worthwhile", "+0.059 (+0.030 to +0.089)", 80),
    )
    lines = [
        "| claim | stated | checked | paired difference | note |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        f"| `{claim}` | {stated} | recomputed: {verdict} | {interval}, n {n}, margin 0.05 "
        f"| {notes.get(claim, '')} |"
        for claim, stated, verdict, interval, n in rows
    )
    return "\n".join(lines)


def _routes(*, at_250000: str = "retrieve-then-generate") -> list[BudgetRoute]:
    def under(ceiling: int) -> BudgetRoute:
        return BudgetRoute(
            ceiling=ceiling,
            pipeline="retrieve-then-generate",
            claims=(),
            reasons=(
                "rule 'whole-corpus-when-it-fits' held but was skipped: its prompt cost 253408 "
                f"exceeds max_prompt_tokens {ceiling}",
                "no rule was usable, so the fallback 'retrieve-then-generate' answers",
            ),
        )

    over = BudgetRoute(
        ceiling=300_000,
        pipeline="whole-corpus-wide-then-generate",
        claims=(FETCH, WHOLE),
        reasons=(
            "rule 'whole-corpus-when-it-fits' held, routing to 'whole-corpus-wide-then-generate'",
        ),
    )
    routes = [under(0), under(100_000), under(250_000), over]
    if at_250000 != "retrieve-then-generate":
        routes[2] = over.model_copy(update={"ceiling": 250_000})
    return routes


def test_the_four_claims_read_their_published_verdicts_and_intervals() -> None:
    # Act
    problems = check_governance_demo.claims_problems(_table(), stale=frozenset())

    # Assert
    assert problems == []


def test_a_moved_interval_is_named_by_its_claim() -> None:
    # Act
    problems = check_governance_demo.claims_problems(
        _table(graph="-0.070 (-0.101 to -0.039)"), stale=frozenset()
    )

    # Assert
    assert any(GRAPH in problem and "-0.080 (-0.111 to -0.049)" in problem for problem in problems)


def test_a_missing_or_extra_claim_is_refused() -> None:
    # Arrange
    missing = "\n".join(line for line in _table().splitlines() if RAPTOR not in line)
    extra = (
        _table() + "\n| `some.other.claim` | helps (worthwhile) | recomputed: worthwhile | x | |"
    )

    # Act
    without = check_governance_demo.claims_problems(missing, stale=frozenset())
    beyond = check_governance_demo.claims_problems(extra, stale=frozenset())

    # Assert
    assert any(RAPTOR in problem for problem in without)
    assert any("some.other.claim" in problem for problem in beyond)


def test_staleness_is_read_per_claim_both_ways() -> None:
    # Arrange — after the drift edit only the two whole-corpus claims rest on the edited rung.
    drifted = _table({FETCH: STALE, WHOLE: STALE})
    both = frozenset({FETCH, WHOLE})

    # Act
    expected = check_governance_demo.claims_problems(drifted, stale=both)
    unexpected = check_governance_demo.claims_problems(drifted, stale=frozenset())
    unmarked = check_governance_demo.claims_problems(_table(), stale=both)

    # Assert
    assert expected == []
    assert any(FETCH in problem for problem in unexpected)
    assert any(WHOLE in problem for problem in unmarked)


def test_the_budget_receipts_name_cost_against_ceiling_until_the_corpus_fits() -> None:
    # Act
    clean = check_governance_demo.budget_problems(_routes())
    wrong = check_governance_demo.budget_problems(_routes(at_250000="whole"))

    # Assert
    assert clean == []
    assert any("250000" in problem for problem in wrong)


def test_the_budget_case_refuses_a_route_that_cites_too_little() -> None:
    # Arrange
    routes = _routes()
    routes[3] = routes[3].model_copy(update={"claims": (WHOLE,)})

    # Act
    problems = check_governance_demo.budget_problems(routes)

    # Assert
    assert any(FETCH in problem for problem in problems)


def test_ff38_must_fail_by_name_naming_the_rule_and_both_claims() -> None:
    # Arrange
    named = (
        f"E   AssertionError: route-by-evidence: rule 'whole-corpus-when-it-fits' cites "
        f"'{FETCH}', which is {STALE}\n"
        f"E     route-by-evidence: rule 'whole-corpus-when-it-fits' cites '{WHOLE}', which is "
        f"{STALE}\nFAILED {FF38} - AssertionError\n1 failed"
    )
    elsewhere = "FAILED tests/architecture/test_other.py::test_x - boom\n1 failed"

    # Act
    expected = check_governance_demo.ff38_problems(1, named, expect_failure=True)
    unnamed = check_governance_demo.ff38_problems(1, elsewhere, expect_failure=True)
    passed = check_governance_demo.ff38_problems(0, "1 passed", expect_failure=False)
    still_red = check_governance_demo.ff38_problems(1, named, expect_failure=False)

    # Assert
    assert expected == []
    assert unnamed != []
    assert passed == []
    assert still_red != []


def test_the_script_imports_nothing_from_tests() -> None:
    # Arrange
    tree = ast.parse((REPO_ROOT / "scripts" / "check_governance_demo.py").read_text())

    # Act
    modules = [
        name
        for node in ast.walk(tree)
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
    ]

    # Assert
    assert modules
    assert not [module for module in modules if module.split(".")[0] == "tests"]


def test_the_governance_demo_is_a_poe_task_and_a_ci_job() -> None:
    # Arrange
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        tasks = cast("dict[str, Any]", tomllib.load(handle)["tool"]["poe"]["tasks"])
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    # Act
    task = tasks.get("governance-demo")

    # Assert
    assert task is not None, "`pyproject.toml` declares no `governance-demo` task"
    assert "scripts/check_governance_demo.py" in str(task)
    assert "scripts/check_governance_demo.py" in workflow, "no CI job runs the governance demo"


def test_the_check_can_actually_fail() -> None:
    # Arrange — one case read clean, and the same case carrying the problem its reading found.
    clean = check_governance_demo.claims_problems(_table(), stale=frozenset())
    moved = check_governance_demo.claims_problems(
        _table(graph="-0.070 (-0.101 to -0.039)"), stale=frozenset()
    )

    # Act
    verdicts = (
        CaseResult(name="claims", problems=tuple(clean), output="").passed,
        CaseResult(name="claims", problems=tuple(moved), output="").passed,
    )

    # Assert
    assert verdicts == (True, False)
