"""The governance demo, replayed from the built wheels — task **46.1**.

Records support a scoped choice, a budget can veto it, and pipeline drift makes its evidence stale
and fails the repository gate. Each case is replayed from committed material by the installed
`weft`, in a clean virtualenv, from a directory outside the checkout:

- **table** — `weft eval table` regenerates `eval/experiments/global-synthesis/table.md` byte for
  byte;
- **claims** — `weft eval claims check` over four claims reads each verdict at its interval;
- **budget** — the shipped `route-by-evidence`, given ceilings the way its own comments say to (a
  derived document), routes a *simulated* corpus profile: the policy is real, the profile is not
  an index, a ceiling bounds the rule's declared prompt cost and nothing else, and every rung is
  offered — a real run leaves `whole-corpus-wide-then-generate` out when `generate` is unmapped or
  its provider cannot count tokens (`weft_retrieve.engine.route_catalogue`);
- **drift** — the install's copy of `whole-corpus-wide-then-generate` edited 260000 → 250000 makes
  both whole-corpus claims definitely-stale; `claims check` still exits 0, because staleness warns,
  and fitness function 38 fails by name; restored, both read clean.

Then **checkout unchanged**. Every edit is to the scratch install, so an interrupted run leaves the
checkout as it found it. A replay generates no answer and writes no record; what the claims do and
do not support is `manual/evidence.md` §3's.

    uv run python scripts/check_governance_demo.py
"""

import asyncio
import hashlib
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from pydantic import BaseModel, ConfigDict

from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.route_ask import resolve_in_catalogue
from weft_engine.registry_bootstrap import Dependencies, resolution_dependencies
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced, SourceId
from weft_kernel.pipeline import Pipeline
from weft_retrieve.contract import QueryScorer, RouteCatalogue, RoutingPolicy
from weft_retrieve.engine import PipelineRouteCatalogue
from weft_retrieve.payload import Query
from weft_retrieve.profile import CorpusProfile, corpus_profile
from weft_store import SourceRecord, SourceStats

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DISTRIBUTIONS: Final[tuple[str, ...]] = ("weft-kernel", "weft-rag")
#: The extras the participants' recipe installs. Without `pdf` every claim here reads
#: possibly-stale, because each experiment's index pipeline names `pdf-text`.
EXTRAS: Final[tuple[str, ...]] = ("openai", "pdf")
#: What `tests/architecture` needs beyond the wheels to run fitness function 38.
TEST_RUNNER: Final[tuple[str, ...]] = ("pytest", "pytest-asyncio", "pytest-timeout")

EXPERIMENT: Final[Path] = Path("eval/experiments/global-synthesis.toml")
COMMITTED_TABLE: Final[Path] = Path("eval/experiments/global-synthesis/table.md")
DRIFTED_DOCUMENT: Final[str] = "whole-corpus-wide-then-generate.yaml"
SHIPPED_BOUND: Final[str] = "max_tokens: 260000"
DRIFTED_BOUND: Final[str] = "max_tokens: 250000"
FF38_TEST: Final[str] = (
    "tests/architecture/test_ff38_policy_cites_evidence.py"
    "::test_every_shipped_evidence_rule_cites_evidence_that_holds"
)

ROUTER: Final[str] = "route-by-evidence"
RULE: Final[str] = "whole-corpus-when-it-fits"
WHOLE_CORPUS: Final[str] = "whole-corpus-wide-then-generate"
DENSE: Final[str] = "retrieve-then-generate"
STALE_NOTE: Final[str] = "definitely-stale: rung changed since the claim was pinned"


class ClaimReading(BaseModel):
    """What `claims check` must print for one claim: its recomputed verdict and interval."""

    model_config = ConfigDict(frozen=True)

    verdict: str
    interval: str


CLAIM_READINGS: Final[Mapping[str, ClaimReading]] = {
    "graph-and-vector-rrf.global.answer-correctness": ClaimReading(
        verdict="harm", interval="-0.080 (-0.111 to -0.049)"
    ),
    "raptor-and-leaves-rrf.global.answer-correctness": ClaimReading(
        verdict="positive-below-margin", interval="+0.025 (+0.000 to +0.051)"
    ),
    "whole-corpus.fetch-operator.answer-correctness": ClaimReading(
        verdict="worthwhile", interval="+0.075 (+0.039 to +0.117)"
    ),
    "whole-corpus.global.answer-correctness": ClaimReading(
        verdict="worthwhile", interval="+0.059 (+0.030 to +0.089)"
    ),
}
WHOLE_CORPUS_CLAIMS: Final[frozenset[str]] = frozenset(
    {"whole-corpus.fetch-operator.answer-correctness", "whole-corpus.global.answer-correctness"}
)

#: `validation-en`'s leaves and tokens as task 43.52 counted them, and the README's declared
#: `generate` window — a profile, simulated, not an index.
SIMULATED_TOKENS: Final[int] = 253_408
SIMULATED_LEAVES: Final[int] = 1_725
SIMULATED_WINDOW: Final[int] = 272_000
CEILINGS: Final[tuple[int, ...]] = (0, 100_000, 250_000, 300_000)


class BudgetRoute(BaseModel):
    """The route the policy chose under one prompt-token ceiling, with its receipt."""

    model_config = ConfigDict(frozen=True)

    ceiling: int
    pipeline: str
    claims: tuple[str, ...]
    reasons: tuple[str, ...]


class Completed(BaseModel):
    """What one spawned command exited with and printed."""

    model_config = ConfigDict(frozen=True)

    returncode: int
    stdout: str
    stderr: str


class CaseResult(BaseModel):
    """One case's verdict, and everything its commands printed."""

    model_config = ConfigDict(frozen=True)

    name: str
    problems: tuple[str, ...]
    output: str

    @property
    def passed(self) -> bool:
        """Whether the case read what it must."""
        return not self.problems


def _claim_rows(markdown: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in markdown.splitlines():
        if line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows[cells[0].strip("`")] = cells
    return rows


def _row_problems(claim: str, reading: ClaimReading, cells: list[str], *, stale: bool) -> list[str]:
    checked, difference, note = (*cells, "", "", "", "", "")[2:5]
    problems: list[str] = []
    if checked != f"recomputed: {reading.verdict}":
        problems.append(f"{claim} reads {checked!r}, not 'recomputed: {reading.verdict}'")
    if not difference.startswith(f"{reading.interval},"):
        problems.append(f"{claim} reads {difference!r}, not {reading.interval}")
    if stale and STALE_NOTE not in note:
        problems.append(f"{claim} should read {STALE_NOTE!r}; its note is {note!r}")
    if not stale and note:
        problems.append(f"{claim} should carry no note; it reads {note!r}")
    return problems


def claims_problems(markdown: str, *, stale: frozenset[str]) -> list[str]:
    """What `claims check`'s table gets wrong: a claim missing, extra, or misread."""
    rows = _claim_rows(markdown)
    problems = [
        f"{claim} is in the table but is not one of the demo's four"
        for claim in sorted(set(rows) - set(CLAIM_READINGS))
    ]
    for claim, reading in CLAIM_READINGS.items():
        cells = rows.get(claim)
        if cells is None:
            problems.append(f"{claim} is missing from the table")
        else:
            problems.extend(_row_problems(claim, reading, cells, stale=claim in stale))
    return problems


def _route_problems(route: BudgetRoute) -> list[str]:
    if route.ceiling >= SIMULATED_TOKENS:
        pipeline, receipt, cites = WHOLE_CORPUS, f"rule '{RULE}' held", WHOLE_CORPUS_CLAIMS
    else:
        receipt = f"its prompt cost {SIMULATED_TOKENS} exceeds max_prompt_tokens {route.ceiling}"
        pipeline, cites = DENSE, frozenset[str]()
    where = f"at max_prompt_tokens {route.ceiling}"
    problems: list[str] = []
    if route.pipeline != pipeline:
        problems.append(f"{where} the policy chose {route.pipeline!r}, not {pipeline!r}")
    if not any(receipt in reason for reason in route.reasons):
        problems.append(f"{where} no reason reads {receipt!r}: {list(route.reasons)}")
    if frozenset(route.claims) != cites:
        problems.append(f"{where} the route cites {sorted(route.claims)}, not {sorted(cites)}")
    return problems


def budget_problems(routes: Sequence[BudgetRoute]) -> list[str]:
    """What the policy's routes get wrong, one ceiling at a time."""
    asked = [route.ceiling for route in routes]
    problems = [] if asked == list(CEILINGS) else [f"routes for {asked}, not {list(CEILINGS)}"]
    for route in routes:
        problems.extend(_route_problems(route))
    return problems


def ff38_problems(exit_code: int, output: str, *, expect_failure: bool) -> list[str]:
    """Whether fitness function 38 failed by name, naming the rule and both claims, or passed."""
    if not expect_failure:
        passed = exit_code == 0 and "1 passed" in output
        return [] if passed else [f"FF38 exited {exit_code}; restored, it must pass"]
    problems: list[str] = []
    named = any(line.startswith("FAILED ") and FF38_TEST in line for line in output.splitlines())
    if exit_code != 1 or not named:
        problems.append(f"FF38 exited {exit_code} without its named test failing")
    problems.extend(
        f"FF38 does not name rule '{RULE}' citing {claim} as definitely-stale"
        for claim in sorted(WHOLE_CORPUS_CLAIMS)
        if f"rule '{RULE}' cites '{claim}', which is definitely-stale" not in output
    )
    return problems


def simulated_profile() -> CorpusProfile:
    """One complete source the size of `validation-en`, under the README's `generate` window."""
    record = SourceRecord(
        id=SourceId("simulated"),
        uri="simulated://validation-en",
        content_hash="simulated",
        indexed_at=datetime.now(UTC),
        pipeline="index-text",
        stats=SourceStats(
            leaves=SIMULATED_LEAVES,
            characters=0,
            tokens=SIMULATED_TOKENS,
            tokenizer="simulated",
        ),
    )
    return corpus_profile((record,), context_tokens=SIMULATED_WINDOW)


def budget_ceilings(argv: Sequence[str]) -> tuple[int, ...]:
    """The ceilings after `--budget`, or the demo's four when none is named."""
    named: list[int] = []
    for value in argv[1:]:
        if not value.isdigit():
            raise SystemExit(f"{value!r} is not a prompt-token ceiling; name whole numbers")
        named.append(int(value))
    return tuple(named) or CEILINGS


def _write_budgets(directory: Path, ceilings: Sequence[int]) -> None:
    for ceiling in ceilings:
        (directory / f"route-with-budget-{ceiling}.yaml").write_text(
            f"name: route-with-budget-{ceiling}\nextends: {ROUTER}\nset:\n"
            f"  - {{id: decide, with: {{constraints: {{max_prompt_tokens: {ceiling}}}}}}}\n",
            encoding="utf-8",
        )


async def _route(
    pipeline: Pipeline, ceiling: int, *, catalogue: Mapping[str, Pipeline], deps: Dependencies
) -> BudgetRoute:
    resolved = resolve_in_catalogue(
        pipeline,
        registry=deps.registry,
        catalogue=catalogue,
        reports=deps.reports,
        contributions=deps.contributions,
    )
    stages = {stage.id: stage for stage in resolved.stages}
    score, decide = stages["score"], stages["decide"]
    scorer = cast(QueryScorer, deps.registry.lookup(QueryScorer, score.use)(score.config))
    policy = cast(RoutingPolicy, deps.registry.lookup(RoutingPolicy, decide.use)(decide.config))
    services = ServiceRegistry()
    services.add(CorpusProfile, simulated_profile())
    services.add(RouteCatalogue, PipelineRouteCatalogue(catalogue))
    ctx = Context(tenant_id="demo", run_id="demo", trace_id="demo", locale="en", services=services)
    card = await scorer.run(Query(text="what does the whole corpus say about budgets?"), ctx)
    if not isinstance(card, Produced):
        raise SystemExit(f"the query profiler refused: {card}")
    route = await policy.run(card.value, ctx)
    if not isinstance(route, Produced):
        raise SystemExit(f"the policy refused at max_prompt_tokens {ceiling}: {route}")
    return BudgetRoute(
        ceiling=ceiling,
        pipeline=route.value.pipeline,
        claims=route.value.claims,
        reasons=route.value.reasons,
    )


async def budget_routes(ceilings: Sequence[int]) -> list[BudgetRoute]:
    """The shipped policy's route under each ceiling, resolved as a project document would be.

    The derived documents go to a directory of their own, so a run from a checkout leaves it clean.
    """
    with tempfile.TemporaryDirectory(prefix="weft-budget-") as scratch:
        project = Path(scratch)
        _write_budgets(project, ceilings)
        deps = resolution_dependencies(config_path=project / "weft.toml")
        catalogue = full_catalogue(directory=project, reports=deps.reports)
        return [
            await _route(
                catalogue[f"route-with-budget-{ceiling}"], ceiling, catalogue=catalogue, deps=deps
            )
            for ceiling in ceilings
        ]


async def _print_budget_routes(ceilings: Sequence[int]) -> int:
    for route in await budget_routes(ceilings):
        print(route.model_dump_json())
    return 0


def _environment() -> dict[str, str]:
    env = {
        key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "VIRTUAL_ENV"}
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


async def _run(argv: Sequence[str | Path], *, cwd: Path) -> Completed:
    process = await asyncio.create_subprocess_exec(
        *map(str, argv),
        cwd=cwd,
        env=_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return Completed(
        returncode=cast(int, process.returncode),
        stdout=stdout.decode("utf-8"),
        stderr=stderr.decode("utf-8"),
    )


async def _must(argv: Sequence[str | Path], *, cwd: Path) -> None:
    completed = await _run(argv, cwd=cwd)
    if completed.returncode != 0:
        command = " ".join(map(str, argv))
        raise SystemExit(f"{command} exited {completed.returncode}:\n{completed.stderr}")


async def install(root: Path) -> Path:
    """Build both wheels and install them, and the test runner, into a fresh virtualenv."""
    wheels = root / "wheels"
    for name in DISTRIBUTIONS:
        build = ["uv", "build", "--package", name, "--wheel", "--out-dir", wheels, REPO_ROOT]
        await _must(build, cwd=root)
    venv = root / "venv"
    await _must(["uv", "venv", "--quiet", "--python", "3.12", venv], cwd=root)
    python = venv / "bin" / "python"
    kernel, rag = (next(wheels.glob(f"{name.replace('-', '_')}-*.whl")) for name in DISTRIBUTIONS)
    rag_with_extras = f"{rag}[{','.join(EXTRAS)}]"
    install = ["uv", "pip", "install", "--quiet", "--python", python, kernel, rag_with_extras]
    await _must([*install, *TEST_RUNNER], cwd=root)
    return venv


async def table_case(venv: Path, project: Path) -> CaseResult:
    """`weft eval table` regenerates the committed global-synthesis table byte for byte."""
    weft = venv / "bin" / "weft"
    completed = await _run([weft, "eval", "table", REPO_ROOT / EXPERIMENT], cwd=project)
    committed = (REPO_ROOT / COMMITTED_TABLE).read_text(encoding="utf-8")
    problems: list[str] = []
    if completed.returncode != 0:
        problems.append(f"weft eval table exited {completed.returncode}")
    elif completed.stdout != committed:
        problems.append(f"the regenerated table differs from {COMMITTED_TABLE}")
    output = completed.stdout + completed.stderr
    return CaseResult(name="table", problems=tuple(problems), output=output)


async def _claims_check(
    venv: Path, project: Path, *, stale: frozenset[str], label: str
) -> CaseResult:
    weft = venv / "bin" / "weft"
    completed = await _run(
        [weft, "eval", "claims", "check", "--directory", project / "claims", "--root", REPO_ROOT],
        cwd=project,
    )
    problems = [] if completed.returncode == 0 else [f"claims check exited {completed.returncode}"]
    problems.extend(claims_problems(completed.stdout, stale=stale))
    output = completed.stdout + completed.stderr
    return CaseResult(name=label, problems=tuple(problems), output=output)


async def claims_case(venv: Path, project: Path) -> CaseResult:
    """The four claims read their verdicts at their intervals, none of them stale."""
    return await _claims_check(venv, project, stale=frozenset(), label="claims")


async def budget_case(venv: Path, project: Path) -> CaseResult:
    """The shipped policy over the simulated profile, through the installed packs."""
    await installed_package(venv, project)
    python = venv / "bin" / "python"
    completed = await _run([python, Path(__file__).resolve(), "--budget"], cwd=project)
    name = "budget (simulated profile)"
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        problems = (f"the budget routes exited {completed.returncode}",)
        return CaseResult(name=name, problems=problems, output=output)
    routes = [BudgetRoute.model_validate_json(line) for line in completed.stdout.splitlines()]
    return CaseResult(name=name, problems=tuple(budget_problems(routes)), output=output)


async def _ff38(venv: Path, project: Path, *, expect_failure: bool) -> CaseResult:
    python = venv / "bin" / "python"
    completed = await _run(
        [
            *(python, "-m", "pytest", REPO_ROOT / FF38_TEST, "-q", "-p", "no:cacheprovider"),
            *("--rootdir", REPO_ROOT, "-c", REPO_ROOT / "pyproject.toml"),
        ],
        cwd=project,
    )
    output = completed.stdout + completed.stderr
    problems = ff38_problems(completed.returncode, output, expect_failure=expect_failure)
    return CaseResult(name="FF38", problems=tuple(problems), output=output)


async def installed_package(venv: Path, project: Path) -> Path:
    """Where the scratch interpreter resolves `weft_retrieve`, refused unless it is the install."""
    python = venv / "bin" / "python"
    completed = await _run(
        [python, "-c", "import weft_retrieve; print(weft_retrieve.__file__)"], cwd=project
    )
    package = Path(completed.stdout.strip()).resolve().parent
    if not package.is_relative_to(venv.resolve()):
        raise SystemExit(f"the scratch interpreter resolves {package}, not the install's copy")
    return package


async def installed_document(venv: Path, project: Path) -> Path:
    """The installed copy of the pipeline document the drift case edits."""
    document = await installed_package(venv, project) / "pipelines" / DRIFTED_DOCUMENT
    if not document.is_file():
        raise SystemExit(f"the scratch install carries no {document}")
    return document


async def _drifted(venv: Path, project: Path) -> list[CaseResult]:
    document = await installed_document(venv, project)
    shipped = document.read_text(encoding="utf-8")
    if shipped.count(SHIPPED_BOUND) != 1:
        problem = (f"{DRIFTED_DOCUMENT} does not carry {SHIPPED_BOUND!r} exactly once",)
        return [CaseResult(name="drift edit", problems=problem, output=shipped)]
    try:
        return await _checks_while_drifted(venv, project, document, shipped)
    finally:
        document.write_text(shipped, encoding="utf-8")


async def _checks_while_drifted(
    venv: Path, project: Path, document: Path, shipped: str
) -> list[CaseResult]:
    document.write_text(shipped.replace(SHIPPED_BOUND, DRIFTED_BOUND), encoding="utf-8")
    return [
        await _claims_check(venv, project, stale=WHOLE_CORPUS_CLAIMS, label="drifted claims check"),
        await _ff38(venv, project, expect_failure=True),
    ]


async def drift_case(venv: Path, project: Path) -> CaseResult:
    """Drift goes stale and fails the gate by name; restored, both read clean."""
    steps = [
        *await _drifted(venv, project),
        await _claims_check(venv, project, stale=frozenset(), label="restored claims check"),
        await _ff38(venv, project, expect_failure=False),
    ]
    return CaseResult(
        name="drift",
        problems=tuple(f"{step.name}: {problem}" for step in steps for problem in step.problems),
        output="\n".join(f"--- {step.name}\n{step.output}" for step in steps),
    )


async def checkout_state(root: Path = REPO_ROOT) -> str:
    """The checkout's status and a digest of its diff, so two readings compare as one string.

    Refused where git cannot read `root`: two empty readings would otherwise compare as unchanged.
    """
    readings: list[str] = []
    for argv in (
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        ["git", "diff", "HEAD", "--binary"],
    ):
        completed = await _run(argv, cwd=root)
        if completed.returncode != 0:
            command = " ".join(argv)
            raise SystemExit(
                f"{command} exited {completed.returncode} in {root}:\n{completed.stderr}"
            )
        readings.append(completed.stdout)
    status, diff = readings
    return status + hashlib.sha256(diff.encode()).hexdigest()


def write_project(project: Path) -> None:
    """A directory outside the checkout, holding copies of the four claims the demo reads."""
    (project / "claims").mkdir(parents=True)
    for claim in CLAIM_READINGS:
        shutil.copy(REPO_ROOT / "eval" / "claims" / f"{claim}.toml", project / "claims")


async def walk(venv: Path, project: Path) -> list[CaseResult]:
    """Every case in order, stopping at the first that does not read what it must."""
    results: list[CaseResult] = []
    for case in (table_case, claims_case, budget_case, drift_case):
        results.append(await case(venv, project))
        if not results[-1].passed:
            break
    return results


async def replay() -> int:
    """Replay the demo once; 0 only if every case and the checkout read what they must."""
    before = await checkout_state()
    with tempfile.TemporaryDirectory(prefix="weft-governance-") as scratch:
        root = Path(scratch)
        venv = await install(root)
        project = root / "project"
        write_project(project)
        results = await walk(venv, project)
    after = await checkout_state()
    unchanged = () if after == before else ("the checkout's status or diff moved during the run",)
    results.append(CaseResult(name="checkout unchanged", problems=unchanged, output=after))
    for result in results:
        print(f"{'ok  ' if result.passed else 'FAIL'} {result.name}")
    failed = next((result for result in results if not result.passed), None)
    if failed is None:
        return 0
    detail = "\n".join(failed.problems)
    print(f"\n{failed.name}:\n{detail}\n\n{failed.output}", file=sys.stderr)
    return 1


def main(argv: Sequence[str]) -> int:
    """The script's one bridge into async: the replay, or under `--budget` the policy's routes.

    `--budget [CEILING ...]` prints the route under each ceiling and asserts nothing, so a
    participant reads the receipt themselves.
    """
    if argv[:1] == ["--budget"]:
        return asyncio.run(_print_budget_routes(budget_ceilings(argv)))
    return asyncio.run(replay())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
