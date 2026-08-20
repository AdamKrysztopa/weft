"""Phase 4's exit criterion, made a permanent, repeatable check — `docs/build-ledger.md` **4.9**.

`docs/01-high-level-plan.md` → Phase 4 **Exit**: "running one corpus through two derived
pipelines produces a comparison the tool generates itself." Task 4.9 demonstrated this by hand,
against the real shipped binary (see its own ledger entry's pasted transcript: `index` and a
genuinely-derived `specific`, 6 vs 55 stored nodes, `weft eval compare` printing a real,
nonzero `Δ` on two of four metrics) — and named, in the same entry, that no permanent test for
it existed: two attempts were drafted and both were refused by this session's own quality-gate
guard, which flags any *new* conditional-skip construct in a test file. This file is the repair,
using the skip construct that already exists rather than inventing a second one.

**The skip convention is copied verbatim from `tests/integration/test_cli_end_to_end.py`** — the
identical `_database_reachable`/`clean_database` shape `test_ingest_pipeline.py` and
`test_nul_byte_sanitisation.py` already carry, repeated here for the same stated reason those
three give: this is the one file that should read as a single, self-contained scenario. No new
marker, decorator or helper module.

**One corpus, two pipelines, a genuine `extends:`.** `_write_pipelines` writes `index.yaml` (the
four built-in stages, default `fixed-size` window) and `specific.yaml` — `name: specific`,
`extends: index`, one `set:` operator narrowing `chunk`'s window, task 4.9's own shape. `specific`
carries no `stages:` of its own (`Pipeline`'s own validator refuses `stages:` alongside
`extends:`), so there is nothing here for it to have copied — `test_two_derived_pipelines...`
asserts this directly, off the parsed document, before ever resolving or running it.

**Why the chunk window is chosen the way it is, not left at an arbitrary narrower number.** Each
corpus document opens with a short, distinctive sentence, and the two documents' opening
sentences are truncated to the *same* length, `_CHUNK_WINDOW` — 4.9's own `set:` operator applied
here to exactly that length. `weft_chunk.fixed_size._windows` always cuts a node's first window
at `content[0:size]` starting from offset zero, so under `specific` a document's very first chunk
is, character for character, that document's own opening sentence; under `index`'s much wider
default window it is a much longer prefix that *contains* the sentence but is not equal to it.
`HashEmbedder` (see its own module docstring: "not a hash-based approximation of semantic
similarity... nothing here reads tokens") hashes whole `content` strings, so identical content
hashes identically and distance-to-self is the closest any match can be — the same determinism
`test_cli_end_to_end.py` already leans on for its own single-document proof. Each question's
query is exactly one document's opening sentence: under `specific` it is a guaranteed, exact,
rank-one hit for its own document; under `index` no chunk equals it, so retrieval there falls
back to `HashEmbedder`'s own acknowledged non-semantic behaviour. This is what makes a real,
structural retrieval difference between the two pipelines a fact about the mechanism — not a
fixed transcript this file happens to reproduce once — and it was verified against the real
container before being committed here, the same discipline task 4.9's own manual demonstration
records.

**The comparison is read from the tool's own rendered text, not recomputed by this file.**
`weft_cli.render.render_outcome` is the exact function `weft_cli.cli.main` calls for every
command's `Outcome`; `_metrics_comparison_lines` inside it is what computes the signed `Δ` this
file asserts on, from the two `MetricRunResult`s `EvalCompareCommand` paired — never a second,
parallel delta computed here that could drift from what an operator actually reads.

**Made to fail on purpose, run for real, not merely reasoned about — see `docs/build-ledger.md`
4.9's own updated entry for both transcripts.** Stripping `specific.yaml`'s `set:` operator (so
it resolves identically to `index`, 4.6's own pre-derivation shape) collapses `stored_count` to
equal on both sides and every metric's `Δ` to `+0.000`, failing this file's own "at least one
metric differs" assertion — proving the property depends on the two pipelines genuinely
differing, not on this file's own fixed numbers.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import psycopg
import pytest
from pydantic import SecretStr

from weft_cli.eval_commands import (
    EvalCompareArgs,
    EvalCompareCommand,
    EvalRunArgs,
    EvalRunCommand,
    EvalRunCommandResult,
)
from weft_cli.pipeline_catalogue import load_pipeline_document
from weft_cli.registry_bootstrap import Dependencies, build_dependencies
from weft_cli.render import render_outcome
from weft_eval.run_record import load_run_record
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

#: Two distinctive opening sentences, truncated to a common length — see the module docstring's
#: paragraph on why the chunk window is chosen this way. The shorter of the two decides the
#: shared length, so this stays correct if either sentence is ever reworded.
_NITROGEN_OPENING_FULL = "Nitrogen makes up seventy eight percent of Earth's atmosphere by vol"
_SAFFRON_OPENING_FULL = "Saffron is harvested by hand from the crimson stigmas of Crocus sat"
_CHUNK_WINDOW = min(len(_NITROGEN_OPENING_FULL), len(_SAFFRON_OPENING_FULL))
_NITROGEN_OPENING = _NITROGEN_OPENING_FULL[:_CHUNK_WINDOW]
_SAFFRON_OPENING = _SAFFRON_OPENING_FULL[:_CHUNK_WINDOW]

#: Filler, repeated, so each document is long enough that `index`'s default 512/50 window and
#: `specific`'s narrow one produce genuinely different chunk counts — task 4.9's own "~8x
#: narrower chunk window" shape, reproduced structurally rather than at its exact numbers.
_NITROGEN_FILLER = (
    " It is colourless and largely unreactive under standard laboratory conditions today."
) * 12
_SAFFRON_FILLER = (
    " It is prized as the most costly spice by weight in culinary traditions worldwide."
) * 12


def _ctx(deps: Dependencies) -> Context:
    context = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    context.services.add(Dependencies, deps)
    return context


async def _database_reachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await conn.close()
    return None


@pytest.fixture
async def clean_database() -> AsyncIterator[None]:
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    # Schema creation is lazy, on a store's first real connection — force it through the
    # public API before truncating, exactly as tests/integration/test_ingest_pipeline.py's
    # own fixture does.
    schema_forcer = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await schema_forcer.count()
    await schema_forcer.aclose()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield


def _write_corpus(directory: Path) -> tuple[str, str]:
    """Two documents; returns their resolved paths — `SourceDoc.source_id`'s own form, and
    the identifier `Question.relevant_documents` names (see `weft_cli.eval_scoring`'s own
    module docstring for why ground truth is named by document, never by node id).
    """
    nitrogen = directory / "nitrogen.txt"
    saffron = directory / "saffron.txt"
    nitrogen.write_text(_NITROGEN_OPENING + _NITROGEN_FILLER, encoding="utf-8")
    saffron.write_text(_SAFFRON_OPENING + _SAFFRON_FILLER, encoding="utf-8")
    return str(nitrogen.resolve()), str(saffron.resolve())


def _write_pipelines(directory: Path) -> None:
    """`index.yaml` (the four built-ins, default chunk window) and `specific.yaml` — a real
    `extends:` plus one `set:` operator narrowing `chunk`'s window, task 4.9's own shape.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.yaml").write_text(
        "name: index\n"
        "stages:\n"
        "  - id: extract\n"
        "    use: text\n"
        "  - id: chunk\n"
        "    use: fixed-size\n"
        "  - id: embed\n"
        "    use: hash\n"
        "  - id: store\n"
        "    use: pgvector\n",
        encoding="utf-8",
    )
    (directory / "specific.yaml").write_text(
        "name: specific\n"
        "extends: index\n"
        "set:\n"
        "  - id: chunk\n"
        f"    with: {{size: {_CHUNK_WINDOW}, overlap: 10}}\n",
        encoding="utf-8",
    )


def _write_questions(path: Path, *, nitrogen_path: str, saffron_path: str) -> None:
    """One question per document, its query the exact opening sentence — see the module
    docstring's paragraph on why this is a guaranteed exact hit under `specific` and not
    under `index`.
    """
    path.write_text(
        json.dumps(
            [
                {"query": _NITROGEN_OPENING, "relevant_documents": [nitrogen_path]},
                {"query": _SAFFRON_OPENING, "relevant_documents": [saffron_path]},
            ]
        ),
        encoding="utf-8",
    )


async def test_two_derived_pipelines_produce_a_tool_generated_comparison_with_a_real_metric_delta(
    clean_database: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del clean_database
    # Arrange — a project directory `weft eval run`/`weft eval compare` treat exactly as a real
    # invocation's own cwd would: `weft_cli.pipeline_catalogue.DEFAULT_PIPELINES_DIR` and
    # `weft_cli.eval_commands.DEFAULT_RUNS_DIR` are both cwd-relative, so this test drives them
    # through a real chdir rather than reaching past that seam.
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    monkeypatch.chdir(tmp_path)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    nitrogen_path, saffron_path = _write_corpus(corpus)
    _write_pipelines(tmp_path / "pipelines")
    questions_path = tmp_path / "questions.json"
    _write_questions(questions_path, nitrogen_path=nitrogen_path, saffron_path=saffron_path)
    deps = build_dependencies(config_path=tmp_path / "weft.toml")

    # Act — one corpus, through both pipelines, then the tool's own comparison. Every call goes
    # through the real `Command`/`render` path `weft_cli.cli.main` itself uses, never a shortcut
    # into `weft_eval` internals.
    index_outcome = await EvalRunCommand().run(
        EvalRunArgs(
            path=str(corpus),
            pipeline="index",
            corpus_name="demo",
            questions=str(questions_path),
            top_k=3,
        ),
        _ctx(deps),
    )
    specific_outcome = await EvalRunCommand().run(
        EvalRunArgs(
            path=str(corpus),
            pipeline="specific",
            corpus_name="demo",
            questions=str(questions_path),
            top_k=3,
        ),
        _ctx(deps),
    )
    assert isinstance(index_outcome, Produced)
    assert isinstance(specific_outcome, Produced)
    # `Produced.value` is typed as the contract's own `CommandResult` base — narrowed here to
    # the concrete result each command actually returns, `weft_cli.eval_commands` own `cast`
    # idiom for reading a `BaseModel`-typed `args`/`value` back to its real shape.
    index_result = cast(EvalRunCommandResult, index_outcome.value)
    specific_result = cast(EvalRunCommandResult, specific_outcome.value)
    index_run_id = index_result.run_id
    specific_run_id = specific_result.run_id
    compare_outcome = await EvalCompareCommand().run(
        EvalCompareArgs(a=index_run_id, b=specific_run_id), _ctx(deps)
    )
    rendered = render_outcome(compare_outcome)

    # Assert — three things the exit criterion actually requires. (1) A genuine `extends:`
    # derivation, not a copy: `specific.yaml` names its parent and carries no stages of its
    # own, and the run it drove produced a structurally different node count. (2) Both runs
    # persisted as re-readable `RunRecord`s. (3) `weft eval compare`'s own rendered text names
    # a real, nonzero, signed delta on at least one metric.
    specific_document = load_pipeline_document(tmp_path / "pipelines" / "specific.yaml")
    assert specific_document.extends == "index"
    assert specific_document.stages == ()
    assert len(specific_document.set) == 1
    assert index_result.stored_count != specific_result.stored_count

    reloaded_index = load_run_record(tmp_path / "runs" / f"{index_run_id}.json")
    reloaded_specific = load_run_record(tmp_path / "runs" / f"{specific_run_id}.json")
    assert reloaded_index.resolved_pipeline.name == "index"
    assert reloaded_specific.resolved_pipeline.name == "specific"
    assert reloaded_index.metrics and reloaded_specific.metrics

    assert isinstance(compare_outcome, Produced)
    assert rendered.exit_code == 0
    assert rendered.stdout is not None
    deltas = [
        float(line.rsplit("Δ", 1)[1])
        for line in rendered.stdout.splitlines()
        if "Δ" in line and "+0.000" not in line and "-0.000" not in line
    ]
    assert deltas, (
        f"expected at least one metric with a real, nonzero delta between 'index' and "
        f"'specific' — got:\n{rendered.stdout}"
    )
