"""Task 44.31 — `weft eval claims check`: a row per claim, every mismatch refused at once."""

import shutil
from pathlib import Path

import pytest

from weft_cli.eval_claims import EvalClaimsCheckArgs, EvalClaimsCheckCommand, EvalClaimsCheckResult
from weft_command.permission import PermissionClass
from weft_eval.claims_check import ClaimMismatchError
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced

REPO = Path(__file__).resolve().parents[3]


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=ServiceRegistry())


def _claim_text(claim_id: str, status: str) -> str:
    return f"""\
[claim]
schema = 1
id = "{claim_id}"
rung = "whole-corpus-wide-then-generate"
baseline = "retrieve-then-generate"
metric = "answer_correctness"
status = "{status}"
basis = "records"
margin = 0.05

[claim.population]
benchmark = "validation-en"
language = "en"
question_sets = []

[claim.source]
experiment = "eval/experiments/whole-corpus-en.toml"
invocation = "77a0ab088ccd43688bc0403932c95e6b"
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    experiments = tmp_path / "eval" / "experiments"
    experiments.mkdir(parents=True)
    shutil.copy(REPO / "eval/experiments/whole-corpus-en.toml", experiments)
    shutil.copytree(
        REPO / "eval/experiments/whole-corpus-en/runs", experiments / "whole-corpus-en/runs"
    )
    (tmp_path / "eval" / "claims").mkdir()
    return tmp_path


async def test_every_claim_gets_a_row_with_its_recomputed_difference(root: Path) -> None:
    # Arrange
    (root / "eval/claims/a.one.toml").write_text(_claim_text("a.one", "helps"), encoding="utf-8")

    # Act
    outcome = await EvalClaimsCheckCommand().run(EvalClaimsCheckArgs(root=str(root)), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, EvalClaimsCheckResult)
    assert "| `a.one` | helps | recomputed: worthwhile | +0.075" in outcome.value.markdown


async def test_every_mismatched_claim_is_named_in_one_refusal(root: Path) -> None:
    # Arrange
    (root / "eval/claims/a.one.toml").write_text(_claim_text("a.one", "no-gain"), encoding="utf-8")
    (root / "eval/claims/b.two.toml").write_text(_claim_text("b.two", "harms"), encoding="utf-8")
    (root / "eval/claims/c.ok.toml").write_text(_claim_text("c.ok", "helps"), encoding="utf-8")

    # Act / Assert
    with pytest.raises(ClaimMismatchError) as raised:
        await EvalClaimsCheckCommand().run(EvalClaimsCheckArgs(root=str(root)), _ctx())

    # Assert
    message = str(raised.value)
    assert "'a.one'" in message
    assert "'b.two'" in message
    assert "c.ok" not in message


def test_the_command_reads_only() -> None:
    # Assert
    assert EvalClaimsCheckCommand.permission_class is PermissionClass.READ
