"""A stranger's first hour, run against the built wheels — carried repair **R20.8**.

An outside review asked for one check that does what somebody arriving from a package index does,
as an external process, rather than more tests of the commands one at a time. This builds both
wheels, installs them into a clean virtualenv, creates its own database on the server
`WEFT_DATABASE_URL` names, and drives the installed `weft` from a directory outside the repository:

    plugins doctor → index → lexical ask → the defaulted-`hash` refusal → an embedder chosen →
    vector ask → eval experiment → eval table, both defaulted

Each step names the exit code it expects and a fragment its output must carry; the first that
disagrees fails the run with everything the binary printed. The database is dropped by the exact
name this run created, never by pattern. Fixed argv, no shell, `check=False` — the shape
`check_isolated_installs.py` set.

    uv run python scripts/check_golden_path.py
"""

import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

REPO_ROOT = Path(__file__).resolve().parent.parent
DISTRIBUTIONS = ("weft-kernel", "weft-rag")

#: Six documents and one chunk each, so a cutoff of 5 has more candidates than it scores — fewer,
#: and every `@5` metric is refused per question, which is correct and measures nothing.
_DOCUMENTS = {
    "warp.txt": "The warp is the set of threads held taut on the loom before weaving begins.",
    "weft.txt": "The weft is the thread passed over and under the warp to make the cloth.",
    "shuttle.txt": "A shuttle carries the weft yarn across the loom from one side to the other.",
    "heddle.txt": "Heddles lift chosen warp threads so the shuttle can pass between them.",
    "reed.txt": "The reed beats each new row of weft firmly against the cloth already woven.",
    "selvage.txt": "The selvage is the tightly woven edge that keeps the cloth from fraying.",
}
_QUESTIONS = {
    "q-warp": ("which threads are held taut on the loom", "warp.txt"),
    "q-shuttle": ("what carries the yarn across the loom", "shuttle.txt"),
    "q-selvage": ("which edge keeps the cloth from fraying", "selvage.txt"),
}
_EXPERIMENT = """[experiment]
schema = 1
name = "golden"
questions = "questions.toml"
corpus = "../corpus"
repeats = 2
top_k = 5
metrics = ["mrr@5"]
minimum_detectable_effect = 0.05

[[arm]]
name = "lexical"
pipeline = "index-text"
query_pipeline = "lexical-retrieve"

[[arm]]
name = "vector"
pipeline = "index-text"
"""


@dataclass(frozen=True)
class Step:
    """One invocation of the installed binary and what it must do."""

    name: str
    argv: tuple[str, ...]
    exit_code: int
    expect: str


@dataclass(frozen=True)
class StepResult:
    """What one step did, against what it was asked to."""

    step: Step
    exit_code: int
    output: str

    @property
    def passed(self) -> bool:
        """Whether the step exited as expected and printed what it must."""
        return self.exit_code == self.step.exit_code and self.step.expect in self.output


def steps() -> tuple[tuple[Step, ...], tuple[Step, ...]]:
    """The path before an embedder is chosen, and the path after."""
    question = "which threads are held taut on the loom"
    before = (
        Step("plugins doctor", ("plugins", "doctor"), 0, "embed"),
        Step("index", ("index", "corpus"), 0, "carries no semantic meaning"),
        Step(
            "lexical ask",
            ("ask", question, "--retrieve-only", "--pipeline", "lexical-retrieve"),
            0,
            "held taut",
        ),
        Step(
            "vector ask, embedder unchosen",
            ("ask", question, "--retrieve-only"),
            1,
            "lexical-retrieve",
        ),
    )
    after = (
        Step("vector ask, embedder chosen", ("ask", question, "--retrieve-only"), 0, "held taut"),
        Step(
            "eval experiment", ("eval", "experiment", "eval/golden.toml", "--yes"), 0, "4 record(s)"
        ),
        Step("eval table", ("eval", "table", "eval/golden.toml"), 0, "# Evidence — golden"),
    )
    return before, after


def run_step(step: Step, *, binary: Path, cwd: Path, env: dict[str, str]) -> StepResult:
    """Run one step through the installed binary and keep everything it printed."""
    completed = subprocess.run(  # noqa: S603
        (str(binary), *step.argv), cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    return StepResult(
        step=step, exit_code=completed.returncode, output=completed.stdout + completed.stderr
    )


def _run(argv: list[str]) -> None:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603
    if completed.returncode != 0:
        raise SystemExit(f"{' '.join(argv)} exited {completed.returncode}:\n{completed.stderr}")


def install(root: Path) -> Path:
    """Build both wheels and install them into a fresh virtualenv; return its `weft`."""
    wheels = root / "wheels"
    for name in DISTRIBUTIONS:
        _run(
            ["uv", "build", "--package", name, "--wheel", "--out-dir", str(wheels), str(REPO_ROOT)]
        )
    venv = root / "venv"
    _run(["uv", "venv", "--quiet", "--python", "3.12", str(venv)])
    python = venv / "bin" / "python"
    _run(
        [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--python",
            str(python),
            *map(str, wheels.glob("*.whl")),
        ]
    )
    return venv / "bin" / "weft"


def write_project(project: Path) -> None:
    """A corpus, a question set and an experiment document, as a stranger would write them."""
    (project / "corpus").mkdir(parents=True)
    (project / "eval").mkdir()
    for name, text in _DOCUMENTS.items():
        (project / "corpus" / name).write_text(text + "\n", encoding="utf-8")
    questions = [
        "[question_set]\nschema = 2\n"
        'absent = ["kind", "difficulty", "quote", "reference_answer", "notes"]\n'
        'absent_reason = "the golden-path check"\naxes = []\n'
    ]
    for question_id, (text, document) in _QUESTIONS.items():
        questions.append(
            f'\n[[question]]\nid = "{question_id}"\ntext = "{text}"\nlanguage = "en"\n'
            f'relevant_documents = ["{document}"]\n'
        )
    (project / "eval" / "questions.toml").write_text("".join(questions), encoding="utf-8")
    (project / "eval" / "golden.toml").write_text(_EXPERIMENT, encoding="utf-8")


def _with_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{name}"))


def _environment(database_url: str) -> dict[str, str]:
    env = {
        key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "VIRTUAL_ENV"}
    }
    env["WEFT_DATABASE_URL"] = database_url
    return env


def walk(binary: Path, project: Path, database_url: str) -> list[StepResult]:
    """Every step in order, stopping at the first that does not do what it must."""
    env = _environment(database_url)
    before, after = steps()
    results: list[StepResult] = []
    for phase, chosen in ((before, False), (after, True)):
        if chosen:
            (project / "weft.toml").write_text('[services]\nembed = "hash"\n', encoding="utf-8")
        for step in phase:
            results.append(run_step(step, binary=binary, cwd=project, env=env))
            if not results[-1].passed:
                return results
    return results


def _walk_on(url: str) -> list[StepResult]:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
    with tempfile.TemporaryDirectory(prefix="weft-golden-") as scratch:
        root = Path(scratch)
        binary = install(root)
        project = root / "project"
        write_project(project)
        return walk(binary, project, url)


def main() -> int:
    """Run the golden path once; exit 0 only if every step did what it must."""
    server = os.environ.get("WEFT_DATABASE_URL")
    if not server:
        print(
            "WEFT_DATABASE_URL is unset; the golden path needs a pgvector server", file=sys.stderr
        )
        return 2
    database = f"weft_golden_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(server, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    try:
        results = _walk_on(_with_database(server, database))
    finally:
        with psycopg.connect(server, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
            )
    for result in results:
        print(f"{'ok  ' if result.passed else 'FAIL'} {result.step.name}")
    failed = [result for result in results if not result.passed]
    if failed:
        result = failed[0]
        print(
            f"\n{result.step.name}: exited {result.exit_code}, expected {result.step.exit_code} "
            f"and output carrying {result.step.expect!r}:\n{result.output}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
