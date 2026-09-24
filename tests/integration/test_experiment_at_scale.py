"""The experiment harness, run at scale for free — ledger task **38.15**.

Phase 38's two measurements ran seven times between them, and six of the defects that cost those
runs were invisible to 3,390 unit tests because each sat past a threshold no fixture crosses: the
paired bootstrap drew only the **first 256** questions (`R38.8`); a search switched to a generic
plan on its **sixth** execution over one connection (`R38.7`); a store connection per question
exhausted a **100-connection** server (`R38.6`); **one** rung failure in 300 aborted the run
(`R38.12`); a ranking that collapsed below `k` documents was excluded rather than scored
(`R38.5`); and per-role tokens went unrecorded (`R38.9`). Every one of them was found by a paid
run, some after two hours of it.

So this test crosses those thresholds by construction, with the `hash` embedder and no model call
at all: **300 questions** over 60 documents, two arms, one of them repeated, a rung failure planted
on one question, and the evidence table built from the records it writes. It costs seconds and no
money, and it is what `docs/internal/lessons.md` `L24.7` asks to run before any paid measurement.

**The skip is the one every test in this directory takes.** Without a container there is no store
to index into, and `tests/conftest.py`'s `SkipCause.POSTGRES_UNREACHABLE` is the cause it names —
a skip whose reason matches no cause fails the whole run, which is what keeps this from becoming a
test that quietly never runs.

It asserts properties, never the numbers a `hash` embedder happens to produce: `hash` is a
deterministic non-semantic embedder, so *which* documents it ranks first is not a fact about
retrieval quality and nothing here reads it as one.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest

from weft_cli import eval_scoring as eval_scoring_module
from weft_cli.eval_experiment import (
    EvalExperimentArgs,
    EvalExperimentCommand,
    EvalExperimentCommandResult,
)
from weft_cli.route_ask import PipelineDidNotProduceError, run_named_retrieve
from weft_engine.registry_bootstrap import Dependencies, build_dependencies
from weft_eval.evidence import evidence_table
from weft_eval.experiment import load_experiment
from weft_eval.pool import PoolIntegrityError
from weft_eval.run_record import load_run_record
from weft_kernel.context import Context
from weft_kernel.payload import Produced

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_DOCUMENTS = 60
_QUESTIONS_PER_DOCUMENT = 5
_FAILING_DOCUMENT = 8
_FAILING_QUESTION = f"q-{_FAILING_DOCUMENT * _QUESTIONS_PER_DOCUMENT:04d}"

_WORDS = (
    "kestrel heron albatross petrel gannet",
    "lattice hopfield ising potts vertex",
    "corpus retrieval ranking passage index",
)


def _document(number: int) -> str:
    """One document per number, each naming a token no other document carries."""
    return (
        f"# Document {number}\n\nThe unique token for this document is d{number}marker.\n\n"
        f"Every document carries the word weft, so a question's shared words reach a real "
        f"candidate depth; {_WORDS[number % len(_WORDS)]} are this one's own.\n"
    )


def _question_text(document: int) -> str:
    """A question naming the document's own token *and* the word every document carries, so the
    lexical arm retrieves more than `top_k` candidates — a rung that returns fewer is refused by
    the `@k` guard (`R38.5`), which is correct and would make this smoke test measure nothing.
    """
    return f"what does weft say in d{document}marker?"


def _questions() -> str:
    rows = [
        "[question_set]\nschema = 2\n"
        'absent = ["kind", "difficulty", "quote", "reference_answer", "notes"]\n'
        'absent_reason = "a scale smoke, not a corpus study"\naxes = ["bucket"]\n'
    ]
    for document in range(_DOCUMENTS):
        for index in range(_QUESTIONS_PER_DOCUMENT):
            identifier = document * _QUESTIONS_PER_DOCUMENT + index
            bucket = "even" if document % 2 == 0 else "odd"
            rows.append(
                f'\n[[question]]\nid = "q-{identifier:04d}"\n'
                f'text = "{_question_text(document)}"\nlanguage = "en"\n'
                f'relevant_documents = ["doc-{document:03d}.md"]\n'
                f'axes = {{ bucket = "{bucket}" }}\n'
            )
    return "".join(rows)


_EXPERIMENT = """[experiment]
schema = 1
name = "scale-smoke"
questions = "questions.toml"
corpus = "corpus"
repeats = 2
top_k = 5
metrics = ["recall@5", "mrr@5"]
minimum_detectable_effect = 0.05

[[arm]]
name = "vector"
pipeline = "index-text"
repeats = 1

[[arm]]
name = "lexical"
pipeline = "index-text"
query_pipeline = "lexical-retrieve"
"""


async def _database_reachable() -> str | None:
    try:
        connection = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await connection.close()
    return None


async def _open_connections() -> int:
    connection = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            )
            row = await cursor.fetchone()
            return int(cast("tuple[int, ...]", row)[0])
    finally:
        await connection.close()


@pytest.fixture
async def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """A project holding the corpus, the questions and the experiment document — see the module
    docstring for why the skip below is the one every test in this directory takes.
    """
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    connection = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with connection.cursor() as cursor:
        await cursor.execute("TRUNCATE weft_nodes, weft_sources, weft_node_productions")
        await cursor.execute("ALTER TABLE weft_nodes ALTER COLUMN embedding TYPE vector")
    await connection.close()
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for number in range(_DOCUMENTS):
        (corpus / f"doc-{number:03d}.md").write_text(_document(number), encoding="utf-8")
    (tmp_path / "questions.toml").write_text(_questions(), encoding="utf-8")
    (tmp_path / "experiment.toml").write_text(_EXPERIMENT, encoding="utf-8")
    (tmp_path / "weft.toml").write_text(
        f'[packs.store]\ndsn = "{_DSN}"\n\n[services]\nembed = "hash"\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def _ctx(deps: Dependencies) -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="scale", trace_id="scale", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


# 28 s locally, ~57 s on a CI runner (green) and >60 s (red) on 2026-09-18 — the suite's 60 s
# default is too close for a test that runs 300 questions by design.
@pytest.mark.timeout(180)
async def test_an_experiment_over_three_hundred_questions_holds_every_property_a_paid_run_needs(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — one question's rung fails, as a model's unparseable answer did in `38.6`.
    retrieve = run_named_retrieve
    failing_text = _question_text(_FAILING_DOCUMENT)

    async def _one_question_fails(question: str, **kwargs: Any) -> Any:
        if question == failing_text:
            raise PipelineDidNotProduceError(
                "pipeline 'lexical-retrieve' did not produce: planted", pipeline="lexical-retrieve"
            )
        return await retrieve(question, **kwargs)

    monkeypatch.setattr(eval_scoring_module, "run_named_retrieve", _one_question_fails)
    deps = build_dependencies(project / "weft.toml")
    before = await _open_connections()

    # Act
    outcome = await EvalExperimentCommand().run(
        EvalExperimentArgs(path=str(project / "experiment.toml")), _ctx(deps)
    )

    # Assert — the run wrote what the document asked for, per arm.
    assert isinstance(outcome, Produced)
    result = cast("EvalExperimentCommandResult", outcome.value)
    assert {(run.arm, run.repetition) for run in result.runs} == {
        ("vector", 1),
        ("lexical", 1),
        ("lexical", 2),
    }
    records = {
        (run.arm, run.repetition): load_run_record(Path("runs") / f"{run.run_id}.json")
        for run in result.runs
    }
    total = _DOCUMENTS * _QUESTIONS_PER_DOCUMENT

    # Every question is scored, or excluded with its reason, and the planted failure is counted.
    vector = records[("vector", 1)].metrics["recall@5"]
    assert isinstance(vector, Produced)
    assert (vector.value.n, vector.value.excluded) == (total, 0)
    for repetition in (1, 2):
        lexical = records[("lexical", repetition)].metrics["recall@5"]
        assert isinstance(lexical, Produced)
        assert lexical.value.n == total - _QUESTIONS_PER_DOCUMENT
        assert lexical.value.excluded == _QUESTIONS_PER_DOCUMENT
    scores = records[("lexical", 1)].question_scores
    assert scores is not None
    assert "planted" in str(scores["recall@5"].scores[_FAILING_QUESTION])

    # The `hash` embedder reports no usage, which is recorded as no roles rather than as zeros.
    assert records[("vector", 1)].token_usage == {}

    # The bootstrap reads every question, not the first 256: its interval contains its own mean.
    table = evidence_table(load_experiment(project / "experiment.toml"), list(records.values()))
    assert table.comparisons
    for comparison in table.comparisons:
        paired = comparison.paired
        assert paired is not None, comparison.metric
        assert paired.n > 256
        assert paired.low is not None
        assert paired.high is not None
        assert paired.low <= paired.mean <= paired.high, comparison.metric

    # Connections: the run closes every store it opened, whatever the questions did.
    assert await _open_connections() <= before + 1


# --- Task 40.2 — a frozen pool, captured against the real store and replayed without the corpus.
#
# The unit tests hold replay's rules against a store double. What only the real store can answer is
# whether a pool captured through `vector-top-k` and replayed through nothing but a packer scores
# exactly what the capture scored, and whether pgvector hands back by id the chunks a manifest
# names. The corpus is deleted between capture and replay, so a replay that read it fails here.

_POOL_QUESTIONS = 12

_CAPTURE_PIPELINE = """name: dense-pool-retrieve
stages:
  - {id: retrieve, use: vector-top-k, with: {top_k: 50}}
  - {id: fuse, use: single-list}
  - {id: pack, use: repack, with: {method: reverse, top_n: 50}}
"""

_IDENTITY_PIPELINE = """name: replay-identity
stages:
  - {id: pack, use: repack, with: {method: reverse}}
"""


def _pool_experiment(name: str, arms: str) -> str:
    return (
        f'[experiment]\nschema = 1\nname = "{name}"\nquestions = "pool-questions.toml"\n'
        'corpus = "corpus"\nrepeats = 2\ntop_k = [1, 5]\nmetrics = ["mrr@5", "recall@1"]\n'
        "minimum_detectable_effect = 0.05\n" + arms
    )


def _replay_arms(manifest: Path) -> str:
    arm = (
        '\n[[arm]]\nname = "{name}"\npipeline = "index-text"\n'
        'query_pipeline = "replay-identity"\npool = "{pool}"\nrepeats = 1\n'
    )
    return arm.format(name="identity", pool=manifest) + arm.format(name="again", pool=manifest)


@pytest.fixture
def pool_project(project: Path) -> Path:
    """`project`, with a short question set and the two documents a capture and a replay need."""
    lines = _questions().split("\n[[question]]")
    (project / "pool-questions.toml").write_text(
        "\n[[question]]".join(lines[: _POOL_QUESTIONS + 1]), encoding="utf-8"
    )
    (project / "pipelines").mkdir()
    (project / "pipelines" / "dense-pool-retrieve.yaml").write_text(_CAPTURE_PIPELINE)
    (project / "pipelines" / "replay-identity.yaml").write_text(_IDENTITY_PIPELINE)
    arm = (
        '\n[[arm]]\nname = "{name}"\npipeline = "index-text"\n'
        'query_pipeline = "dense-pool-retrieve"\n{extra}repeats = 1\n'
    )
    (project / "capture.toml").write_text(
        _pool_experiment(
            "capture",
            arm.format(name="dense", extra="capture_pool = true\n")
            + arm.format(name="plain", extra=""),
        ),
        encoding="utf-8",
    )
    return project


async def _pool_run(project: Path, document: str) -> dict[str, Any]:
    deps = build_dependencies(project / "weft.toml")
    outcome = await EvalExperimentCommand().run(
        EvalExperimentArgs(path=str(project / document)), _ctx(deps)
    )
    assert isinstance(outcome, Produced)
    result = cast("EvalExperimentCommandResult", outcome.value)
    return {run.arm: load_run_record(Path("runs") / f"{run.run_id}.json") for run in result.runs}


def _scores(record: Any, metric: str) -> dict[str, object]:
    assert record.question_scores is not None
    return dict(record.question_scores[metric].scores)


@pytest.mark.timeout(180)
async def test_an_identity_replay_of_a_captured_pool_scores_what_the_capture_scored(
    pool_project: Path,
) -> None:
    # Arrange
    captured = await _pool_run(pool_project, "capture.toml")
    (manifest,) = (pool_project / "runs" / "pools").glob("*.json")
    shutil.rmtree(pool_project / "corpus")
    (pool_project / "replay.toml").write_text(
        _pool_experiment("replay", _replay_arms(manifest)), encoding="utf-8"
    )

    # Act
    replayed = await _pool_run(pool_project, "replay.toml")

    # Assert
    for metric in ("mrr@5", "recall@1"):
        assert _scores(replayed["identity"], metric) == _scores(captured["dense"], metric), metric
    assert replayed["identity"].corpus.digest == captured["dense"].corpus.digest


@pytest.mark.timeout(180)
async def test_a_manifest_whose_chunk_hash_was_changed_is_refused_naming_the_chunk(
    pool_project: Path,
) -> None:
    # Arrange
    await _pool_run(pool_project, "capture.toml")
    (manifest,) = (pool_project / "runs" / "pools").glob("*.json")
    body = json.loads(manifest.read_text(encoding="utf-8"))
    chunk = body["questions"][0]["chunks"][0]
    chunk["content_sha256"] = "0" * 64
    corrupt = pool_project / "corrupt.json"
    corrupt.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    (pool_project / "replay.toml").write_text(
        _pool_experiment("replay", _replay_arms(corrupt)), encoding="utf-8"
    )
    before = sorted(Path("runs").glob("*.json"))

    # Act
    with pytest.raises(PoolIntegrityError) as caught:
        await _pool_run(pool_project, "replay.toml")

    # Assert
    assert chunk["node_id"] in str(caught.value)
    assert sorted(Path("runs").glob("*.json")) == before, "a refused replay writes no record"
