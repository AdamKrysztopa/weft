"""Task 44.31 — `weft eval claims check`: a row per claim, every mismatch refused at once."""

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from weft_cli.eval_claims import (
    EvalClaimsCheckArgs,
    EvalClaimsCheckCommand,
    EvalClaimsCheckResult,
    EvalClaimsPinArgs,
    EvalClaimsPinCommand,
    EvalClaimsRenderCommand,
)
from weft_command.contract import CommandResult
from weft_command.permission import PermissionClass
from weft_engine import registry_bootstrap
from weft_eval.claims import ClaimDocumentError, load_claim
from weft_eval.claims_check import ClaimMismatchError
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Outcome, Produced

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def deps(tmp_path_factory: pytest.TempPathFactory) -> Iterator[registry_bootstrap.Dependencies]:
    scratch = tmp_path_factory.mktemp("claims-command")
    config = scratch / "weft.toml"
    config.write_text("", encoding="utf-8")
    previous = Path.cwd()
    os.chdir(scratch)
    patcher = mock.patch.dict(
        os.environ, {"WEFT_DATABASE_URL": "postgresql://nobody@localhost:1/none"}
    )
    patcher.start()
    try:
        yield registry_bootstrap.build_dependencies(config_path=config)
    finally:
        patcher.stop()
        os.chdir(previous)


def _ctx(deps: registry_bootstrap.Dependencies) -> Context:
    services = ServiceRegistry()
    services.add(registry_bootstrap.Dependencies, deps)
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=services)


_VERDICT_OF_STATUS = {"helps": "worthwhile", "no-gain": "benefit-ruled-out", "harms": "harm"}


def _claim_text(claim_id: str, status: str) -> str:
    return f"""\
[claim]
schema = 2
id = "{claim_id}"
rung = "whole-corpus-wide-then-generate"
baseline = "retrieve-then-generate"
metric = "answer_correctness"
status = "{status}"
verdict = "{_VERDICT_OF_STATUS[status]}"
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


def _markdown(outcome: Outcome[CommandResult]) -> str:
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, EvalClaimsCheckResult)
    return outcome.value.markdown


@pytest.fixture
def root(tmp_path: Path) -> Path:
    experiments = tmp_path / "eval" / "experiments"
    experiments.mkdir(parents=True)
    shutil.copy(REPO / "eval/experiments/whole-corpus-en.toml", experiments)
    shutil.copytree(
        REPO / "eval/experiments/whole-corpus-en/runs", experiments / "whole-corpus-en/runs"
    )
    shutil.copytree(REPO / "eval/experiments/pipelines", experiments / "pipelines")
    (tmp_path / "eval" / "claims").mkdir()
    return tmp_path


async def test_every_claim_gets_a_row_with_its_recomputed_difference(
    root: Path, deps: registry_bootstrap.Dependencies
) -> None:
    # Arrange
    (root / "eval/claims/a.one.toml").write_text(_claim_text("a.one", "helps"), encoding="utf-8")

    # Act
    outcome = await EvalClaimsCheckCommand().run(EvalClaimsCheckArgs(root=str(root)), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, EvalClaimsCheckResult)
    assert (
        "| `a.one` | helps (worthwhile) | recomputed: worthwhile | +0.075" in outcome.value.markdown
    )


async def test_every_mismatched_claim_is_named_in_one_refusal(
    root: Path, deps: registry_bootstrap.Dependencies
) -> None:
    # Arrange
    (root / "eval/claims/a.one.toml").write_text(_claim_text("a.one", "no-gain"), encoding="utf-8")
    (root / "eval/claims/b.two.toml").write_text(_claim_text("b.two", "harms"), encoding="utf-8")
    (root / "eval/claims/c.ok.toml").write_text(_claim_text("c.ok", "helps"), encoding="utf-8")

    # Act / Assert
    with pytest.raises(ClaimMismatchError) as raised:
        await EvalClaimsCheckCommand().run(EvalClaimsCheckArgs(root=str(root)), _ctx(deps))

    # Assert
    message = str(raised.value)
    assert "'a.one'" in message
    assert "'b.two'" in message
    assert "c.ok" not in message


def test_the_command_reads_only() -> None:
    # Assert
    assert EvalClaimsCheckCommand.permission_class is PermissionClass.READ


async def test_render_prints_the_generated_table_with_a_never_row(
    root: Path, monkeypatch: pytest.MonkeyPatch, deps: registry_bootstrap.Dependencies
) -> None:
    # Arrange
    (root / "eval/claims/a.one.toml").write_text(_claim_text("a.one", "helps"), encoding="utf-8")
    shipped: tuple[str, ...] = ("whole-corpus-wide-then-generate", "hyde-then-generate")

    def _fixed(_context: Context) -> tuple[str, ...]:
        return shipped

    monkeypatch.setattr("weft_cli.eval_claims._shipped_rungs", _fixed)

    # Act
    outcome = await EvalClaimsRenderCommand().run(EvalClaimsCheckArgs(root=str(root)), _ctx(deps))

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, EvalClaimsCheckResult)
    table = outcome.value.markdown
    assert (
        "| `whole-corpus-wide-then-generate` | **helps (worthwhile)** against "
        "`retrieve-then-generate`" in table
    )
    assert table.splitlines()[-1] == "| `hyde-then-generate` | never | none |"


async def test_render_refuses_when_a_claim_is_unsupported_as_check_does(
    root: Path, deps: registry_bootstrap.Dependencies
) -> None:
    # Arrange
    (root / "eval/claims/a.one.toml").write_text(_claim_text("a.one", "harms"), encoding="utf-8")

    # Act / Assert
    with pytest.raises(ClaimMismatchError, match="'a.one'"):
        await EvalClaimsRenderCommand().run(EvalClaimsCheckArgs(root=str(root)), _ctx(deps))


async def test_an_unpinned_claim_is_possibly_stale_and_pinning_it_makes_it_valid(
    root: Path, deps: registry_bootstrap.Dependencies
) -> None:
    # Arrange
    path = root / "eval/claims/a.one.toml"
    path.write_text(_claim_text("a.one", "helps"), encoding="utf-8")
    args = EvalClaimsCheckArgs(root=str(root))
    pin_args = EvalClaimsPinArgs(root=str(root), claim="a.one")

    # Act
    before = await EvalClaimsCheckCommand().run(args, _ctx(deps))
    pinned = await EvalClaimsPinCommand().run(pin_args, _ctx(deps))
    after = await EvalClaimsCheckCommand().run(args, _ctx(deps))

    # Assert
    assert _markdown(before) is not None
    assert "possibly-stale: no evidence fingerprint is pinned" in _markdown(before)
    assert "pinned `a.one`" in _markdown(pinned)
    assert load_claim(path).fingerprint is not None
    assert "stale" not in _markdown(after)


async def test_pinning_twice_changes_nothing_the_second_time(
    root: Path, deps: registry_bootstrap.Dependencies
) -> None:
    # Arrange
    path = root / "eval/claims/a.one.toml"
    path.write_text(_claim_text("a.one", "helps"), encoding="utf-8")
    pin_args = EvalClaimsPinArgs(root=str(root), claim="a.one")
    await EvalClaimsPinCommand().run(pin_args, _ctx(deps))
    first = path.read_text(encoding="utf-8")

    # Act
    await EvalClaimsPinCommand().run(pin_args, _ctx(deps))

    # Assert
    assert path.read_text(encoding="utf-8") == first


async def test_a_pipeline_changed_after_the_pin_is_reported_definitely_stale_naming_it(
    root: Path, deps: registry_bootstrap.Dependencies
) -> None:
    # Arrange — pin, then move the pinned rung digest as a changed pipeline would.
    path = root / "eval/claims/a.one.toml"
    path.write_text(_claim_text("a.one", "helps"), encoding="utf-8")
    args = EvalClaimsCheckArgs(root=str(root))
    pin_args = EvalClaimsPinArgs(root=str(root), claim="a.one")
    await EvalClaimsPinCommand().run(pin_args, _ctx(deps))
    pinned = load_claim(path).fingerprint
    assert pinned is not None
    path.write_text(
        path.read_text(encoding="utf-8").replace(pinned.rung, "0" * 32), encoding="utf-8"
    )

    # Act
    outcome = await EvalClaimsCheckCommand().run(args, _ctx(deps))

    # Assert
    assert "definitely-stale: rung changed since the claim was pinned" in _markdown(outcome)


async def test_pinning_refuses_a_claim_its_records_do_not_support_and_writes_nothing(
    root: Path, deps: registry_bootstrap.Dependencies
) -> None:
    # Arrange
    path = root / "eval/claims/a.one.toml"
    text = _claim_text("a.one", "no-gain")
    path.write_text(text, encoding="utf-8")

    # Act / Assert
    with pytest.raises(ClaimMismatchError):
        await EvalClaimsPinCommand().run(
            EvalClaimsPinArgs(root=str(root), claim="a.one"), _ctx(deps)
        )
    assert path.read_text(encoding="utf-8") == text


def test_pinning_writes_a_file_so_it_is_not_a_read() -> None:
    # Assert
    assert EvalClaimsPinCommand.permission_class is PermissionClass.WRITE


async def test_pinning_a_claim_that_does_not_exist_names_the_ones_that_do(
    root: Path, deps: registry_bootstrap.Dependencies
) -> None:
    # Arrange
    (root / "eval/claims/a.one.toml").write_text(_claim_text("a.one", "helps"), encoding="utf-8")

    # Act / Assert
    with pytest.raises(ClaimDocumentError, match="no claim 'a.two'.*a.one"):
        await EvalClaimsPinCommand().run(
            EvalClaimsPinArgs(root=str(root), claim="a.two"), _ctx(deps)
        )
